import React, { useState, FormEvent } from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../context/ToastContext';
import { Card } from '../../components/ui/Card';
import { Input } from '../../components/ui/Input';
import { Button } from '../../components/ui/Button';
import { Bot, Mail, Lock, LogIn } from 'lucide-react';

export const LoginPage: React.FC = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { login } = useAuth();
  const { success } = useToast();
  const navigate = useNavigate();
  const location = useLocation();

  const from = (location.state as { from?: { pathname: string } })?.from?.pathname || '/dashboard';

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!email.trim() || !password.trim()) {
      setError('Please enter your email and password.');
      return;
    }

    setError(null);
    setIsLoading(true);

    try {
      await login({ email: email.trim(), password });
      success('Welcome back! Authentication successful.');
      navigate(from, { replace: true });
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Invalid email or password. Please try again.';
      setError(msg);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 'var(--space-4)',
        background: 'radial-gradient(ellipse at top, #1a233a 0%, #0a0e17 70%)',
      }}
    >
      <div style={{ maxWidth: 440, width: '100%' }}>
        <div style={{ textAlign: 'center', marginBottom: 'var(--space-6)' }}>
          <div
            style={{
              width: 52,
              height: 52,
              borderRadius: 'var(--radius-lg)',
              background: 'linear-gradient(135deg, var(--accent-primary), var(--info))',
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#fff',
              boxShadow: 'var(--shadow-glow)',
              marginBottom: 'var(--space-3)',
            }}
          >
            <Bot size={30} />
          </div>
          <h1 style={{ fontSize: '1.6rem', fontWeight: 800, letterSpacing: '-0.02em' }}>
            AutoPost AI Agent
          </h1>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', marginTop: 'var(--space-1)' }}>
            Sign in to access your multi-agent social automation studio
          </p>
        </div>

        <Card glass>
          <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
            {error && (
              <div
                style={{
                  background: 'var(--error-bg)',
                  border: '1px solid var(--error-border)',
                  color: 'var(--error)',
                  padding: 'var(--space-3)',
                  borderRadius: 'var(--radius-md)',
                  fontSize: '0.875rem',
                }}
                role="alert"
              >
                {error}
              </div>
            )}

            <Input
              label="Email Address"
              type="email"
              placeholder="you@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              leftIcon={<Mail size={18} />}
              required
            />

            <Input
              label="Password"
              type="password"
              placeholder="••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              leftIcon={<Lock size={18} />}
              required
            />

            <Button
              type="submit"
              variant="primary"
              isLoading={isLoading}
              leftIcon={<LogIn size={18} />}
              style={{ width: '100%', marginTop: 'var(--space-2)' }}
            >
              Sign In
            </Button>
          </form>

          <div
            style={{
              marginTop: 'var(--space-6)',
              paddingTop: 'var(--space-4)',
              borderTop: '1px solid var(--border-subtle)',
              textAlign: 'center',
              fontSize: '0.875rem',
              color: 'var(--text-secondary)',
            }}
          >
            Don't have an account?{' '}
            <Link to="/register" style={{ fontWeight: 600, color: 'var(--accent-light)' }}>
              Create an account
            </Link>
          </div>
        </Card>
      </div>
    </div>
  );
};
