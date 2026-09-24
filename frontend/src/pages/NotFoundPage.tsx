import React from 'react';
import { Link } from 'react-router-dom';
import { Button } from '../components/ui/Button';
import { Bot, Home } from 'lucide-react';

export const NotFoundPage: React.FC = () => {
  return (
    <div
      style={{
        minHeight: '70vh',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        textAlign: 'center',
        padding: 'var(--space-8)',
        gap: 'var(--space-4)',
      }}
    >
      <div
        style={{
          width: 64,
          height: 64,
          borderRadius: 'var(--radius-full)',
          background: 'var(--bg-tertiary)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: 'var(--text-muted)',
        }}
      >
        <Bot size={34} />
      </div>
      <h1 style={{ fontSize: '2.5rem', fontWeight: 800 }}>404</h1>
      <h2 style={{ fontSize: '1.25rem', fontWeight: 700 }}>Page Not Found</h2>
      <p style={{ color: 'var(--text-secondary)', maxWidth: 420 }}>
        The requested view or workflow route does not exist or you do not have permission to view it.
      </p>
      <Link to="/dashboard" style={{ marginTop: 'var(--space-2)' }}>
        <Button variant="primary" leftIcon={<Home size={16} />}>
          Return to Dashboard
        </Button>
      </Link>
    </div>
  );
};
