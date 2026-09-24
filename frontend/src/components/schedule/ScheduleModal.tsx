import React, { useState } from 'react';
import { Modal } from '../ui/Modal';
import { Button } from '../ui/Button';
import { Input } from '../ui/Input';
import { Select } from '../ui/Select';
import { Calendar, Clock, Globe } from 'lucide-react';
import { format, addHours } from 'date-fns';

export interface ScheduleModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSchedule: (scheduledAt: string, timezone: string, platform?: string) => Promise<void>;
  defaultPlatform?: string;
  isLoading?: boolean;
}

export const ScheduleModal: React.FC<ScheduleModalProps> = ({
  isOpen,
  onClose,
  onSchedule,
  defaultPlatform = 'linkedin',
  isLoading = false,
}) => {
  // Default to 2 hours in the future
  const defaultFutureDate = format(addHours(new Date(), 2), "yyyy-MM-dd'T'HH:mm");

  const [datetime, setDatetime] = useState(defaultFutureDate);
  const [timezone, setTimezone] = useState(
    Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
  );
  const [platform, setPlatform] = useState(defaultPlatform);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!datetime) {
      setError('Please select a scheduled execution time.');
      return;
    }

    const selectedTime = new Date(datetime);
    if (selectedTime.getTime() <= Date.now()) {
      setError('Scheduled time must be in the future.');
      return;
    }

    setError(null);
    await onSchedule(selectedTime.toISOString(), timezone, platform);
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Schedule Post for Future Publication"
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={isLoading}>
            Cancel
          </Button>
          <Button
            variant="primary"
            onClick={handleSubmit}
            isLoading={isLoading}
            leftIcon={<Clock size={16} />}
          >
            Confirm Schedule
          </Button>
        </>
      }
    >
      <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
        <Input
          label="Execution Date & Time"
          type="datetime-local"
          value={datetime}
          onChange={(e) => setDatetime(e.target.value)}
          error={error || undefined}
          leftIcon={<Calendar size={18} />}
          required
        />

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-4)' }}>
          <Select
            label="Target Platform"
            value={platform}
            onChange={(e) => setPlatform(e.target.value)}
            options={[
              { label: 'LinkedIn', value: 'linkedin' },
              { label: 'Twitter / X', value: 'twitter' },
            ]}
          />

          <Input
            label="Timezone"
            value={timezone}
            onChange={(e) => setTimezone(e.target.value)}
            leftIcon={<Globe size={18} />}
          />
        </div>

        <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>
          The APScheduler engine will trigger the publication job precisely at the configured timestamp.
        </p>
      </form>
    </Modal>
  );
};
