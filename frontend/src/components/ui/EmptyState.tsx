import React, { ReactNode } from 'react';
import { Inbox, AlertTriangle } from 'lucide-react';
import { Button } from './Button';

export interface EmptyStateProps {
  title?: string;
  description?: string;
  icon?: ReactNode;
  action?: {
    label: string;
    onClick: () => void;
  };
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  title = 'No items found',
  description = 'Get started by creating a new entry.',
  icon,
  action,
}) => {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 'var(--space-12) var(--space-6)',
        textAlign: 'center',
        background: 'var(--bg-secondary)',
        border: '1px dashed var(--border-default)',
        borderRadius: 'var(--radius-lg)',
        gap: 'var(--space-3)',
      }}
    >
      <div
        style={{
          width: 52,
          height: 52,
          borderRadius: 'var(--radius-full)',
          background: 'var(--bg-tertiary)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: 'var(--text-muted)',
          marginBottom: 'var(--space-2)',
        }}
      >
        {icon || <Inbox size={26} />}
      </div>
      <h3 style={{ fontSize: '1.1rem', fontWeight: 600, color: 'var(--text-primary)' }}>
        {title}
      </h3>
      <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', maxWidth: '400px' }}>
        {description}
      </p>
      {action && (
        <div style={{ marginTop: 'var(--space-3)' }}>
          <Button onClick={action.onClick} variant="primary">
            {action.label}
          </Button>
        </div>
      )}
    </div>
  );
};

export interface ErrorStateProps {
  title?: string;
  message?: string;
  onRetry?: () => void;
}

export const ErrorState: React.FC<ErrorStateProps> = ({
  title = 'Something went wrong',
  message = 'Failed to load information from the server.',
  onRetry,
}) => {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 'var(--space-10) var(--space-6)',
        textAlign: 'center',
        background: 'var(--error-bg)',
        border: '1px solid var(--error-border)',
        borderRadius: 'var(--radius-lg)',
        gap: 'var(--space-3)',
      }}
      role="alert"
    >
      <div
        style={{
          width: 48,
          height: 48,
          borderRadius: 'var(--radius-full)',
          background: 'rgba(239, 68, 68, 0.2)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: 'var(--error)',
        }}
      >
        <AlertTriangle size={24} />
      </div>
      <h3 style={{ fontSize: '1.05rem', fontWeight: 600, color: 'var(--error)' }}>
        {title}
      </h3>
      <p style={{ color: 'var(--text-secondary)', fontSize: '0.875rem', maxWidth: '420px' }}>
        {message}
      </p>
      {onRetry && (
        <Button onClick={onRetry} variant="secondary" size="sm" style={{ marginTop: 'var(--space-2)' }}>
          Try Again
        </Button>
      )}
    </div>
  );
};
