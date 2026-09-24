import React from 'react';
import { ScheduleResponse } from '../../types';
import { Card } from '../ui/Card';
import { StatusBadge } from '../ui/StatusBadge';
import { Button } from '../ui/Button';
import { Calendar, Clock, Globe, Play, XCircle, AlertCircle, Linkedin, Twitter } from 'lucide-react';
import { format, parseISO } from 'date-fns';

export interface ScheduleCardProps {
  schedule: ScheduleResponse;
  onRunNow?: (scheduleId: string) => void;
  onCancel?: (scheduleId: string) => void;
  isActionLoading?: boolean;
}

export const ScheduleCard: React.FC<ScheduleCardProps> = ({
  schedule,
  onRunNow,
  onCancel,
  isActionLoading = false,
}) => {
  let formattedDate = schedule.scheduled_at;
  try {
    formattedDate = format(parseISO(schedule.scheduled_at), 'PPP pp');
  } catch {
    // Keep raw if unparseable
  }

  const isPending = schedule.status === 'SCHEDULED';
  const isFailed = schedule.status === 'FAILED';

  return (
    <Card
      header={
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
            {schedule.platform.toLowerCase() === 'linkedin' ? (
              <Linkedin size={18} color="#0a66c2" />
            ) : (
              <Twitter size={18} color="#1d9bf0" />
            )}
            <span style={{ fontWeight: 700, fontSize: '0.95rem', textTransform: 'capitalize' }}>
              {schedule.platform} Job
            </span>
          </div>
          <StatusBadge status={schedule.status} />
        </div>
      }
      footer={
        isPending && (onRunNow || onCancel) ? (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 'var(--space-3)' }}>
            {onCancel && (
              <Button
                size="sm"
                variant="danger"
                onClick={() => onCancel(schedule.id)}
                disabled={isActionLoading}
                leftIcon={<XCircle size={14} />}
              >
                Cancel Schedule
              </Button>
            )}
            {onRunNow && (
              <Button
                size="sm"
                variant="success"
                onClick={() => onRunNow(schedule.id)}
                isLoading={isActionLoading}
                leftIcon={<Play size={14} />}
              >
                Run Immediately
              </Button>
            )}
          </div>
        ) : undefined
      }
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', fontSize: '0.9rem' }}>
          <Calendar size={16} color="var(--accent-light)" />
          <span>
            <strong>Scheduled For:</strong> {formattedDate}
          </span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', fontSize: '0.85rem', color: 'var(--text-muted)' }}>
          <Globe size={14} />
          <span>Timezone: {schedule.timezone}</span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', fontSize: '0.85rem', color: 'var(--text-muted)' }}>
          <Clock size={14} />
          <span>Attempts: {schedule.attempt_count}</span>
        </div>

        {isFailed && schedule.last_error && (
          <div
            style={{
              background: 'var(--error-bg)',
              border: '1px solid var(--error-border)',
              borderRadius: 'var(--radius-sm)',
              padding: 'var(--space-3)',
              color: 'var(--error)',
              fontSize: '0.85rem',
              display: 'flex',
              alignItems: 'flex-start',
              gap: 'var(--space-2)',
            }}
          >
            <AlertCircle size={16} style={{ flexShrink: 0, marginTop: '2px' }} />
            <span>{schedule.last_error}</span>
          </div>
        )}
      </div>
    </Card>
  );
};
