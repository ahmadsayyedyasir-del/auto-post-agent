import React, { useState, useEffect, useCallback } from 'react';
import { credentialService } from '../../services/credentials';
import { CredentialMetadata, UpsertCredentialRequest } from '../../types';
import { useToast } from '../../context/ToastContext';
import { CredentialCard } from '../../components/credentials/CredentialCard';
import { CredentialModal } from '../../components/credentials/CredentialModal';
import { ConfirmDialog } from '../../components/ui/ConfirmDialog';
import { Button } from '../../components/ui/Button';
import { LoadingSpinner } from '../../components/ui/LoadingSpinner';
import { ErrorState } from '../../components/ui/ErrorState';
import { ShieldCheck, RefreshCw } from 'lucide-react';

const SUPPORTED_PLATFORMS = ['linkedin', 'twitter'];

export const CredentialsPage: React.FC = () => {
  const [credentials, setCredentials] = useState<CredentialMetadata[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Modals
  const [modalOpen, setModalOpen] = useState(false);
  const [selectedPlatform, setSelectedPlatform] = useState('linkedin');
  const [isSaving, setIsSaving] = useState(false);

  // Delete Dialog
  const [deleteTarget, setDeleteTarget] = useState<{ platform: string; key: string } | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  const { success, error: toastError } = useToast();

  const fetchCredentials = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const res = await credentialService.listCredentials();
      setCredentials(res.credentials || res.items || []);
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Failed to load platform credentials.';
      setError(msg);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchCredentials();
  }, [fetchCredentials]);

  const handleOpenAddModal = (platform: string) => {
    setSelectedPlatform(platform);
    setModalOpen(true);
  };

  const handleSaveCredential = async (data: UpsertCredentialRequest) => {
    setIsSaving(true);
    try {
      await credentialService.upsertCredential(data);
      success(`Successfully stored encrypted credential for ${data.platform}!`);
      setModalOpen(false);
      await fetchCredentials();
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Failed to save credential.';
      toastError(msg);
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    setIsDeleting(true);
    try {
      await credentialService.deleteCredential(deleteTarget.platform, deleteTarget.key);
      success(`Deleted credential ${deleteTarget.key} for ${deleteTarget.platform}.`);
      setDeleteTarget(null);
      await fetchCredentials();
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Failed to delete credential.';
      toastError(msg);
    } finally {
      setIsDeleting(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-6)' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 'var(--space-4)' }}>
        <div>
          <h1 style={{ fontSize: '1.75rem', fontWeight: 800, letterSpacing: '-0.02em' }}>
            Platform Credentials Vault
          </h1>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.925rem' }}>
            Configure and manage encrypted platform access tokens for automated publishing.
          </p>
        </div>
        <Button variant="secondary" size="sm" onClick={fetchCredentials} leftIcon={<RefreshCw size={14} />}>
          Refresh
        </Button>
      </div>

      {/* Security Architecture Banner */}
      <div
        style={{
          background: 'var(--bg-glass-card)',
          border: '1px solid var(--border-subtle)',
          borderRadius: 'var(--radius-lg)',
          padding: 'var(--space-5)',
          display: 'flex',
          alignItems: 'center',
          gap: 'var(--space-4)',
        }}
      >
        <div
          style={{
            width: 44,
            height: 44,
            borderRadius: 'var(--radius-md)',
            background: 'rgba(16, 185, 129, 0.15)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'var(--success)',
            flexShrink: 0,
          }}
        >
          <ShieldCheck size={24} />
        </div>
        <div style={{ fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
          <strong style={{ color: 'var(--text-primary)' }}>Encrypted At Rest:</strong> All platform tokens are
          encrypted with Fernet symmetric cryptography prior to database storage. Plaintext secrets are never
          logged, transmitted in error states, or exposed to the client interface.
        </div>
      </div>

      {isLoading ? (
        <LoadingSpinner message="Loading credentials vault..." />
      ) : error ? (
        <ErrorState message={error} onRetry={fetchCredentials} />
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(380px, 1fr))', gap: 'var(--space-6)' }}>
          {SUPPORTED_PLATFORMS.map((platform) => {
            const platformCreds = credentials.filter(
              (c) => c.platform.toLowerCase() === platform.toLowerCase()
            );
            return (
              <CredentialCard
                key={platform}
                platform={platform}
                credentials={platformCreds}
                onAdd={handleOpenAddModal}
                onDelete={(plat, key) => setDeleteTarget({ platform: plat, key })}
                isDeleting={isDeleting}
              />
            );
          })}
        </div>
      )}

      {/* Upsert Modal */}
      <CredentialModal
        isOpen={modalOpen}
        onClose={() => setModalOpen(false)}
        onSave={handleSaveCredential}
        initialPlatform={selectedPlatform}
        isLoading={isSaving}
      />

      {/* Delete Confirmation */}
      <ConfirmDialog
        isOpen={!!deleteTarget}
        onClose={() => setDeleteTarget(null)}
        onConfirm={handleDelete}
        title="Delete Platform Credential?"
        message={`Are you sure you want to remove ${deleteTarget?.key} for ${deleteTarget?.platform}? Automated publishing to this platform may fail until a new credential is provided.`}
        confirmLabel="Delete Credential"
        variant="danger"
        isLoading={isDeleting}
      />
    </div>
  );
};
