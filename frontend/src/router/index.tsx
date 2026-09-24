import React from 'react';
import { Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { AppLayout } from '../components/layout/AppLayout';
import { LoadingSpinner } from '../components/ui/LoadingSpinner';

// Pages
import { LoginPage } from '../pages/auth/LoginPage';
import { RegisterPage } from '../pages/auth/RegisterPage';
import { DashboardPage } from '../pages/dashboard/DashboardPage';
import { WorkflowListPage } from '../pages/workflows/WorkflowListPage';
import { WorkflowCreatePage } from '../pages/workflows/WorkflowCreatePage';
import { WorkflowDetailPage } from '../pages/workflows/WorkflowDetailPage';
import { HITLReviewPage } from '../pages/review/HITLReviewPage';
import { SchedulesPage } from '../pages/schedules/SchedulesPage';
import { CredentialsPage } from '../pages/credentials/CredentialsPage';
import { SettingsPage } from '../pages/settings/SettingsPage';
import { NotFoundPage } from '../pages/NotFoundPage';

export const ProtectedRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { isAuthenticated, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <LoadingSpinner message="Authenticating session..." />
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return <>{children}</>;
};

export const PublicRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { isAuthenticated, isLoading } = useAuth();

  if (isLoading) {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <LoadingSpinner message="Checking session..." />
      </div>
    );
  }

  if (isAuthenticated) {
    return <Navigate to="/dashboard" replace />;
  }

  return <>{children}</>;
};

export const AppRoutes: React.FC = () => {
  return (
    <Routes>
      {/* Public Routes */}
      <Route
        path="/login"
        element={
          <PublicRoute>
            <LoginPage />
          </PublicRoute>
        }
      />
      <Route
        path="/register"
        element={
          <PublicRoute>
            <RegisterPage />
          </PublicRoute>
        }
      />

      {/* Protected Layout Routes */}
      <Route
        path="/"
        element={
          <ProtectedRoute>
            <AppLayout />
          </ProtectedRoute>
        }
      >
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="dashboard" element={<DashboardPage />} />
        <Route path="workflows" element={<WorkflowListPage />} />
        <Route path="workflows/new" element={<WorkflowCreatePage />} />
        <Route path="workflows/:id" element={<WorkflowDetailPage />} />
        <Route path="review" element={<HITLReviewPage />} />
        <Route path="review/:id" element={<HITLReviewPage />} />
        <Route path="schedules" element={<SchedulesPage />} />
        <Route path="credentials" element={<CredentialsPage />} />
        <Route path="settings" element={<SettingsPage />} />
      </Route>

      {/* Catch-all 404 */}
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
};
