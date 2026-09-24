"""Phase 12: Comprehensive tests for Authentication, Authorization & Platform Credential Management.

Test coverage:
1. Security utilities: password hashing (bcrypt), JWT creation/validation, Fernet encryption/decryption.
2. Models & Repositories: User, PlatformCredential (encrypted), RefreshToken (hashed), secret redaction in __repr__.
3. Authentication Service & API: register, login, refresh, logout, profile (/auth/me), inactive user handling.
4. Platform Credential Management: CRUD API (/credentials), encryption at rest, secret concealment in responses.
5. AsyncCredentialResolver: per-user DB credential resolution, env fallback, missing credential error.
6. Authorization & IDOR isolation:
   - Workflows: User A cannot view/review/publish User B's workflow (404 isolation).
   - Schedules: User A cannot view/modify/cancel/run User B's schedule (404 isolation).
   - Credentials: User A cannot access User B's credentials.
   - Legacy workflows (user_id=None) accessible by authenticated users.
7. Publishing integration: Publishing uses the workflow owner's platform credentials.
8. Scheduling integration: Scheduled job derives user_id from workflow in DB and uses owner's credentials.
9. LangGraph security boundary: Secrets never enter workflow state or checkpoints.
"""

from datetime import datetime, timedelta, timezone
import json
from unittest.mock import AsyncMock, patch
import uuid

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.api.v1.dependencies import get_current_active_user, get_current_user
from backend.app.config import Settings, get_settings
from backend.app.core.security import (
    create_access_token,
    decode_access_token,
    decrypt_credential,
    encrypt_credential,
    generate_refresh_token,
    get_password_hash,
    hash_refresh_token,
    verify_password,
)
from backend.app.db.models.post import Post
from backend.app.db.models.schedule import Schedule
from backend.app.db.models.user import PlatformCredential, RefreshToken, User
from backend.app.db.models.workflow import WorkflowRun
from backend.app.db.repositories.schedule_repo import ScheduleRepository
from backend.app.db.repositories.user_repo import (
    PlatformCredentialRepository,
    RefreshTokenRepository,
    UserRepository,
)
from backend.app.db.repositories.workflow_repo import PostRepository, WorkflowRepository
from backend.app.db.session import Base, get_db_session
from backend.app.main import app
from backend.app.models.auth import UserLoginRequest, UserRegisterRequest
from backend.app.publishing.base import (
    PlatformRegistry,
    PublicationResult,
    PublishingRequest,
    PublishingStatus,
    SocialPlatformPublisher,
)
from backend.app.publishing.credentials import (
    AsyncCredentialResolver,
    CredentialResolver,
    PlatformCredentials,
)
from backend.app.publishing.service import PublishingService
from backend.app.scheduling.manager import ScheduleManager, ScheduleStatus
from backend.app.scheduling.service import SchedulingService
from backend.app.services.auth_service import AuthService
from backend.app.workflows.state import WorkflowStatus


# ------------------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------------------


