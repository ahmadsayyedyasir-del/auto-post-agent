import React, { useState } from 'react';
import { Modal } from '../ui/Modal';
import { Button } from '../ui/Button';
import { Select } from '../ui/Select';
import { Send, AlertTriangle } from 'lucide-react';

export interface PublishModalProps {
  isOpen: boolean;
  onClose: () => void;
  onPublish: (platformOverride?: string) => Promise<void>;
  defaultPlatform: string;
  isLoading?: boolean;
}

export const PublishModal: React.FC<PublishModalProps> = ({
  isOpen,
  onClose,
  onPublish,
  defaultPlatform,
  isLoading = false,
}) => {
  const [platform, setPlatform] = useState(defaultPlatform);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    await onPublish(platform !== defaultPlatform ? platform : undefined);
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Publish Approved Social Post"
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={isLoading}>
            Cancel
          </Button>
          <Button
            variant="success"
            onClick={handleSubmit}
            isLoading={isLoading}
            leftIcon={<Send size={16} />}
          >
            Confirm & Publish Now
          </Button>
        </>
      }
    >
      <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.925rem', lineHeight: 1.5 }}>
          This will immediately dispatch the approved content to your connected social media account
          using your encrypted credentials.
        </p>

        <Select
          label="Target Destination Platform"
          value={platform}
          onChange={(e) => setPlatform(e.target.value)}
          options={[
            { label: 'LinkedIn (Official API)', value: 'linkedin' },
            { label: 'Twitter / X', value: 'twitter' },
          ]}
        />

        <div
          style={{
            background: 'var(--bg-tertiary)',
            border: '1px solid var(--border-default)',
            borderRadius: 'var(--radius-md)',
            padding: 'var(--space-3)',
            display: 'flex',
            alignItems: 'flex-start',
            gap: 'var(--space-2)',
            fontSize: '0.85rem',
            color: 'var(--text-muted)',
          }}
        >
          <AlertTriangle size={18} color="var(--warning)" style={{ flexShrink: 0, marginTop: '2px' }} />
          <span>
            Publishing is idempotent. If a duplicate request is dispatched, the system guarantees only a
            single post will be published.
          </span>
        </div>
      </form>
    </Modal>
  );
};
