import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { workflowService } from '../../services/workflows';
import { publicationService } from '../../services/publications';
import { scheduleService } from '../../services/schedules';
import { useToast } from '../../context/ToastContext';
import { WorkflowDetailResponse, WorkflowStatus } from '../../types';
import { Card } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { StatusBadge } from '../../components/ui/StatusBadge';
import { Stepper } from '../../components/ui/Stepper';
import { ConfirmDialog } from '../../components/ui/Modal';
import { PostPreview } from '../../components/workflow/PostPreview';
import { CriticPanel } from '../../components/workflow/CriticPanel';
import { RevisionDiff } from '../../components/workflow/RevisionDiff';
import { PublishModal } from '../../components/publication/PublishModal';
import { ScheduleModal } from '../../components/schedule/ScheduleModal';
import { LoadingSpinner } from '../../components/ui/LoadingSpinner';
import { ErrorState } from '../../components/ui/ErrorState';
import {
  Eye,
  Send,
  Clock,
  RefreshCw,
  ExternalLink,
  FileText,
  Compass,
  AlertTriangle,
  Trash2,
} from 'lucide-react';

const TERMINAL_STATUSES: WorkflowStatus[] = [
  'WAITING_FOR_HUMAN_REVIEW',
  'HUMAN_REVIEW',
  'APPROVED',
  'PUBLISHED',
  'COMPLETED',
  'REJECTED',
  'FAILED',
];