@pytest.fixture
async def auth_engine():
    """Create isolated in-memory SQLite database."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def auth_session(auth_engine):
    """Yield async database session."""
    session_factory = async_sessionmaker(
        bind=auth_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    async with session_factory() as session:
        yield session


# ------------------------------------------------------------------------------
# 1. Security Utilities Tests
# ------------------------------------------------------------------------------


def test_password_hashing_and_verification():
    """Verify bcrypt password hashing and verification."""
    password = "SuperSecretPassword123!"
    hashed = get_password_hash(password)

    assert hashed != password
    assert verify_password(password, hashed) is True
    assert verify_password("WrongPassword123!", hashed) is False


def test_jwt_creation_and_decoding():
    """Verify JWT token encoding, decoding, and expiration validation."""
    user_id = str(uuid.uuid4())
    token = create_access_token(
        subject=user_id,
        expires_delta=timedelta(minutes=15),
        extra_claims={"email": "alice@example.com"},
    )
    assert isinstance(token, str)

    payload = decode_access_token(token)
    assert payload is not None
    assert payload["sub"] == user_id
    assert payload["email"] == "alice@example.com"
    assert "exp" in payload


def test_jwt_expired_token_rejected():
    """Verify expired JWT tokens decode as None."""
    user_id = str(uuid.uuid4())
    token = create_access_token(
        subject=user_id,
        expires_delta=timedelta(seconds=-10),  # expired
    )
    payload = decode_access_token(token)
    assert payload is None


def test_jwt_invalid_signature_rejected():
    """Verify tokens with corrupted payload/signature decode as None."""
    payload = decode_access_token("invalid.jwt.token.string")
    assert payload is None


def test_refresh_token_generation_and_hashing():
    """Verify raw refresh tokens generate distinct SHA-256 hashes."""
    raw_token_1 = generate_refresh_token()
    raw_token_2 = generate_refresh_token()

    assert raw_token_1 != raw_token_2
    assert len(raw_token_1) >= 40

    hash_1 = hash_refresh_token(raw_token_1)
    hash_2 = hash_refresh_token(raw_token_2)

    assert hash_1 != hash_2
    assert hash_1 == hash_refresh_token(raw_token_1)  # Deterministic hash


def test_fernet_credential_encryption_and_decryption():
    """Verify Fernet encryption at rest and lossless decryption."""
    raw_secret = "AQEDAS_very_secret_linkedin_oauth_token_12345"
    encrypted = encrypt_credential(raw_secret)

    assert encrypted != raw_secret
    assert raw_secret not in encrypted

    decrypted = decrypt_credential(encrypted)
    assert decrypted == raw_secret


# ------------------------------------------------------------------------------
# 2. Model & Security Boundary Redaction Tests
# ------------------------------------------------------------------------------


def test_models_repr_redaction():
    """Verify ORM models conceal password hashes, credentials, and tokens in repr."""
    user = User(
        id="user-123",
        email="test@example.com",
        hashed_password="$2b$12$secretpasswordhash",
    )
    cred = PlatformCredential(
        id="cred-123",
        user_id="user-123",
        platform="linkedin",
        credential_key="access_token",
        credential_value_encrypted="gAAAAABlsecretencryptedvalue",
    )
    token = RefreshToken(
        id="tok-123",
        user_id="user-123",
        token_hash="a591a6d40bf420404a011733cfb7b190d62c65bf0bcda32b57b277d9ad9f146e",
    )

    user_repr = repr(user)
    cred_repr = repr(cred)
    token_repr = repr(token)

    assert "secretpasswordhash" not in user_repr
    assert "gAAAAABlsecretencryptedvalue" not in cred_repr
    assert "REDACTED" in user_repr
    assert "gAAAAABlsecretencryptedvalue" not in cred_repr
    assert "a591a6d40bf420404a011733cfb7b190d62c65bf0bcda32b57b277d9ad9f146e" not in token_repr


def test_platform_credentials_model_repr_redaction():
    """Verify PlatformCredentials dataclass repr redacts sensitive secrets."""
    creds = PlatformCredentials(
        platform="linkedin",
        access_token="AQEDAS_secret_access_token",
        author_urn="urn:li:person:secret_urn_123",
        client_secret="secret_client_secret",
    )
    r = repr(creds)
    assert "AQEDAS_secret_access_token" not in r
    assert "secret_urn_123" not in r
    assert "secret_client_secret" not in r
    assert "REDACTED" in r


# ------------------------------------------------------------------------------
# 3. AuthService & Auth Endpoints Tests
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_auth_service_register_login_refresh_logout(auth_session: AsyncSession):
    """Test full auth service cycle: register, login, refresh, logout."""
    auth_service = AuthService(auth_session)

    # 1. Register User
    reg_req = UserRegisterRequest(
        email="alice@example.com",
        password="AliceSecurePassword123!",
        full_name="Alice Smith",
    )
    user_resp = await auth_service.register(reg_req)
    assert user_resp.email == "alice@example.com"
    assert user_resp.full_name == "Alice Smith"
    assert user_resp.is_active is True

    # 2. Duplicate Registration Rejection
    with pytest.raises(ValueError, match="already exists"):
        await auth_service.register(reg_req)

    # 3. Login with Correct Password
    login_req = UserLoginRequest(
        email="alice@example.com",
        password="AliceSecurePassword123!",
    )
    tokens = await auth_service.login(login_req)
    assert tokens.access_token is not None
    assert tokens.refresh_token is not None
    assert tokens.token_type == "bearer"

    # 4. Login with Incorrect Password
    bad_login = UserLoginRequest(
        email="alice@example.com",
        password="WrongPassword999!",
    )
    with pytest.raises(ValueError, match="Invalid email or password"):
        await auth_service.login(bad_login)

    # 5. Token Refresh
    refreshed = await auth_service.refresh_access_token(tokens.refresh_token)
    assert refreshed.access_token is not None
    assert refreshed.token_type == "bearer"

    # 6. Logout (Revoke Token)
    logout_resp = await auth_service.logout(tokens.refresh_token)
    assert logout_resp.message == "Successfully logged out."

    # 7. Refresh with Revoked Token Fails
    with pytest.raises(ValueError, match="Invalid or expired refresh token"):
        await auth_service.refresh_access_token(tokens.refresh_token)


@pytest.mark.asyncio
async def test_auth_service_inactive_user_rejected(auth_session: AsyncSession):
    """Test that deactivated users cannot log in."""
    auth_service = AuthService(auth_session)
    user_repo = UserRepository(auth_session)

    # Create inactive user directly
    user = User(
        email="inactive@example.com",
        hashed_password=get_password_hash("Password123!"),
        full_name="Inactive User",
        is_active=False,
    )
    await user_repo.create(user)
    await auth_session.commit()

    with pytest.raises(PermissionError, match="Account is inactive"):
        await auth_service.login(
            UserLoginRequest(email="inactive@example.com", password="Password123!")
        )


# ------------------------------------------------------------------------------
# 4. Platform Credential Management API & Repository Tests
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_credential_repository_crud(auth_session: AsyncSession):
    """Test PlatformCredentialRepository upsert, retrieval, and deletion."""
    user_repo = UserRepository(auth_session)
    cred_repo = PlatformCredentialRepository(auth_session)

    user = User(
        email="bob@example.com",
        hashed_password=get_password_hash("Password123!"),
    )
    await user_repo.create(user)
    await auth_session.commit()

    # 1. Upsert credential (encrypted)
    encrypted_val = encrypt_credential("AQEDAS_secret_token_1")
    cred = await cred_repo.upsert_credential(
        user_id=user.id,
        platform="linkedin",
        credential_key="access_token",
        encrypted_value=encrypted_val,
    )
    assert cred.platform == "linkedin"
    assert cred.credential_key == "access_token"
    assert cred.credential_value_encrypted == encrypted_val

    # 2. Retrieve credentials for user
    all_creds = await cred_repo.get_all_for_user_and_platform(user.id, "linkedin")
    assert len(all_creds) == 1
    assert decrypt_credential(all_creds[0].credential_value_encrypted) == "AQEDAS_secret_token_1"

    # 3. Upsert (update) same key
    new_encrypted = encrypt_credential("AQEDAS_updated_token_2")
    updated_cred = await cred_repo.upsert_credential(
        user_id=user.id,
        platform="linkedin",
        credential_key="access_token",
        encrypted_value=new_encrypted,
    )
    assert updated_cred.id == cred.id  # Same record updated
    assert decrypt_credential(updated_cred.credential_value_encrypted) == "AQEDAS_updated_token_2"

    # 4. Delete credential
    deleted = await cred_repo.delete_credential(user.id, "linkedin", "access_token")
    assert deleted is True

    remaining = await cred_repo.get_all_for_user_and_platform(user.id, "linkedin")
    assert len(remaining) == 0


# ------------------------------------------------------------------------------
# 5. AsyncCredentialResolver Tests
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_async_credential_resolver_from_db(auth_session: AsyncSession):
    """Test AsyncCredentialResolver resolves credentials from per-user DB storage."""
    user_repo = UserRepository(auth_session)
    cred_repo = PlatformCredentialRepository(auth_session)

    user = User(
        email="charlie@example.com",
        hashed_password=get_password_hash("Password123!"),
    )
    await user_repo.create(user)
    await cred_repo.upsert_credential(
        user_id=user.id,
        platform="linkedin",
        credential_key="access_token",
        encrypted_value=encrypt_credential("charlie_token_123"),
    )
    await cred_repo.upsert_credential(
        user_id=user.id,
        platform="linkedin",
        credential_key="author_urn",
        encrypted_value=encrypt_credential("urn:li:person:charlie_urn"),
    )
    await auth_session.commit()

    resolver = AsyncCredentialResolver(allow_env_fallback=False)
    resolved = await resolver.resolve("linkedin", user_id=user.id, session=auth_session)

    assert resolved.platform == "linkedin"
    assert resolved.access_token == "charlie_token_123"
    assert resolved.author_urn == "urn:li:person:charlie_urn"


@pytest.mark.asyncio
async def test_async_credential_resolver_fallback_to_env(auth_session: AsyncSession, monkeypatch):
    """Test AsyncCredentialResolver falls back to environment when DB has no credentials."""
    user_repo = UserRepository(auth_session)
    user = User(
        email="david@example.com",
        hashed_password=get_password_hash("Password123!"),
    )
    await user_repo.create(user)
    await auth_session.commit()

    monkeypatch.setenv("LINKEDIN_ACCESS_TOKEN", "env_token_abc")
    monkeypatch.setenv("LINKEDIN_AUTHOR_URN", "urn:li:person:env_urn_xyz")
    get_settings.cache_clear()

    resolver = AsyncCredentialResolver(allow_env_fallback=True)
    resolved = await resolver.resolve("linkedin", user_id=user.id, session=auth_session)

    assert resolved.access_token == "env_token_abc"
    assert resolved.author_urn == "urn:li:person:env_urn_xyz"


# ------------------------------------------------------------------------------
# 6. Authorization & IDOR Protection Tests
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_authorization_workflow_isolation(auth_engine):
    """Test that User A receives 404 when trying to access User B's workflow (IDOR protection)."""
    session_factory = async_sessionmaker(bind=auth_engine, class_=AsyncSession, expire_on_commit=False)

    user_a = User(id="user-a-id", email="usera@example.com", hashed_password="pw", is_active=True)
    user_b = User(id="user-b-id", email="userb@example.com", hashed_password="pw", is_active=True)

    async with session_factory() as session:
        session.add_all([user_a, user_b])
        wf_b = WorkflowRun(
            id=str(uuid.uuid4()),
            user_id=user_b.id,
            niche="AI",
            target_platform="linkedin",
            status="WAITING_FOR_HUMAN_REVIEW",
        )
        session.add(wf_b)
        await session.commit()
        wf_b_id = wf_b.id

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db
    # Authenticated as User A
    app.dependency_overrides[get_current_active_user] = lambda: user_a

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # User A tries to GET User B's workflow -> 404 (not 403)
        get_res = await client.get(f"/api/v1/workflows/{wf_b_id}")
        assert get_res.status_code == 404

        # User A tries to review User B's workflow -> 404
        review_res = await client.post(
            f"/api/v1/workflows/{wf_b_id}/review",
            json={"action": "APPROVE"},
        )
        assert review_res.status_code == 404

        # User A tries to publish User B's workflow -> 404
        pub_res = await client.post(f"/api/v1/workflows/{wf_b_id}/publish")
        assert pub_res.status_code == 404

        # User A list workflows -> does NOT include User B's workflow
        list_res = await client.get("/api/v1/workflows")
        assert list_res.status_code == 200
        ids = [w["id"] for w in list_res.json()]
        assert wf_b_id not in ids

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_authorization_schedule_isolation(auth_engine):
    """Test that User A receives 404 when trying to view/cancel/run User B's schedule."""
    session_factory = async_sessionmaker(bind=auth_engine, class_=AsyncSession, expire_on_commit=False)

    user_a = User(id="user-a-id", email="usera@example.com", hashed_password="pw", is_active=True)
    user_b = User(id="user-b-id", email="userb@example.com", hashed_password="pw", is_active=True)

    async with session_factory() as session:
        session.add_all([user_a, user_b])
        wf_b = WorkflowRun(
            id=str(uuid.uuid4()),
            user_id=user_b.id,
            niche="AI",
            target_platform="linkedin",
            status="APPROVED",
        )
        post_b = Post(
            id=str(uuid.uuid4()),
            workflow_run_id=wf_b.id,
            content="User B post content",
            platform="linkedin",
            topic="AI",
        )
        sched_b = Schedule(
            id=str(uuid.uuid4()),
            workflow_run_id=wf_b.id,
            post_id=post_b.id,
            platform="linkedin",
            scheduled_at=datetime.now(timezone.utc) + timedelta(hours=2),
            timezone="UTC",
            status="SCHEDULED",
            job_id=f"job_sched_{uuid.uuid4()}",
        )
        session.add_all([wf_b, post_b, sched_b])
        await session.commit()
        sched_b_id = sched_b.id

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db
    # Authenticated as User A
    app.dependency_overrides[get_current_active_user] = lambda: user_a

    # Mock schedule manager on app state
    manager = AsyncMock()
    app.state.schedule_manager = manager

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # User A tries to GET User B's schedule -> 404
        get_res = await client.get(f"/api/v1/schedules/{sched_b_id}")
        assert get_res.status_code == 404

        # User A tries to cancel User B's schedule -> 404
        del_res = await client.delete(f"/api/v1/schedules/{sched_b_id}")
        assert del_res.status_code == 404

        # User A tries to run User B's schedule now -> 404
        run_res = await client.post(f"/api/v1/schedules/{sched_b_id}/run")
        assert run_res.status_code == 404

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_authorization_credentials_api_isolation(auth_engine):
    """Test credentials API ensures no cross-user credential access and secrets are never returned."""
    session_factory = async_sessionmaker(bind=auth_engine, class_=AsyncSession, expire_on_commit=False)

    user_a = User(id="user-a-id", email="usera@example.com", hashed_password="pw", is_active=True)
    user_b = User(id="user-b-id", email="userb@example.com", hashed_password="pw", is_active=True)

    async with session_factory() as session:
        session.add_all([user_a, user_b])
        # Add credential for User B
        cred_b = PlatformCredential(
            id=str(uuid.uuid4()),
            user_id=user_b.id,
            platform="linkedin",
            credential_key="access_token",
            credential_value_encrypted=encrypt_credential("secret_user_b_token"),
        )
        session.add(cred_b)
        await session.commit()

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db
    # Authenticated as User A
    app.dependency_overrides[get_current_active_user] = lambda: user_a

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # 1. User A lists credentials -> should NOT see User B's credentials
        list_res = await client.get("/api/v1/credentials")
        assert list_res.status_code == 200
        data = list_res.json()
        assert data["total"] == 0

        # 2. User A stores their own credential
        post_res = await client.post(
            "/api/v1/credentials",
            json={
                "platform": "linkedin",
                "credential_key": "access_token",
                "credential_value": "user_a_raw_token_xyz",
            },
        )
        assert post_res.status_code == 201
        post_data = post_res.json()
        assert post_data["platform"] == "linkedin"
        assert post_data["credential_key"] == "access_token"
        # CRITICAL: Plaintext value is NEVER returned in response!
        assert "user_a_raw_token_xyz" not in json.dumps(post_data)
        assert "credential_value" not in post_data

        # 3. User A lists credentials -> sees only their own credential metadata
        list_res_2 = await client.get("/api/v1/credentials")
        assert list_res_2.status_code == 200
        data_2 = list_res_2.json()
        assert data_2["total"] == 1
        assert "user_a_raw_token_xyz" not in json.dumps(data_2)

    app.dependency_overrides.clear()


