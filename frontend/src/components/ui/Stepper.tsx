import React from 'react';
import { WorkflowStatus } from '../../types';
import { Check, Loader2 } from 'lucide-react';

export interface StepperStep {
  id: string;
  label: string;
  statuses: WorkflowStatus[];
}

const DEFAULT_STEPS: StepperStep[] = [
  { id: 'research', label: 'Research', statuses: ['STARTING', 'RESEARCHING'] },
  { id: 'planning', label: 'Planning', statuses: ['PLANNING'] },
  { id: 'writing', label: 'Writing', statuses: ['WRITING'] },
  { id: 'critic', label: 'Critic', statuses: ['CRITIQUING'] },
  { id: 'review', label: 'Review', statuses: ['WAITING_FOR_HUMAN_REVIEW', 'HUMAN_REVIEW'] },
  { id: 'done', label: 'Published', statuses: ['APPROVED', 'PUBLISHED', 'COMPLETED'] },
];

export interface StepperProps {
  currentStatus: WorkflowStatus | string;
}

export const Stepper: React.FC<StepperProps> = ({ currentStatus }) => {
  const normStatus = currentStatus.toUpperCase() as WorkflowStatus;

  // Determine current active step index
  let activeIndex = 0;
  for (let i = 0; i < DEFAULT_STEPS.length; i++) {
    if (DEFAULT_STEPS[i].statuses.includes(normStatus)) {
      activeIndex = i;
      break;
    }
  }

  const isFailed = normStatus === 'FAILED' || normStatus === 'REJECTED';

  return (
    <div className="stepper-container" aria-label="Workflow progress steps">
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
      <div
        style={{
          position: 'absolute',
          top: '19px',
          left: '30px',
          width: `${(activeIndex / (DEFAULT_STEPS.length - 1)) * 100}%`,
          height: '2px',
          background: isFailed ? 'var(--error)' : 'var(--accent-primary)',
          transition: 'width var(--transition-normal)',
          zIndex: 1,
        }}
      />
      {DEFAULT_STEPS.map((step, idx) => {
        const isCompleted = idx < activeIndex;
        const isActive = idx === activeIndex && !isFailed;
        const isStepFailed = idx === activeIndex && isFailed;

        let stepClass = 'stepper-step';
        if (isCompleted) stepClass += ' completed';
        if (isActive) stepClass += ' active';
        if (isStepFailed) stepClass += ' failed';

        return (
          <div key={step.id} className={stepClass}>
            <div className="stepper-circle">
              {isCompleted ? (
                <Check size={18} strokeWidth={3} />
              ) : isActive ? (
                <Loader2 size={18} style={{ animation: 'pulse 1s linear infinite' }} />
              ) : isStepFailed ? (
                '!'
              ) : (
                idx + 1
              )}
            </div>
            <span className="stepper-label">{step.label}</span>
          </div>
        );
      })}
    </div>
  );
};