export const WorkflowDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [workflow, setWorkflow] = useState<WorkflowDetailResponse | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Polling state
  const [isPolling, setIsPolling] = useState<boolean>(false);
  const [pollingTimeoutReached, setPollingTimeoutReached] = useState<boolean>(false);

  // Action Modals
  const [publishModalOpen, setPublishModalOpen] = useState(false);
  const [scheduleModalOpen, setScheduleModalOpen] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [deleteLoading, setDeleteLoading] = useState(false);

  const { success, error: toastError, warning } = useToast();

  const pollingTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pollingStartTimeRef = useRef<number>(Date.now());
  const errorCountRef = useRef<number>(0);
  const lastStatusRef = useRef<string>('');
  const stageStartTimeRef = useRef<number>(Date.now());

  const workflowRef = useRef<WorkflowDetailResponse | null>(null);
  workflowRef.current = workflow;

  // Store warning in a ref so fetchWorkflow doesn't need it as a dependency
  const warningRef = useRef(warning);
  warningRef.current = warning;

  // Core fetch function stored in a ref to avoid recreating the polling effect.
  // This fixes the stale closure problem: previously, fetchWorkflow was a useCallback
  // with [id, warning] deps, and the polling effect depended on [fetchWorkflow, id].
  // When ToastContext re-rendered (changing `warning`), fetchWorkflow was recreated,
  // which restarted the polling effect — causing infinite effect recreation.
  // By storing the fetch logic in a ref, the polling effect only depends on [id].
  const fetchWorkflowRef = useRef<(isManualRefresh?: boolean) => Promise<void>>();

  const fetchWorkflow = useCallback(
    async (isManualRefresh = false) => {
      if (!id) return;
      if (isManualRefresh) setIsLoading(true);

      try {
        const data = await workflowService.getWorkflow(id);
        setWorkflow(data);
        setError(null);
        errorCountRef.current = 0;

        // Check stage duration for adaptive backoff
        if (data.status !== lastStatusRef.current) {
          lastStatusRef.current = data.status;
          stageStartTimeRef.current = Date.now();
        }

        // Stop polling if reached terminal status
        if (TERMINAL_STATUSES.includes(data.status)) {
          setIsPolling(false);
          if (pollingTimerRef.current) {
            clearTimeout(pollingTimerRef.current);
            pollingTimerRef.current = null;
          }
        }
      } catch (err: unknown) {
        errorCountRef.current += 1;
        if (errorCountRef.current >= 3) {
          setIsPolling(false);
          warningRef.current('Polling paused due to connection issues. Use Refresh button to retry.');
        }
        const msg =
          (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
          'Failed to load workflow execution details.';
        if (!workflowRef.current) setError(msg);
      } finally {
        if (isManualRefresh) setIsLoading(false);
      }
    },
    [id]
  );

  // Keep the ref in sync with the latest fetchWorkflow closure
  fetchWorkflowRef.current = fetchWorkflow;

  // Polling Engine — depends only on [id] to avoid effect recreation from callback changes
  useEffect(() => {
    let isMounted = true;

    const runPollLoop = async () => {
      if (!isMounted) return;

      const elapsedTotal = Date.now() - pollingStartTimeRef.current;
      if (elapsedTotal > 300000) {
        // 5 minutes max timeout
        setPollingTimeoutReached(true);
        setIsPolling(false);
        return;
      }

      // Use the ref to always call the latest fetch logic without recreating the effect
      await fetchWorkflowRef.current?.(false);

      const current = workflowRef.current;
      if (
        isMounted &&
        current &&
        !TERMINAL_STATUSES.includes(current.status) &&
        errorCountRef.current < 3
      ) {
        const stageElapsed = Date.now() - stageStartTimeRef.current;
        const interval = stageElapsed > 30000 ? 4000 : 2000;

        setIsPolling(true);
        pollingTimerRef.current = setTimeout(runPollLoop, interval);
      } else {
        setIsPolling(false);
      }
    };

    // Initial load
    setIsLoading(true);
    pollingStartTimeRef.current = Date.now();
    fetchWorkflowRef.current?.(true).then(() => {
      const current = workflowRef.current;
      if (
        isMounted &&
        current &&
        !TERMINAL_STATUSES.includes(current.status)
      ) {
        setIsPolling(true);
        pollingTimerRef.current = setTimeout(runPollLoop, 2000);
      }
    });

    return () => {
      isMounted = false;
      if (pollingTimerRef.current) {
        clearTimeout(pollingTimerRef.current);
        pollingTimerRef.current = null;
      }
    };
  }, [id]);

  const handlePublish = async (platformOverride?: string) => {
    if (!workflow) return;
    setActionLoading(true);
    try {
      const pub = await publicationService.publishWorkflow(workflow.id, {
        platform_override: platformOverride,
      });
      success(`Successfully published to ${pub.platform}!`);
      setPublishModalOpen(false);
      await fetchWorkflow(true);
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Publishing failed. Check your platform credentials.';
      toastError(msg);
    } finally {
      setActionLoading(false);
    }
  };

  const handleSchedule = async (scheduledAt: string, timezone: string, platform?: string) => {
    if (!workflow) return;
    setActionLoading(true);
    try {
      await scheduleService.createSchedule({
        workflow_id: workflow.id,
        platform: platform || workflow.target_platform,
        scheduled_at: scheduledAt,
        timezone,
      });
      success('Post successfully scheduled!');
      setScheduleModalOpen(false);
      await fetchWorkflow(true);
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Failed to schedule post.';
      toastError(msg);
    } finally {
      setActionLoading(false);
    }
  };

  if (isLoading && !workflow) {
    return <LoadingSpinner message="Loading workflow details..." />;
  }

  if (error && !workflow) {
    return <ErrorState message={error} onRetry={() => fetchWorkflow(true)} />;
  }

  if (!workflow) {
    return <ErrorState message="Workflow not found." />;
  }

  const isReviewRequired =
    workflow.status === 'WAITING_FOR_HUMAN_REVIEW' || workflow.status === 'HUMAN_REVIEW';
  const isApproved = workflow.status === 'APPROVED' || workflow.status === 'PUBLISHED';
  const primaryPost = workflow.posts && workflow.posts.length > 0 ? workflow.posts[0] : null;

  // Deletable when not actively executing
  const ACTIVE_STATUSES: WorkflowStatus[] = ['STARTING', 'RESEARCHING', 'PLANNING', 'WRITING', 'CRITIQUING'];
  const isDeletable = !ACTIVE_STATUSES.includes(workflow.status);

  const handleDeleteWorkflow = async () => {
    if (!workflow) return;
    setDeleteLoading(true);
    try {
      await workflowService.deleteWorkflow(workflow.id);
      success('Workflow deleted successfully.');
      setDeleteDialogOpen(false);
      navigate('/workflows');
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Failed to delete workflow.';
      toastError(msg);
    } finally {
      setDeleteLoading(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-6)' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 'var(--space-4)' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)' }}>
            <h1 style={{ fontSize: '1.6rem', fontWeight: 800, letterSpacing: '-0.02em' }}>
              {workflow.niche}
            </h1>
            <StatusBadge status={workflow.status} />
          </div>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.875rem', marginTop: 'var(--space-1)' }}>
            Target Platform: <strong style={{ textTransform: 'capitalize' }}>{workflow.target_platform}</strong> • Audience: <strong>{workflow.audience || 'General'}</strong> • Language: <strong>{workflow.language}</strong>
          </p>
        </div>

        <div style={{ display: 'flex', gap: 'var(--space-3)', flexWrap: 'wrap' }}>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => fetchWorkflow(true)}
            aria-label="Refresh"
            leftIcon={<RefreshCw size={14} className={isPolling ? 'animate-spin' : ''} />}
          >
            {isPolling ? 'Polling Progress...' : 'Refresh'}
          </Button>

          {isReviewRequired && (
            <Link to={`/review/${workflow.id}`}>
              <Button variant="primary" size="sm" leftIcon={<Eye size={16} />}>
                Review Draft (Action Required)
              </Button>
            </Link>
          )}

          {isApproved && (
            <>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setScheduleModalOpen(true)}
                leftIcon={<Clock size={16} />}
              >
                Schedule Post
              </Button>
              <Button
                variant="success"
                size="sm"
                onClick={() => setPublishModalOpen(true)}
                leftIcon={<Send size={16} />}
              >
                Publish Now
              </Button>
            </>
          )}

          {isDeletable && (
            <Button
              variant="danger"
              size="sm"
              onClick={() => setDeleteDialogOpen(true)}
              leftIcon={<Trash2 size={14} />}
            >
              Delete Workflow
            </Button>
          )}
        </div>
      </div>

      {/* Polling Timeout Notice if applicable */}
      {pollingTimeoutReached && (
        <div
          style={{
            background: 'var(--warning-bg)',
            border: '1px solid var(--warning-border)',
            borderRadius: 'var(--radius-md)',
            padding: 'var(--space-3) var(--space-4)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            fontSize: '0.875rem',
            color: 'var(--warning)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
            <AlertTriangle size={18} />
            <span>Polling paused after 5 minutes. Click Refresh to query the latest agent status.</span>
          </div>
          <Button size="sm" variant="secondary" onClick={() => fetchWorkflow(true)}>
            Refresh Status
          </Button>
        </div>
      )}

      {/* Stepper Progress */}
      <Card>
        <Stepper
          currentStatus={workflow.status}
          currentStage={workflow.current_stage}
          errorMessage={workflow.error_message}
          revisionCount={workflow.revision_count}
        />
      </Card>

      {/* Live Execution Metadata */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 'var(--space-4)' }}>
        {[
          { label: 'Current Stage', value: workflow.current_stage || workflow.status },
          { label: 'Total Revisions', value: workflow.revision_count },
          { label: 'Agent Revisions', value: workflow.agent_revision_count },
          { label: 'Human Revisions', value: workflow.human_revision_count },
          { label: 'Rejections', value: `${workflow.human_rejection_count} / ${workflow.max_human_rejections}` },
          { label: 'Max Revisions', value: workflow.max_revisions },
        ].map((item) => (
          <div
            key={item.label}
            style={{
              background: 'var(--bg-secondary)',
              borderRadius: 'var(--radius-md)',
              padding: 'var(--space-3) var(--space-4)',
              textAlign: 'center',
            }}
          >
            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 'var(--space-1)' }}>
              {item.label}
            </div>
            <div style={{ fontSize: '1.1rem', fontWeight: 700, textTransform: 'uppercase' }}>
              {item.value}
            </div>
          </div>
        ))}
      </div>

      {/* Failure Callout Box if workflow failed */}
      {workflow.status === 'FAILED' && (
        <div
          style={{
            background: 'rgba(239, 68, 68, 0.08)',
            border: '1px solid rgba(239, 68, 68, 0.3)',
            borderRadius: 'var(--radius-lg)',
            padding: 'var(--space-5) var(--space-6)',
            display: 'flex',
            alignItems: 'flex-start',
            gap: 'var(--space-3)',
          }}
        >
          <AlertTriangle size={24} color="var(--error)" style={{ marginTop: '2px', flexShrink: 0 }} />
          <div>
            <h3 style={{ fontSize: '1.05rem', fontWeight: 700, color: 'var(--error)' }}>
              Execution Failed during stage: {workflow.current_stage || 'UNKNOWN'}
            </h3>
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.875rem', marginTop: 'var(--space-1)' }}>
              {workflow.error_message || 'An unexpected error occurred during workflow execution.'}
            </p>
          </div>
        </div>
      )}

      {/* Review Callout Box if paused */}
      {isReviewRequired && (
        <div
          style={{
            background: 'var(--warning-bg)',
            border: '1px solid var(--warning-border)',
            borderRadius: 'var(--radius-lg)',
            padding: 'var(--space-5) var(--space-6)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: 'var(--space-4)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)' }}>
            <Eye size={26} color="var(--warning)" />
            <div>
              <h3 style={{ fontSize: '1.05rem', fontWeight: 700 }}>Human Review Required</h3>
              <p style={{ color: 'var(--text-secondary)', fontSize: '0.875rem' }}>
                The AI agents generated and validated this draft post. Inspect the content, check critic feedback, and submit your decision.
              </p>
            </div>
          </div>
          <Link to={`/review/${workflow.id}`}>
            <Button variant="primary">Launch Review & Diff Station</Button>
          </Link>
        </div>
      )}

      {/* Generated Post & Critic Row */}
      {primaryPost && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(400px, 1fr))', gap: 'var(--space-6)' }}>
          <PostPreview post={primaryPost} />
          <CriticPanel feedbacks={workflow.feedbacks} />
        </div>
      )}

      {/* Revision Diff View */}
      {primaryPost && primaryPost.revisions && primaryPost.revisions.length > 0 && (
        <RevisionDiff revisions={primaryPost.revisions} />
      )}

      {/* Research & Strategy Snapshot Accordions */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))', gap: 'var(--space-6)' }}>
        {/* Research Data */}
        <Card header={<div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}><Compass size={18} color="var(--info)" /><span style={{ fontWeight: 700 }}>Research Agent Discoveries</span></div>}>
          {workflow.research_data ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)', fontSize: '0.875rem' }}>
              <div>
                <strong>Discovered Trends:</strong>
                <ul style={{ paddingLeft: 'var(--space-4)', marginTop: 'var(--space-1)' }}>
                  {Array.isArray(workflow.research_data.trends)
                    ? (workflow.research_data.trends as Array<{ topic?: string; summary?: string }>).map((t, idx) => (
                        <li key={idx} style={{ marginBottom: 'var(--space-1)' }}>
                          <strong>{t.topic}:</strong> {t.summary}
                        </li>
                      ))
                    : <li>{JSON.stringify(workflow.research_data)}</li>}
                </ul>
              </div>
            </div>
          ) : (
            <div style={{ color: 'var(--text-muted)', fontSize: '0.875rem' }}>
              Research data will appear once research_node completes.
            </div>
          )}
        </Card>

        {/* Content Plan */}
        <Card header={<div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}><FileText size={18} color="var(--accent-light)" /><span style={{ fontWeight: 700 }}>Planning Agent Strategy</span></div>}>
          {workflow.content_plan ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)', fontSize: '0.875rem' }}>
              <div><strong>Topic Strategy:</strong> {String(workflow.content_plan.topic || '')}</div>
              <div><strong>Hook Angle:</strong> {String(workflow.content_plan.hook || '')}</div>
              <div><strong>Core Value Points:</strong>
                <ul style={{ paddingLeft: 'var(--space-4)', marginTop: 'var(--space-1)' }}>
                  {Array.isArray(workflow.content_plan.key_points)
                    ? (workflow.content_plan.key_points as string[]).map((kp, idx) => <li key={idx}>{kp}</li>)
                    : null}
                </ul>
              </div>
            </div>
          ) : (
            <div style={{ color: 'var(--text-muted)', fontSize: '0.875rem' }}>
              Content plan will appear once planning_node completes.
            </div>
          )}
        </Card>
      </div>

      {/* Publications / Execution History */}
      {workflow.publications && workflow.publications.length > 0 && (
        <Card header={<h3 style={{ fontSize: '1rem', fontWeight: 700 }}>Publication Audits</h3>}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
            {workflow.publications.map((pub) => (
              <div
                key={pub.id}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: 'var(--space-3)',
                  background: 'var(--bg-tertiary)',
                  borderRadius: 'var(--radius-md)',
                  flexWrap: 'wrap',
                  gap: 'var(--space-2)',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)' }}>
                  <StatusBadge status={pub.status} />
                  <span style={{ fontWeight: 600, textTransform: 'capitalize' }}>{pub.platform}</span>
                </div>
                {pub.external_url && (
                  <a
                    href={pub.external_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{ display: 'inline-flex', alignItems: 'center', gap: 'var(--space-1)' }}
                  >
                    <span>View Published Post</span>
                    <ExternalLink size={14} />
                  </a>
                )}
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Modals */}
      <PublishModal
        isOpen={publishModalOpen}
        onClose={() => setPublishModalOpen(false)}
        onPublish={handlePublish}
        defaultPlatform={workflow.target_platform}
        isLoading={actionLoading}
      />

      <ScheduleModal
        isOpen={scheduleModalOpen}
        onClose={() => setScheduleModalOpen(false)}
        onSchedule={handleSchedule}
        defaultPlatform={workflow.target_platform}
        isLoading={actionLoading}
      />

      <ConfirmDialog
        isOpen={deleteDialogOpen}
        onClose={() => setDeleteDialogOpen(false)}
        onConfirm={handleDeleteWorkflow}
        title="Delete Workflow"
        message="This action will permanently delete this workflow and all associated posts, revisions, feedback, publications, and schedules. This cannot be undone."
        confirmLabel="Delete Permanently"
        cancelLabel="Keep Workflow"
        variant="danger"
        isLoading={deleteLoading}
      />
    </div>
  );
};