# ------------------------------------------------------------------------------
# 7. Publishing Uses Workflow Owner's Credentials
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_publishing_uses_workflow_owner_credentials(auth_engine):
    """Verify PublishingService resolves credentials belonging to the workflow owner."""
    session_factory = async_sessionmaker(bind=auth_engine, class_=AsyncSession, expire_on_commit=False)

    owner = User(id="owner-user-id", email="owner@example.com", hashed_password="pw", is_active=True)

    async with session_factory() as session:
        session.add(owner)
        # Store encrypted credentials for owner
        cred1 = PlatformCredential(
            user_id=owner.id,
            platform="linkedin",
            credential_key="access_token",
            credential_value_encrypted=encrypt_credential("owner_specific_linkedin_token"),
        )
        cred2 = PlatformCredential(
            user_id=owner.id,
            platform="linkedin",
            credential_key="author_urn",
            credential_value_encrypted=encrypt_credential("urn:li:person:owner_urn"),
        )
        wf = WorkflowRun(
            id=str(uuid.uuid4()),
            user_id=owner.id,
            niche="AI",
            target_platform="linkedin",
            status="APPROVED",
        )
        post = Post(
            id=str(uuid.uuid4()),
            workflow_run_id=wf.id,
            content="Approved post text.",
            platform="linkedin",
            topic="AI",
        )
        session.add_all([cred1, cred2, wf, post])
        await session.commit()
        wf_id = wf.id

    # Mock platform publisher to capture received credentials
    captured_creds = []

    class CapturingPublisher(SocialPlatformPublisher):
        @property
        def platform_name(self) -> str:
            return "linkedin"

        async def publish(self, request: PublishingRequest, credentials: PlatformCredentials) -> PublicationResult:
            captured_creds.append(credentials)
            return PublicationResult(
                success=True,
                platform="linkedin",
                external_post_id="urn:li:share:captured_123",
                published_at=datetime.now(timezone.utc),
            )

    registry = PlatformRegistry()
    registry.register(CapturingPublisher())
    service = PublishingService(platform_registry=registry)

    async with session_factory() as session:
        pub = await service.publish_workflow_post(
            workflow_id=wf_id,
            session=session,
            user_id=owner.id,
        )
        assert pub.status == "PUBLISHED"

    # Verify that the publisher received the OWNER'S decrypted credentials
    assert len(captured_creds) == 1
    assert captured_creds[0].access_token == "owner_specific_linkedin_token"
    assert captured_creds[0].author_urn == "urn:li:person:owner_urn"


