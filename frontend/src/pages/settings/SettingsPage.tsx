import React from 'react';
import { useAuth } from '../../context/AuthContext';
import { Card } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { Badge } from '../../components/ui/Badge';
import { LogOut } from 'lucide-react';
import { format, parseISO } from 'date-fns';

export const SettingsPage: React.FC = () => {
  const { user, logout } = useAuth();

  let formattedDate = 'N/A';
  if (user?.created_at) {
    try {
      formattedDate = format(parseISO(user.created_at), 'PPP');
    } catch {
      formattedDate = user.created_at;
    }
  }

  return (
    <div style={{ maxWidth: 720, margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 'var(--space-6)' }}>
      <div>
        <h1 style={{ fontSize: '1.75rem', fontWeight: 800, letterSpacing: '-0.02em' }}>
          Account Settings & Profile
        </h1>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.925rem' }}>
          Manage your personal account profile and session preferences.
        </p>
      </div>

      <Card header={<h3 style={{ fontSize: '1.05rem', fontWeight: 700 }}>User Profile</h3>}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-4)' }}>
            <div
              style={{
                width: 56,
                height: 56,
                borderRadius: 'var(--radius-full)',
                background: 'linear-gradient(135deg, var(--accent-primary), var(--info))',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: '#fff',
                fontSize: '1.3rem',
                fontWeight: 800,
              }}
            >
              {user?.full_name ? user.full_name.charAt(0).toUpperCase() : user?.email.charAt(0).toUpperCase() || 'U'}
            </div>
            <div>
              <div style={{ fontSize: '1.15rem', fontWeight: 700 }}>{user?.full_name || 'User'}</div>
              <div style={{ color: 'var(--text-secondary)', fontSize: '0.875rem' }}>{user?.email}</div>
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 'var(--space-4)', marginTop: 'var(--space-2)' }}>
            <div style={{ background: 'var(--bg-tertiary)', padding: 'var(--space-3)', borderRadius: 'var(--radius-md)' }}>
              <div style={{ color: 'var(--text-muted)', fontSize: '0.75rem', fontWeight: 600 }}>ACCOUNT ID</div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8rem', marginTop: '2px' }}>{user?.id}</div>
            </div>

            <div style={{ background: 'var(--bg-tertiary)', padding: 'var(--space-3)', borderRadius: 'var(--radius-md)' }}>
              <div style={{ color: 'var(--text-muted)', fontSize: '0.75rem', fontWeight: 600 }}>ACCOUNT STATUS</div>
              <div style={{ marginTop: '2px' }}>
                <Badge variant={user?.is_active ? 'success' : 'error'}>
                  {user?.is_active ? 'ACTIVE' : 'INACTIVE'}
                </Badge>
              </div>
            </div>

            <div style={{ background: 'var(--bg-tertiary)', padding: 'var(--space-3)', borderRadius: 'var(--radius-md)' }}>
              <div style={{ color: 'var(--text-muted)', fontSize: '0.75rem', fontWeight: 600 }}>ROLE / PRIVILEGES</div>
              <div style={{ marginTop: '2px' }}>
                <Badge variant={user?.is_superuser ? 'warning' : 'info'}>
                  {user?.is_superuser ? 'SUPERUSER' : 'STANDARD USER'}
                </Badge>
              </div>
            </div>

            <div style={{ background: 'var(--bg-tertiary)', padding: 'var(--space-3)', borderRadius: 'var(--radius-md)' }}>
              <div style={{ color: 'var(--text-muted)', fontSize: '0.75rem', fontWeight: 600 }}>REGISTERED DATE</div>
              <div style={{ fontSize: '0.85rem', marginTop: '2px' }}>{formattedDate}</div>
            </div>
          </div>
        </div>
      </Card>

      <Card header={<h3 style={{ fontSize: '1.05rem', fontWeight: 700 }}>Security & Session</h3>}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div>
            <div style={{ fontWeight: 600, fontSize: '0.95rem' }}>Sign Out of Current Session</div>
            <div style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
              Invalidates your server-side refresh token and clears memory tokens.
            </div>
          </div>
          <Button variant="danger" size="sm" onClick={() => logout()} leftIcon={<LogOut size={16} />}>
            Sign Out
          </Button>
        </div>
      </Card>
    </div>
  );
};
