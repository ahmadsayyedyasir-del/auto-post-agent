/**
 * TypeScript type definitions corresponding to backend FastAPI schemas and models.
 */

export interface User {
  id: string;
  email: string;
  full_name: string | null;
  is_active: boolean;
  is_superuser: boolean;
  created_at: string;
  updated_at: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface AccessTokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

export interface MessageResponse {
  message: string;
}

export interface CredentialMetadata {
  id: string;
  platform: string;
  credential_key: string;
  created_at: string;
  updated_at: string;
}

export interface CredentialListResponse {
  credentials: CredentialMetadata[];
  total: number;
  items?: CredentialMetadata[];
}

export interface CredentialDeleteResponse {
  deleted: boolean;
  platform: string;
  credential_key: string;
  message?: string;
}

export interface UpsertCredentialRequest {
  platform: string;
  credential_key: string;
  credential_value: string;
}

export type WorkflowStatus =
  | 'STARTING'
  | 'RESEARCHING'
  | 'PLANNING'
  | 'WRITING'
  | 'CRITIQUING'
  | 'WAITING_FOR_HUMAN_REVIEW'
  | 'HUMAN_REVIEW'
  | 'APPROVED'
  | 'PUBLISHED'
  | 'COMPLETED'
  | 'REJECTED'
  | 'FAILED';

export type HumanReviewAction = 'APPROVE' | 'REVISE' | 'REJECT' | 'EDIT';

export interface RevisionResponse {
  id: string;
  revision_number: number;
  revision_source: string;
  content: string;
  hashtags: string[];
  cta: string | null;
  source_references: string[];
  revision_feedback: string[];
}

export interface PostResponse {
  id: string;
  platform: string;
  topic: string;
  content: string;
  status: string;
  content_type: string;
  language: string;
  hashtags: string[];
  cta: string | null;
  source_references: string[];
  revisions: RevisionResponse[];
}

export interface FeedbackResponse {
  id: string;
  feedback_source: string;
  decision: string;
  issues: string[];
  feedback_items: string[];
  reviewer_notes: string | null;
}

export interface PublicationResponse {
  id: string;
  workflow_run_id: string;
  post_id: string;
  platform: string;
  status: 'PENDING' | 'PUBLISHING' | 'PUBLISHED' | 'FAILED';
  idempotency_key: string;
  external_post_id: string | null;
  external_url: string | null;
  attempt_count: number;
  last_attempt_at: string | null;
  published_at: string | null;
  error_code: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface PublicationListResponse {
  publications: PublicationResponse[];
  total: number;
}

export interface ScheduleResponse {
  id: string;
  workflow_run_id: string;
  post_id: string;
  platform: string;
  scheduled_at: string;
  timezone: string;
  status: 'SCHEDULED' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'CANCELLED';
  job_id: string | null;
  attempt_count: number;
  last_error: string | null;
  executed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ScheduleListResponse {
  schedules: ScheduleResponse[];
  total: number;
}

export interface WorkflowDetailResponse {
  id: string;
  niche: string;
  target_platform: string;
  audience: string | null;
  language: string;
  status: WorkflowStatus;
  current_stage: string | null;
  revision_count: number;
  agent_revision_count: number;
  human_revision_count: number;
  max_revisions: number;
  research_data: Record<string, unknown> | null;
  content_plan: Record<string, unknown> | null;
  error_message: string | null;
  posts: PostResponse[];
  feedbacks: FeedbackResponse[];
  publications: PublicationResponse[];
  schedules: ScheduleResponse[];
}

export interface ResearchRequest {
  niche: string;
  platform?: string;
  audience?: string;
  language?: string;
  max_trends?: number;
  days_back?: number;
}

export interface HumanReviewPayload {
  action: HumanReviewAction;
  feedback?: string[] | string | null;
  content?: string | null;
}

export interface PublishWorkflowRequest {
  platform_override?: string | null;
}

export interface CreateScheduleRequest {
  workflow_id: string;
  post_id?: string | null;
  platform?: string | null;
  scheduled_at: string;
  timezone?: string;
}

export interface UpdateScheduleRequest {
  scheduled_at?: string | null;
  timezone?: string | null;
}
