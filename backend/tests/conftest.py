"""Pytest configuration and environment shims for Windows Application Control environments."""

import os
import sys
import types
import hashlib

# Provide test defaults for security settings in test suite
os.environ.setdefault("JWT_SECRET_KEY", "test_jwt_secret_key_for_testing_purposes_only_32_bytes")
os.environ.setdefault("CREDENTIAL_ENCRYPTION_KEY", "MDEyMzQ1Njc4OTAxMjM0NTY3ODkwMTIzNDU2Nzg5MDE=")

# Provide a pure-Python fallback for xxhash if the C-extension .pyd is blocked by OS policy
if "xxhash" not in sys.modules:
    try:
        import xxhash  # noqa: F401
    except ImportError:
        class _XXHash64:
            def __init__(self, data=b"", seed=0):
                self._hasher = hashlib.sha256(data)
                self._seed = seed

            def update(self, data):
                if isinstance(data, str):
                    data = data.encode("utf-8")
                self._hasher.update(data)

            def intdigest(self):
                return int.from_bytes(self._hasher.digest()[:8], byteorder="big")

            def hexdigest(self):
                return self._hasher.hexdigest()[:16]

            def digest(self):
                return self._hasher.digest()[:8]

        class _XXHash32:
            def __init__(self, data=b"", seed=0):
                self._hasher = hashlib.sha256(data)
                self._seed = seed

            def update(self, data):
                if isinstance(data, str):
                    data = data.encode("utf-8")
                self._hasher.update(data)

            def intdigest(self):
                return int.from_bytes(self._hasher.digest()[:4], byteorder="big")

            def hexdigest(self):
                return self._hasher.hexdigest()[:8]

            def digest(self):
                return self._hasher.digest()[:4]

        mock_xxhash = types.ModuleType("xxhash")
        mock_xxhash.xxh64 = lambda data=b"", seed=0: _XXHash64(data, seed)
        mock_xxhash.xxh32 = lambda data=b"", seed=0: _XXHash32(data, seed)
        mock_xxhash.xxh64_intdigest = lambda data=b"", seed=0: _XXHash64(data, seed).intdigest()
        mock_xxhash.xxh64_hexdigest = lambda data=b"", seed=0: _XXHash64(data, seed).hexdigest()
        mock_xxhash.xxh64_digest = lambda data=b"", seed=0: _XXHash64(data, seed).digest()
        mock_xxhash.xxh32_intdigest = lambda data=b"", seed=0: _XXHash32(data, seed).intdigest()
        mock_xxhash.xxh32_hexdigest = lambda data=b"", seed=0: _XXHash32(data, seed).hexdigest()
        mock_xxhash.xxh32_digest = lambda data=b"", seed=0: _XXHash32(data, seed).digest()
        sys.modules["xxhash"] = mock_xxhash
