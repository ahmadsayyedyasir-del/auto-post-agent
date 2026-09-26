import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { workflowService } from '../../services/workflows';
import { publicationService } from '../../services/publications';
import { scheduleService } from '../../services/schedules';
import { useToast } from '../../context/ToastContext';
import { WorkflowDetailResponse, HumanReviewAction } from '../../types';
import { Card } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { StatusBadge } from '../../components/ui/StatusBadge';
import { Modal } from '../../components/ui/Modal';
import { ConfirmDialog } from '../../components/ui/ConfirmDialog';
import { Textarea } from '../../components/ui/Input';
import { PostPreview } from '../../components/workflow/PostPreview';
import { CriticPanel } from '../../components/workflow/CriticPanel';
import { RevisionDiff } from '../../components/workflow/RevisionDiff';
import { PublishModal } from '../../components/publication/PublishModal';
import { ScheduleModal } from '../../components/schedule/ScheduleModal';
import { LoadingSpinner } from '../../components/ui/LoadingSpinner';
import { ErrorState } from '../../components/ui/ErrorState';
import { EmptyState } from '../../components/ui/EmptyState';
import {
  CheckCircle,
  RotateCcw,
  Edit3,
  XCircle,
  Send,
  Clock,
  Eye,
  ArrowLeft,
  Sparkles,
  ShieldCheck,
} from 'lucide-react';

