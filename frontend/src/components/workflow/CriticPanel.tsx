import React from 'react';
import { FeedbackResponse } from '../../types';
import { Card } from '../ui/Card';
import { Badge } from '../ui/Badge';
import { ShieldCheck, AlertCircle, CheckCircle, Info } from 'lucide-react';

export interface CriticPanelProps {
  feedbacks: FeedbackResponse[];
}

export const CriticPanel: React.FC<CriticPanelProps> = ({ feedbacks }) => {
  if (!feedbacks || feedbacks.length === 0) {
    return (
      <Card header={<h3 style={{ fontSize: '0.95rem', fontWeight: 700 }}>Critic Evaluation Report</h3>}>
        <div style={{ color: 'var(--text-muted)', fontSize: '0.875rem' }}>
          No evaluations recorded yet.
        </div>
      </Card>
    );
  }

  const latestFeedback = feedbacks[feedbacks.length - 1];
  const isApproved = latestFeedback.decision.toUpperCase() === 'APPROVED';

  return (
    <Card
      header={
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
            <ShieldCheck size={18} color={isApproved ? 'var(--success)' : 'var(--warning)'} />
            <span style={{ fontWeight: 700, fontSize: '0.95rem' }}>Critic Evaluation Report</span>
          </div>
          <Badge variant={isApproved ? 'success' : 'warning'}>
            {latestFeedback.decision}
          </Badge>
        </div>
      }
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
        {/* Reviewer / Source Info */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-4)', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
          <span>Source: <strong>{latestFeedback.feedback_source}</strong></span>
        </div>

        {/* Quality issues if any */}
        {latestFeedback.issues && latestFeedback.issues.length > 0 && (
          <div>
            <div style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--warning)', marginBottom: 'var(--space-2)', display: 'flex', alignItems: 'center', gap: 'var(--space-1)' }}>
              <AlertCircle size={15} />
              <span>Identified Issues:</span>
            </div>
            <ul style={{ paddingLeft: 'var(--space-4)', display: 'flex', flexDirection: 'column', gap: 'var(--space-1)', fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
              {latestFeedback.issues.map((issue, idx) => (
                <li key={idx}>{issue}</li>
              ))}
            </ul>
          </div>
        )}

        {/* Feedback items / instructions */}
        {latestFeedback.feedback_items && latestFeedback.feedback_items.length > 0 && (
          <div>
            <div style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--info)', marginBottom: 'var(--space-2)', display: 'flex', alignItems: 'center', gap: 'var(--space-1)' }}>
              <Info size={15} />
              <span>Revision Instructions:</span>
            </div>
            <ul style={{ paddingLeft: 'var(--space-4)', display: 'flex', flexDirection: 'column', gap: 'var(--space-1)', fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
              {latestFeedback.feedback_items.map((item, idx) => (
                <li key={idx}>{item}</li>
              ))}
            </ul>
          </div>
        )}

        {/* Reviewer Notes */}
        {latestFeedback.reviewer_notes && (
          <div style={{ background: 'var(--bg-tertiary)', padding: 'var(--space-3)', borderRadius: 'var(--radius-sm)', fontSize: '0.85rem' }}>
            <strong>Reviewer Notes:</strong> {latestFeedback.reviewer_notes}
          </div>
        )}

        {isApproved && (!latestFeedback.issues || latestFeedback.issues.length === 0) && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', color: 'var(--success)', fontSize: '0.875rem' }}>
            <CheckCircle size={16} />
            <span>Passed all deterministic and LLM quality checks (length, compliance, tone, source grounding).</span>
          </div>
        )}
      </div>
    </Card>
  );
};