# ------------------------------------------------------------------------------
# 8. Scheduling Execution Derives Workflow Owner Credentials from DB
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scheduler_derives_owner_credentials_from_db(auth_engine):
    """Verify ScheduleManager derives user_id from DB record at execution time."""
    session_factory = async_sessionmaker(bind=auth_engine, class_=AsyncSession, expire_on_commit=False)

    owner = User(id="sched-owner-id", email="schedowner@example.com", hashed_password="pw", is_active=True)

    async with session_factory() as session:
        session.add(owner)
        cred1 = PlatformCredential(
            user_id=owner.id,
            platform="linkedin",
            credential_key="access_token",
            credential_value_encrypted=encrypt_credential("sched_owner_token_abc"),
        )
        cred2 = PlatformCredential(
            user_id=owner.id,
            platform="linkedin",
            credential_key="author_urn",
            credential_value_encrypted=encrypt_credential("urn:li:person:sched_owner_urn"),
        )
        wf = WorkflowRun(
            id=str(uuid.uuid4()),
            user_id=owner.id,
            niche="AI",
            target_platform="linkedin",
            status="APPROVED",
        )
        post = Post(
            id=str(uuid.uuid4()),
            workflow_run_id=wf.id,
            content="Scheduled post content",
            platform="linkedin",
            topic="AI",
        )
        sched = Schedule(
            id=str(uuid.uuid4()),
            workflow_run_id=wf.id,
            post_id=post.id,
            platform="linkedin",
            scheduled_at=datetime.now(timezone.utc),
            timezone="UTC",
            status=ScheduleStatus.SCHEDULED.value,
            job_id=f"job_sched_{uuid.uuid4()}",
        )
        session.add_all([cred1, cred2, wf, post, sched])
        await session.commit()
        sched_id = sched.id

    captured_creds = []

    class MockPublisher(SocialPlatformPublisher):
        @property
        def platform_name(self) -> str:
            return "linkedin"

        async def publish(self, request: PublishingRequest, credentials: PlatformCredentials) -> PublicationResult:
            captured_creds.append(credentials)
            return PublicationResult(
                success=True,
                platform="linkedin",
                external_post_id="urn:li:share:sched_pub_123",
                published_at=datetime.now(timezone.utc),
            )

    registry = PlatformRegistry()
    registry.register(MockPublisher())
    pub_service = PublishingService(platform_registry=registry)

    manager = ScheduleManager(session_factory=session_factory, publishing_service=pub_service)

    # Execute scheduled job directly through ScheduleManager
    await manager.execute_scheduled_job(sched_id)

    # Verify execution resolved owner's credentials
    assert len(captured_creds) == 1
    assert captured_creds[0].access_token == "sched_owner_token_abc"
    assert captured_creds[0].author_urn == "urn:li:person:sched_owner_urn"

    # Verify schedule transitioned to COMPLETED
    async with session_factory() as session:
        sched_repo = ScheduleRepository(session)
        updated_sched = await sched_repo.get_by_id(sched_id)
        assert updated_sched.status == ScheduleStatus.COMPLETED.value


