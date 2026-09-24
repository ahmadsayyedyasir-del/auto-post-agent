import React from 'react';

export interface LoadingSpinnerProps {
  message?: string;
  size?: 'sm' | 'md' | 'lg';
}

export const LoadingSpinner: React.FC<LoadingSpinnerProps> = ({
  message = 'Loading...',
  size = 'md',
}) => {
  const pixelSize = size === 'sm' ? 24 : size === 'lg' ? 48 : 36;

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 'var(--space-12) var(--space-4)',
        gap: 'var(--space-4)',
        color: 'var(--text-secondary)',
      }}
      role="status"
    >
      <div
        style={{
          width: `${pixelSize}px`,
          height: `${pixelSize}px`,
          border: '3px solid var(--border-default)',
          borderTopColor: 'var(--accent-primary)',
          borderRadius: '50%',
          animation: 'pulse 1s linear infinite',
        }}
      />
      {message && <span style={{ fontSize: '0.9rem', fontWeight: 500 }}>{message}</span>}
    </div>
  );
};
