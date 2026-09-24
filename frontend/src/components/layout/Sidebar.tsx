import React from 'react';
import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  Sparkles,
  CheckSquare,
  Calendar,
  KeyRound,
  Settings,
  LogOut,
  Bot,
  X,
} from 'lucide-react';
import { useAuth } from '../../context/AuthContext';

export interface SidebarProps {
  isOpen: boolean;
  onClose: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({ isOpen, onClose }) => {
  const { user, logout } = useAuth();

  const navItems = [
    { to: '/dashboard', label: 'Dashboard', icon: <LayoutDashboard size={20} /> },
    { to: '/workflows', label: 'Workflows', icon: <Sparkles size={20} /> },
    { to: '/review', label: 'HITL Review', icon: <CheckSquare size={20} /> },
    { to: '/schedules', label: 'Schedules', icon: <Calendar size={20} /> },
    { to: '/credentials', label: 'Credentials', icon: <KeyRound size={20} /> },
    { to: '/settings', label: 'Settings', icon: <Settings size={20} /> },
  ];

  return (
    <aside className={`sidebar ${isOpen ? 'open' : ''}`} aria-label="Main navigation">
      <div className="sidebar-header">
        <div className="sidebar-logo">
          <Bot size={22} />
        </div>
        <div style={{ flex: 1 }}>
          <div className="sidebar-title">AutoPost AI</div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Multi-Agent Studio</div>
        </div>
        <button
          className="mobile-menu-btn"
          onClick={onClose}
          style={{
            background: 'none',
            border: 'none',
            color: 'var(--text-muted)',
            cursor: 'pointer',
            padding: '4px',
          }}
          aria-label="Close sidebar menu"
        >
          <X size={20} />
        </button>
      </div>

      <nav className="sidebar-nav">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
            onClick={onClose}
          >
            {item.icon}
            <span>{item.label}</span>
          </NavLink>
        ))}
      </nav>

      <div className="sidebar-footer">
        <div className="user-profile-badge">
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)', minWidth: 0 }}>
            <div className="user-avatar">
              {user?.full_name ? user.full_name.charAt(0).toUpperCase() : user?.email.charAt(0).toUpperCase() || 'U'}
            </div>
            <div style={{ minWidth: 0 }}>
              <div
                style={{
                  fontSize: '0.85rem',
                  fontWeight: 600,
                  color: 'var(--text-primary)',
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                }}
              >
                {user?.full_name || 'User'}
              </div>
              <div
                style={{
                  fontSize: '0.75rem',
                  color: 'var(--text-muted)',
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                }}
              >
                {user?.email}
              </div>
            </div>
          </div>
          <button
            onClick={() => logout()}
            style={{
              background: 'none',
              border: 'none',
              color: 'var(--text-muted)',
              cursor: 'pointer',
              padding: '6px',
              borderRadius: 'var(--radius-sm)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
            title="Logout"
            aria-label="Logout"
          >
            <LogOut size={18} />
          </button>
        </div>
      </div>
    </aside>
  );
};
