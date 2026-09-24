import React, { useState } from 'react';
import { Modal } from '../ui/Modal';
import { Button } from '../ui/Button';
import { Input } from '../ui/Input';
import { Select } from '../ui/Select';
import { KeyRound, ShieldAlert } from 'lucide-react';
import { UpsertCredentialRequest } from '../../types';

export interface CredentialModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSave: (data: UpsertCredentialRequest) => Promise<void>;
  initialPlatform?: string;
  isLoading?: boolean;
}

export const CredentialModal: React.FC<CredentialModalProps> = ({
  isOpen,
  onClose,
  onSave,
  initialPlatform = 'linkedin',
  isLoading = false,
}) => {
  const [platform, setPlatform] = useState(initialPlatform);
  const [credentialKey, setCredentialKey] = useState('access_token');
  const [credentialValue, setCredentialValue] = useState('');
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!credentialValue.trim()) {
      setError('Please provide the credential value/token.');
      return;
    }
    setError(null);

    await onSave({
      platform: platform.trim().toLowerCase(),
      credential_key: credentialKey.trim(),
      credential_value: credentialValue.trim(),
    });

    setCredentialValue('');
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Store Platform Credential"
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={isLoading}>
            Cancel
          </Button>
          <Button
            variant="primary"
            onClick={handleSubmit}
            isLoading={isLoading}
            leftIcon={<KeyRound size={16} />}
          >
            Save Encrypted Credential
          </Button>
        </>
      }
    >
      <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
        <Select
          label="Platform"
          value={platform}
          onChange={(e) => setPlatform(e.target.value)}
          options={[
            { label: 'LinkedIn', value: 'linkedin' },
            { label: 'Twitter / X', value: 'twitter' },
          ]}
        />

        <Select
          label="Credential Key Name"
          value={credentialKey}
          onChange={(e) => setCredentialKey(e.target.value)}
          options={[
            { label: 'Access Token (access_token)', value: 'access_token' },
            { label: 'Author URN (author_urn)', value: 'author_urn' },
            { label: 'Client ID (client_id)', value: 'client_id' },
            { label: 'Client Secret (client_secret)', value: 'client_secret' },
          ]}
        />

        <Input
          label="Secret Token / Key Value"
          type="password"
          placeholder="Paste secret token value..."
          value={credentialValue}
          onChange={(e) => setCredentialValue(e.target.value)}
          error={error || undefined}
          helperText="The value is encrypted with Fernet symmetric encryption before database storage."
          required
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
          <ShieldAlert size={18} color="var(--info)" style={{ flexShrink: 0, marginTop: '2px' }} />
          <span>
            Plaintext secrets are never returned in API responses or visible in client state after submission.
          </span>
        </div>
      </form>
    </Modal>
  );
};