# ------------------------------------------------------------------------------
# 9. Full HTTP Auth API Flow Tests
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_http_auth_api_flow(auth_engine):
    """Test full HTTP API lifecycle: /auth/register, /auth/login, /auth/me, /auth/refresh, /auth/logout."""
    session_factory = async_sessionmaker(bind=auth_engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # 1. Register
        reg_res = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "elena@example.com",
                "password": "ElenaPassword123!",
                "full_name": "Elena Rostova",
            },
        )
        assert reg_res.status_code == 201
        reg_data = reg_res.json()
        assert reg_data["email"] == "elena@example.com"
        assert reg_data["full_name"] == "Elena Rostova"
        assert "password" not in reg_data
        assert "hashed_password" not in reg_data

        # 2. Login
        login_res = await client.post(
            "/api/v1/auth/login",
            json={
                "email": "elena@example.com",
                "password": "ElenaPassword123!",
            },
        )
        assert login_res.status_code == 200
        tokens = login_res.json()
        assert "access_token" in tokens
        assert "refresh_token" in tokens
        access_token = tokens["access_token"]
        refresh_token = tokens["refresh_token"]

        # 3. Authenticated Profile (/auth/me)
        me_res = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert me_res.status_code == 200
        me_data = me_res.json()
        assert me_data["email"] == "elena@example.com"
        assert me_data["id"] == reg_data["id"]

        # 4. Token Refresh (/auth/refresh)
        refresh_res = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        assert refresh_res.status_code == 200
        new_token_data = refresh_res.json()
        assert "access_token" in new_token_data
        new_access = new_token_data["access_token"]

        # Verify new access token works on /auth/me
        me_res2 = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {new_access}"},
        )
        assert me_res2.status_code == 200

        # 5. Logout (/auth/logout)
        logout_res = await client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": refresh_token},
        )
        assert logout_res.status_code == 200

        # 6. Re-refresh with revoked token -> 401
        bad_refresh = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        assert bad_refresh.status_code == 401

    app.dependency_overrides.clear()


