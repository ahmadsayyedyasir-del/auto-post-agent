import React from 'react';
import { WorkflowStatus } from '../../types';
import { Check, Loader2, XCircle, Clock, AlertTriangle } from 'lucide-react';

export interface StepperStep {
  id: string;
  label: string;
  statuses: WorkflowStatus[];
  description?: string;
}

const DEFAULT_STEPS: StepperStep[] = [
  { id: 'research', label: 'Research', statuses: ['STARTING', 'RESEARCHING'] },
  { id: 'planning', label: 'Planning', statuses: ['PLANNING'] },
  { id: 'writing', label: 'Writing', statuses: ['WRITING'] },
  { id: 'critic', label: 'Critic', statuses: ['CRITIQUING'] },
  { id: 'review', label: 'Review', statuses: ['WAITING_FOR_HUMAN_REVIEW', 'HUMAN_REVIEW'] },
  { id: 'done', label: 'Published', statuses: ['APPROVED', 'PUBLISHED', 'COMPLETED'] },
];

/**
 * Map a `current_stage` value to the step index it belongs to.
 * Returns -1 if no match found.
 */
function stageToStepIndex(stage: string): number {
  const upper = stage.toUpperCase() as WorkflowStatus;
  for (let i = 0; i < DEFAULT_STEPS.length; i++) {
    if (DEFAULT_STEPS[i].statuses.includes(upper)) {
      return i;
    }
  }
  return -1;
}

/**
 * Determine per-step visual states using both `status` (lifecycle) and
 * `current_stage` (which node is active / where failure occurred).
 */
function computeStepStates(
  status: string,
  currentStage: string | null | undefined,
) {
  const normStatus = status.toUpperCase() as WorkflowStatus;
  const isFailed = normStatus === 'FAILED';
  const isRejected = normStatus === 'REJECTED';
  const isTerminalSuccess = ['APPROVED', 'PUBLISHED', 'COMPLETED'].includes(normStatus);
  const isWaitingForReview = normStatus === 'WAITING_FOR_HUMAN_REVIEW' || normStatus === 'HUMAN_REVIEW';

  // Determine which step index the current_stage maps to
  const stage = currentStage || status;
  let activeIndex = stageToStepIndex(stage);

  // Fallback: if current_stage doesn't map, use status directly
  if (activeIndex < 0) {
    activeIndex = stageToStepIndex(status);
  }
  // Final fallback to step 0
  if (activeIndex < 0) {
    activeIndex = 0;
  }

  return DEFAULT_STEPS.map((_step, idx) => {
    if (isFailed) {
      // For FAILED workflows: steps before the failed stage are completed,
      // the failed stage itself shows as failed, steps after are pending.
      if (idx < activeIndex) return 'completed';
      if (idx === activeIndex) return 'failed';
      return 'pending';
    }

    if (isRejected) {
      // Rejected at the review stage (step 4 = review)
      if (idx < 4) return 'completed';
      if (idx === 4) return 'failed';
      return 'pending';
    }

    if (isTerminalSuccess) {
      // All steps are completed for successful terminal states
      return 'completed';
    }

    if (isWaitingForReview) {
      // Steps before review are completed, review step is waiting
      if (idx < 4) return 'completed';
      if (idx === 4) return 'waiting';
      return 'pending';
    }

    // Active workflow: steps before active are completed, active step is running, rest pending
    if (idx < activeIndex) return 'completed';
    if (idx === activeIndex) return 'active';
    return 'pending';
  });
}

/** Compute a subtitle/description for each step based on its visual state. */
function getStepSubtitle(
  stepState: string,
  stepId: string,
  errorMessage: string | null | undefined,
  revisionCount?: number,
): string {
  switch (stepState) {
    case 'completed':
      if (stepId === 'done') return 'Post published successfully.';
      return 'Completed';
    case 'active':
      if (stepId === 'research') return 'Searching current trends and sources...';
      if (stepId === 'planning') return 'Selecting topic, angle and content strategy...';
      if (stepId === 'writing') {
        return revisionCount && revisionCount > 0
          ? 'Writer Agent — Revising content...'
          : 'Generating platform-specific content...';
      }
      if (stepId === 'critic') return 'Checking quality, relevance and platform constraints...';
      if (stepId === 'review') return 'Waiting for your approval, revision or rejection...';
      if (stepId === 'done') return 'Publishing...';
      return 'Processing...';
    case 'waiting':
      if (stepId === 'review') return 'Waiting for your approval, revision or rejection...';
      return 'Waiting for human review';
    case 'failed':
      return errorMessage ? 'Failed' : 'Failed';
    case 'pending':
    default:
      return 'Waiting';
  }
}

export interface StepperProps {
  currentStatus: WorkflowStatus | string;
  currentStage?: string | null;
  errorMessage?: string | null;
  revisionCount?: number;
}

export const Stepper: React.FC<StepperProps> = ({ currentStatus, currentStage, errorMessage, revisionCount }) => {
  const stepStates = computeStepStates(currentStatus, currentStage);

  // Find active/failed step index for progress bar
  let progressIndex = 0;
  for (let i = DEFAULT_STEPS.length - 1; i >= 0; i--) {
    if (stepStates[i] === 'completed' || stepStates[i] === 'active' || stepStates[i] === 'waiting' || stepStates[i] === 'failed') {
      progressIndex = i;
      break;
    }
  }

  const hasFailed = stepStates.includes('failed');

  return (
    <div className="stepper-container" aria-label="Workflow progress steps">
      {/* Background track */}
      <div
        style={{
          position: 'absolute',
          top: '19px',
          left: '30px',
          right: '30px',
          height: '2px',
          background: 'var(--border-default)',
          zIndex: 1,
        }}
      />
      {/* Progress fill */}
      <div
        style={{
          position: 'absolute',
          top: '19px',
          left: '30px',
          width: `${(progressIndex / (DEFAULT_STEPS.length - 1)) * 100}%`,
          height: '2px',
          background: hasFailed ? 'var(--error)' : 'var(--accent-primary)',
          transition: 'width var(--transition-normal)',
          zIndex: 1,
        }}
      />
      {DEFAULT_STEPS.map((step, idx) => {
        const state = stepStates[idx];
        const subtitle = getStepSubtitle(state, step.id, errorMessage, revisionCount);

        let stepClass = 'stepper-step';
        if (state === 'completed') stepClass += ' completed';
        if (state === 'active') stepClass += ' active';
        if (state === 'failed') stepClass += ' failed';
        if (state === 'waiting') stepClass += ' waiting';

        return (
          <div key={step.id} className={stepClass}>
            <div className="stepper-circle">
              {state === 'completed' ? (
                <Check size={18} strokeWidth={3} />
              ) : state === 'active' ? (
                <Loader2 size={18} style={{ animation: 'pulse 1s linear infinite' }} />
              ) : state === 'failed' ? (
                <XCircle size={16} />
              ) : state === 'waiting' ? (
                <Clock size={16} />
              ) : (
                idx + 1
              )}
            </div>
            <span className="stepper-label">{step.label}</span>
            <span className="stepper-subtitle">{subtitle}</span>
            {state === 'failed' && errorMessage && (
              <div className="stepper-error" title={errorMessage}>
                <AlertTriangle size={12} />
                <span>{errorMessage.length > 80 ? errorMessage.substring(0, 80) + '…' : errorMessage}</span>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
};