export const HITLReviewPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { success, error: toastError } = useToast();

  const [pendingWorkflows, setPendingWorkflows] = useState<WorkflowDetailResponse[]>([]);
  const [currentWorkflow, setCurrentWorkflow] = useState<WorkflowDetailResponse | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Review Modals & State
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [reviseModalOpen, setReviseModalOpen] = useState<boolean>(false);
  const [reviseFeedback, setReviseFeedback] = useState<string>('');
  const [editModalOpen, setEditModalOpen] = useState<boolean>(false);
  const [editContent, setEditContent] = useState<string>('');
  const [rejectDialogOpen, setRejectDialogOpen] = useState<boolean>(false);

  // Post-Approval Actions
  const [publishModalOpen, setPublishModalOpen] = useState<boolean>(false);
  const [scheduleModalOpen, setScheduleModalOpen] = useState<boolean>(false);

  const fetchWorkflowsForReview = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      if (id) {
        const wf = await workflowService.getWorkflow(id);
        setCurrentWorkflow(wf);
      } else {
        const list = await workflowService.listWorkflows();
        const pending = list.filter(
          (w) => w.status === 'WAITING_FOR_HUMAN_REVIEW' || w.status === 'HUMAN_REVIEW'
        );
        setPendingWorkflows(pending);
        if (pending.length === 1) {
          setCurrentWorkflow(pending[0]);
        }
      }
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Failed to load workflows for review.';
      setError(msg);
    } finally {
      setIsLoading(false);
    }
  }, [id]);

  useEffect(() => {
    fetchWorkflowsForReview();
  }, [fetchWorkflowsForReview]);

  const handleSubmitDecision = async (action: HumanReviewAction, feedback?: string, content?: string) => {
    if (!currentWorkflow) return;
    setIsSubmitting(true);
    try {
      const updated = await workflowService.submitReview(currentWorkflow.id, {
        action,
        feedback: feedback ? [feedback] : undefined,
        content: content || undefined,
      });

      setCurrentWorkflow(updated);

      if (action === 'APPROVE') {
        success('Post draft approved successfully!');
      } else if (action === 'REVISE') {
        success('Revision instructions dispatched to Writer Agent!');
        setReviseModalOpen(false);
        navigate(`/workflows/${currentWorkflow.id}`);
      } else if (action === 'EDIT') {
        success('Edited text submitted. Critic Agent is verifying compliance!');
        setEditModalOpen(false);
        navigate(`/workflows/${currentWorkflow.id}`);
      } else if (action === 'REJECT') {
        setRejectDialogOpen(false);
        if (updated.status === 'REJECTED') {
          success('Maximum human rejections reached (3). Workflow execution terminated.');
          navigate('/workflows');
        } else {
          success(
            `Draft rejected (Rejection ${updated.human_rejection_count || 1}/${updated.max_human_rejections || 3}). Writer and Critic agents generated an improved variation!`
          );
        }
      }
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Failed to submit review decision.';
      toastError(msg);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handlePublish = async (platformOverride?: string) => {
    if (!currentWorkflow) return;
    setIsSubmitting(true);
    try {
      const pub = await publicationService.publishWorkflow(currentWorkflow.id, {
        platform_override: platformOverride,
      });
      success(`Successfully published post to ${pub.platform}!`);
      setPublishModalOpen(false);
      navigate(`/workflows/${currentWorkflow.id}`);
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Failed to publish.';
      toastError(msg);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleSchedule = async (scheduledAt: string, timezone: string, platform?: string) => {
    if (!currentWorkflow) return;
    setIsSubmitting(true);
    try {
      await scheduleService.createSchedule({
        workflow_id: currentWorkflow.id,
        platform: platform || currentWorkflow.target_platform,
        scheduled_at: scheduledAt,
        timezone,
      });
      success('Post successfully scheduled for publication!');
      setScheduleModalOpen(false);
      navigate('/schedules');
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Failed to schedule post.';
      toastError(msg);
    } finally {
      setIsSubmitting(false);
    }
  };

  if (isLoading) {
    return <LoadingSpinner message="Loading review station..." />;
  }

  if (error) {
    return <ErrorState message={error} onRetry={fetchWorkflowsForReview} />;
  }

  // If on /review without ID and multiple or zero pending
  if (!id && !currentWorkflow) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-6)' }}>
        <div>
          <h1 style={{ fontSize: '1.75rem', fontWeight: 800, letterSpacing: '-0.02em' }}>
            Human-in-the-Loop Review Queue
          </h1>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.925rem' }}>
            Select an AI-generated draft awaiting human signoff.
          </p>
        </div>

        {pendingWorkflows.length === 0 ? (
          <EmptyState
            title="Review Queue is Empty"
            description="All workflows have been reviewed or are currently in autonomous progress."
            icon={<CheckCircle size={32} color="var(--success)" />}
            action={{
              label: 'View All Workflows',
              onClick: () => navigate('/workflows'),
            }}
          />
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))', gap: 'var(--space-4)' }}>
            {pendingWorkflows.map((wf) => (
              <Card key={wf.id}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 'var(--space-2)' }}>
                  <span style={{ fontWeight: 700, fontSize: '1.05rem' }}>{wf.niche}</span>
                  <StatusBadge status={wf.status} />
                </div>
                <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', marginBottom: 'var(--space-4)' }}>
                  Platform: <strong style={{ textTransform: 'capitalize' }}>{wf.target_platform}</strong> • Revisions: <strong>{wf.revision_count}</strong>
                </p>
                <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                  <Link to={`/review/${wf.id}`}>
                    <Button variant="primary" size="sm" rightIcon={<Eye size={14} />}>
                      Review Draft
                    </Button>
                  </Link>
                </div>
              </Card>
            ))}
          </div>
        )}
      </div>
    );
  }

  if (!currentWorkflow) {
    return <ErrorState message="Workflow not found." />;
  }

  const primaryPost = currentWorkflow.posts && currentWorkflow.posts.length > 0 ? currentWorkflow.posts[0] : null;
  const isApproved = currentWorkflow.status === 'APPROVED' || currentWorkflow.status === 'PUBLISHED';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-6)' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 'var(--space-4)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)' }}>
          <Link to="/workflows">
            <Button size="sm" variant="ghost" leftIcon={<ArrowLeft size={16} />}>
              Back
            </Button>
          </Link>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)' }}>
              <h1 style={{ fontSize: '1.5rem', fontWeight: 800, letterSpacing: '-0.02em' }}>
                HITL Review: {currentWorkflow.niche}
              </h1>
              <StatusBadge status={currentWorkflow.status} />
            </div>
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
              Platform: <strong style={{ textTransform: 'capitalize' }}>{currentWorkflow.target_platform}</strong> • Agent Revisions: <strong>{currentWorkflow.agent_revision_count}</strong> • Human Revisions: <strong>{currentWorkflow.human_revision_count}</strong> • Human Rejections: <strong>{currentWorkflow.human_rejection_count || 0}/{currentWorkflow.max_human_rejections || 3}</strong>
            </p>
          </div>
        </div>

        {/* Action Controls */}
        <div style={{ display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap' }}>
          {!isApproved && (
            <>
              <Button
                variant="danger"
                size="sm"
                onClick={() => setRejectDialogOpen(true)}
                disabled={isSubmitting}
                leftIcon={<XCircle size={15} />}
              >
                Reject
              </Button>

              <Button
                variant="secondary"
                size="sm"
                onClick={() => {
                  setEditContent(primaryPost?.content || '');
                  setEditModalOpen(true);
                }}
                disabled={isSubmitting}
                leftIcon={<Edit3 size={15} />}
              >
                Edit Content
              </Button>

              <Button
                variant="secondary"
                size="sm"
                onClick={() => setReviseModalOpen(true)}
                disabled={isSubmitting}
                leftIcon={<RotateCcw size={15} />}
              >
                Request AI Revision
              </Button>

              <Button
                variant="success"
                size="sm"
                onClick={() => handleSubmitDecision('APPROVE')}
                isLoading={isSubmitting}
                leftIcon={<CheckCircle size={15} />}
              >
                Approve Post
              </Button>
            </>
          )}

          {isApproved && (
            <>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setScheduleModalOpen(true)}
                leftIcon={<Clock size={16} />}
              >
                Schedule Publication
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
        </div>
      </div>

      {/* Post & Critic Panels */}
      {primaryPost && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(420px, 1fr))', gap: 'var(--space-6)' }}>
          <PostPreview post={primaryPost} />
          <CriticPanel feedbacks={currentWorkflow.feedbacks} />
        </div>
      )}

      {/* Revision Diff Viewer */}
      {primaryPost && primaryPost.revisions && primaryPost.revisions.length > 0 && (
        <RevisionDiff revisions={primaryPost.revisions} />
      )}

      {/* REVISE Feedback Modal */}
      <Modal
        isOpen={reviseModalOpen}
        onClose={() => setReviseModalOpen(false)}
        title="Request AI Agent Revision"
        footer={
          <>
            <Button variant="ghost" onClick={() => setReviseModalOpen(false)} disabled={isSubmitting}>
              Cancel
            </Button>
            <Button
              variant="primary"
              onClick={() => handleSubmitDecision('REVISE', reviseFeedback)}
              isLoading={isSubmitting}
              leftIcon={<Sparkles size={16} />}
            >
              Submit Feedback to Writer
            </Button>
          </>
        }
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
            Enter actionable instructions. The Writer Agent will rewrite the copy, and the Critic Agent will re-verify compliance.
          </p>
          <Textarea
            label="Revision Instructions"
            placeholder="e.g., Shorten the opening hook, emphasize actionable ROI, and add 2 hashtags."
            value={reviseFeedback}
            onChange={(e) => setReviseFeedback(e.target.value)}
            rows={4}
            required
          />
        </div>
      </Modal>

      {/* EDIT Direct Edit Modal */}
      <Modal
        isOpen={editModalOpen}
        onClose={() => setEditModalOpen(false)}
        title="Direct Content Edit (Critic Validated)"
        maxWidth="680px"
        footer={
          <>
            <Button variant="ghost" onClick={() => setEditModalOpen(false)} disabled={isSubmitting}>
              Cancel
            </Button>
            <Button
              variant="primary"
              onClick={() => handleSubmitDecision('EDIT', undefined, editContent)}
              isLoading={isSubmitting}
              leftIcon={<ShieldCheck size={16} />}
            >
              Save & Run Critic Validation
            </Button>
          </>
        }
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
            Modify the post text directly. The edited text will be saved as a revision snapshot and evaluated by the Critic Agent.
          </p>
          <Textarea
            label="Post Text"
            value={editContent}
            onChange={(e) => setEditContent(e.target.value)}
            rows={8}
            required
          />
        </div>
      </Modal>

      {/* REJECT Confirmation Dialog */}
      <ConfirmDialog
        isOpen={rejectDialogOpen}
        onClose={() => setRejectDialogOpen(false)}
        onConfirm={() => handleSubmitDecision('REJECT')}
        title="Reject Content Draft?"
        message={
          (currentWorkflow.human_rejection_count || 0) < (currentWorkflow.max_human_rejections || 3)
            ? `Rejecting this draft will increment the rejection counter (${(currentWorkflow.human_rejection_count || 0) + 1}/${currentWorkflow.max_human_rejections || 3}) and send it back to the Writer and Critic agents for an improved variation. After 3 rejections, the workflow will terminate.`
            : `This is the 4th rejection. Submitting will terminate the workflow run and mark it as REJECTED.`
        }
        confirmLabel={(currentWorkflow.human_rejection_count || 0) < (currentWorkflow.max_human_rejections || 3) ? "Reject & Improve" : "Reject & Terminate"}
        variant="danger"
        isLoading={isSubmitting}
      />

      {/* Publish & Schedule Modals */}
      <PublishModal
        isOpen={publishModalOpen}
        onClose={() => setPublishModalOpen(false)}
        onPublish={handlePublish}
        defaultPlatform={currentWorkflow.target_platform}
        isLoading={isSubmitting}
      />

      <ScheduleModal
        isOpen={scheduleModalOpen}
        onClose={() => setScheduleModalOpen(false)}
        onSchedule={handleSchedule}
        defaultPlatform={currentWorkflow.target_platform}
        isLoading={isSubmitting}
      />
    </div>
  );
};
