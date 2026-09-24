import React from 'react';
import { Menu, Plus } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Button } from '../ui/Button';

export interface NavbarProps {
  onToggleSidebar: () => void;
}

export const Navbar: React.FC<NavbarProps> = ({ onToggleSidebar }) => {
  return (
    <header className="top-navbar">
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-4)' }}>
        <button
          className="mobile-menu-btn"
          onClick={onToggleSidebar}
          style={{
            background: 'none',
            border: 'none',
            color: 'var(--text-secondary)',
            cursor: 'pointer',
            padding: '6px',
            borderRadius: 'var(--radius-sm)',
          }}
          aria-label="Open navigation menu"
        >
          <Menu size={22} />
        </button>
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
          <span style={{ fontSize: '0.9rem', fontWeight: 600, color: 'var(--text-secondary)' }}>
            Workspace
          </span>
          <span style={{ color: 'var(--border-default)' }}>/</span>
          <span style={{ fontSize: '0.9rem', fontWeight: 700, color: 'var(--text-primary)' }}>
            Production Agent
          </span>
        </div>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)' }}>
        <Link to="/workflows/new">
          <Button size="sm" variant="primary" leftIcon={<Plus size={16} />}>
            New Workflow
          </Button>
        </Link>
      </div>
    </header>
  );
};