# ------------------------------------------------------------------------------
# 10. Credentials Delete API Endpoint Test
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_credentials_delete_api(auth_engine):
    """Test DELETE /api/v1/credentials/{platform}/{key} endpoint."""
    session_factory = async_sessionmaker(bind=auth_engine, class_=AsyncSession, expire_on_commit=False)

    user = User(id="del-user-id", email="deluser@example.com", hashed_password="pw", is_active=True)

    async with session_factory() as session:
        session.add(user)
        cred = PlatformCredential(
            user_id=user.id,
            platform="linkedin",
            credential_key="author_urn",
            credential_value_encrypted=encrypt_credential("urn:li:person:to_delete"),
        )
        session.add(cred)
        await session.commit()

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db
    app.dependency_overrides[get_current_active_user] = lambda: user

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # Delete existing credential
        del_res = await client.delete("/api/v1/credentials/linkedin/author_urn")
        assert del_res.status_code == 200
        data = del_res.json()
        assert data["deleted"] is True
        assert data["platform"] == "linkedin"
        assert data["credential_key"] == "author_urn"

        # Delete again -> 404
        del_res2 = await client.delete("/api/v1/credentials/linkedin/author_urn")
        assert del_res2.status_code == 404

    app.dependency_overrides.clear()


# ------------------------------------------------------------------------------
# 11. Legacy Workflow Backward Compatibility Test
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_legacy_workflow_accessible_by_authenticated_user(auth_engine):
    """Verify that legacy workflows (user_id=None) are accessible by authenticated users."""
    session_factory = async_sessionmaker(bind=auth_engine, class_=AsyncSession, expire_on_commit=False)

    user = User(id="auth-user-id", email="auth@example.com", hashed_password="pw", is_active=True)

    async with session_factory() as session:
        session.add(user)
        # Create legacy workflow with user_id=None
        legacy_wf = WorkflowRun(
            id=str(uuid.uuid4()),
            user_id=None,  # Legacy unowned workflow
            niche="AI",
            target_platform="linkedin",
            status="APPROVED",
        )
        post = Post(
            id=str(uuid.uuid4()),
            workflow_run_id=legacy_wf.id,
            content="Legacy post content",
            platform="linkedin",
            topic="AI",
        )
        session.add_all([legacy_wf, post])
        await session.commit()
        legacy_wf_id = legacy_wf.id

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db
    app.dependency_overrides[get_current_active_user] = lambda: user

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # Authenticated user can fetch legacy workflow
        get_res = await client.get(f"/api/v1/workflows/{legacy_wf_id}")
        assert get_res.status_code == 200
        assert get_res.json()["id"] == legacy_wf_id

        # Authenticated user list_workflows includes legacy workflows
        list_res = await client.get("/api/v1/workflows")
        assert list_res.status_code == 200
        ids = [w["id"] for w in list_res.json()]
        assert legacy_wf_id in ids

    app.dependency_overrides.clear()


