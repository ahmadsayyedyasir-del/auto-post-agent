import React from 'react';
import { CredentialMetadata } from '../../types';
import { Card } from '../ui/Card';
import { Badge } from '../ui/Badge';
import { Button } from '../ui/Button';
import { KeyRound, Trash2, Plus, Linkedin, Twitter, CheckCircle2, AlertCircle } from 'lucide-react';
import { format, parseISO } from 'date-fns';

export interface CredentialCardProps {
  platform: string;
  credentials: CredentialMetadata[];
  onAdd: (platform: string) => void;
  onDelete: (platform: string, credentialKey: string) => void;
  isDeleting?: boolean;
}

export const CredentialCard: React.FC<CredentialCardProps> = ({
  platform,
  credentials,
  onAdd,
  onDelete,
  isDeleting = false,
}) => {
  const isConnected = credentials.length > 0;
  const isLinkedIn = platform.toLowerCase() === 'linkedin';

  return (
    <Card
      header={
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)' }}>
            <div
              style={{
                width: 36,
                height: 36,
                borderRadius: 'var(--radius-md)',
                background: isLinkedIn ? 'rgba(10, 102, 194, 0.15)' : 'rgba(29, 155, 240, 0.15)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              {isLinkedIn ? <Linkedin size={20} color="#0a66c2" /> : <Twitter size={20} color="#1d9bf0" />}
            </div>
            <div>
              <div style={{ fontWeight: 700, fontSize: '1rem', textTransform: 'capitalize' }}>
                {platform}
              </div>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                {isConnected ? `${credentials.length} keys configured` : 'Not configured'}
              </div>
            </div>
          </div>
          <Badge variant={isConnected ? 'success' : 'default'} icon={isConnected ? <CheckCircle2 size={12} /> : <AlertCircle size={12} />}>
            {isConnected ? 'CONNECTED' : 'DISCONNECTED'}
          </Badge>
        </div>
      }
      footer={
        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <Button
            size="sm"
            variant="secondary"
            onClick={() => onAdd(platform)}
            leftIcon={<Plus size={14} />}
          >
            Add / Update Key
          </Button>
        </div>
      }
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
        {credentials.length === 0 ? (
          <p style={{ color: 'var(--text-muted)', fontSize: '0.875rem' }}>
            No credentials stored for {platform}. Add your API access token or client credentials to enable direct publishing.
          </p>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
            {credentials.map((cred) => {
              let updatedStr = cred.updated_at;
              try {
                updatedStr = format(parseISO(cred.updated_at), 'PPP');
              } catch {
                // keep raw
              }

              return (
                <div
                  key={cred.id}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: 'var(--space-3)',
                    background: 'var(--bg-tertiary)',
                    borderRadius: 'var(--radius-sm)',
                    border: '1px solid var(--border-subtle)',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
                    <KeyRound size={15} color="var(--accent-light)" />
                    <div>
                      <div style={{ fontSize: '0.875rem', fontWeight: 600 }}>{cred.credential_key}</div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                        Updated: {updatedStr}
                      </div>
                    </div>
                  </div>
                  <button
                    onClick={() => onDelete(cred.platform, cred.credential_key)}
                    disabled={isDeleting}
                    style={{
                      background: 'none',
                      border: 'none',
                      color: 'var(--error)',
                      cursor: 'pointer',
                      padding: '4px',
                      borderRadius: 'var(--radius-sm)',
                    }}
                    title={`Delete ${cred.credential_key}`}
                    aria-label={`Delete ${cred.credential_key}`}
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </Card>
  );
};
