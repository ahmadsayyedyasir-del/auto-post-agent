import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { AuthProvider } from '../src/context/AuthContext';
import { ToastProvider } from '../src/context/ToastContext';
import { LoginPage } from '../src/pages/auth/LoginPage';
import { RegisterPage } from '../src/pages/auth/RegisterPage';
import { ProtectedRoute } from '../src/router';
import { authService } from '../src/services/auth';

vi.mock('../src/services/auth', () => ({
  authService: {
    login: vi.fn(),
    register: vi.fn(),
    refresh: vi.fn(),
    logout: vi.fn(),
    getCurrentUser: vi.fn(),
  },
}));

describe('Authentication Flows', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });

  it('renders Login page and handles successful authentication', async () => {
    vi.mocked(authService.login).mockResolvedValue({
      access_token: 'fake-access-token',
      refresh_token: 'fake-refresh-token',
      token_type: 'bearer',
      expires_in: 1800,
    });
    vi.mocked(authService.getCurrentUser).mockResolvedValue({
      id: 'user-123',
      email: 'alex@example.com',
      full_name: 'Alex Smith',
      is_active: true,
      is_superuser: false,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    });

    render(
      <MemoryRouter initialEntries={['/login']}>
        <ToastProvider>
          <AuthProvider>
            <LoginPage />
          </AuthProvider>
        </ToastProvider>
      </MemoryRouter>
    );

    expect(screen.getByLabelText(/email address/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/email address/i), {
      target: { value: 'alex@example.com' },
    });
    fireEvent.change(screen.getByLabelText(/password/i), {
      target: { value: 'password123' },
    });

    fireEvent.click(screen.getByRole('button', { name: /sign in/i }));

    await waitFor(() => {
      expect(authService.login).toHaveBeenCalledWith({
        email: 'alex@example.com',
        password: 'password123',
      });
    });
  });

  it('renders Register page and checks password mismatch validation', async () => {
    render(
      <MemoryRouter initialEntries={['/register']}>
        <ToastProvider>
          <AuthProvider>
            <RegisterPage />
          </AuthProvider>
        </ToastProvider>
      </MemoryRouter>
    );

    fireEvent.change(screen.getByLabelText(/email address/i), {
      target: { value: 'alex@example.com' },
    });
    fireEvent.change(screen.getByLabelText(/^password/i), {
      target: { value: 'password123' },
    });
    fireEvent.change(screen.getByLabelText(/confirm password/i), {
      target: { value: 'mismatchpass' },
    });

    fireEvent.click(screen.getByRole('button', { name: /complete registration/i }));

    expect(screen.getByText(/passwords do not match/i)).toBeInTheDocument();
    expect(authService.register).not.toHaveBeenCalled();
  });

  it('blocks unauthenticated access on ProtectedRoute and redirects to /login', async () => {
    vi.mocked(authService.refresh).mockRejectedValue(new Error('No session'));

    render(
      <MemoryRouter initialEntries={['/dashboard']}>
        <ToastProvider>
          <AuthProvider>
            <Routes>
              <Route
                path="/dashboard"
                element={
                  <ProtectedRoute>
                    <div>Secret Dashboard Content</div>
                  </ProtectedRoute>
                }
              />
              <Route path="/login" element={<div>Login Screen</div>} />
            </Routes>
          </AuthProvider>
        </ToastProvider>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText('Login Screen')).toBeInTheDocument();
      expect(screen.queryByText('Secret Dashboard Content')).not.toBeInTheDocument();
    });
  });
});