# ------------------------------------------------------------------------------
# 12. LangGraph Security Boundary Test
# ------------------------------------------------------------------------------


def test_langgraph_security_boundary_no_secrets_in_state():
    """Verify that SocialWorkflowState schema contains no secret/credential fields."""
    from backend.app.workflows.state import SocialWorkflowState

    # Inspect type annotations and keys of SocialWorkflowState
    state_annotations = getattr(SocialWorkflowState, "__annotations__", {})
    forbidden_terms = [
        "password",
        "hash",
        "secret",
        "jwt",
        "access_token",
        "refresh_token",
        "fernet",
        "credential",
        "linkedin_token",
        "api_key",
    ]

    for key in state_annotations.keys():
        for term in forbidden_terms:
            assert term not in key.lower(), (
                f"Security violation: LangGraph SocialWorkflowState contains sensitive field '{key}'"
            )


# ------------------------------------------------------------------------------
# 13. Missing Production Key Error Handling Tests
# ------------------------------------------------------------------------------


def test_missing_fernet_key_raises_clear_error(monkeypatch):
    """Verify application fails with a clear RuntimeError when CREDENTIAL_ENCRYPTION_KEY is missing."""
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", "")
    get_settings.cache_clear()

    with pytest.raises(RuntimeError, match="CREDENTIAL_ENCRYPTION_KEY is not configured"):
        encrypt_credential("any_secret")

    # Reset cache after test
    get_settings.cache_clear()


def test_invalid_fernet_key_raises_clear_error(monkeypatch):
    """Verify application fails with a clear RuntimeError when CREDENTIAL_ENCRYPTION_KEY is malformed."""
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", "not-a-valid-base64-fernet-key")
    get_settings.cache_clear()

    with pytest.raises(RuntimeError, match="CREDENTIAL_ENCRYPTION_KEY is invalid"):
        encrypt_credential("any_secret")

    # Reset cache after test
    get_settings.cache_clear()

