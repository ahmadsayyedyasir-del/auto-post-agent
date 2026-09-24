import React, { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { workflowService } from '../../services/workflows';
import { scheduleService } from '../../services/schedules';
import { credentialService } from '../../services/credentials';
import { WorkflowDetailResponse, ScheduleResponse, CredentialMetadata } from '../../types';
import { Card } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { StatusBadge } from '../../components/ui/StatusBadge';
import { LoadingSpinner } from '../../components/ui/LoadingSpinner';
import { ErrorState } from '../../components/ui/ErrorState';
import { EmptyState } from '../../components/ui/EmptyState';
import {
  Sparkles,
  Eye,
  CheckCircle2,
  Calendar,
  KeyRound,
  ArrowRight,
  Plus,
  RefreshCw,
} from 'lucide-react';

export const DashboardPage: React.FC = () => {
  const [workflows, setWorkflows] = useState<WorkflowDetailResponse[]>([]);
  const [schedules, setSchedules] = useState<ScheduleResponse[]>([]);
  const [credentials, setCredentials] = useState<CredentialMetadata[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchDashboardData = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const [wfList, schedList, credList] = await Promise.all([
        workflowService.listWorkflows(),
        scheduleService.listSchedules(),
        credentialService.listCredentials(),
      ]);
      setWorkflows(wfList);
      setSchedules(schedList.schedules);
      setCredentials(credList.credentials || credList.items || []);
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Failed to load dashboard metrics. Please check your network connection.';
      setError(msg);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchDashboardData();
  }, [fetchDashboardData]);

  if (isLoading) {
    return <LoadingSpinner message="Loading workspace statistics..." />;
  }

  if (error) {
    return <ErrorState message={error} onRetry={fetchDashboardData} />;
  }

  const reviewCount = workflows.filter(
    (w) => w.status === 'WAITING_FOR_HUMAN_REVIEW' || w.status === 'HUMAN_REVIEW'
  ).length;
  const approvedCount = workflows.filter((w) => w.status === 'APPROVED' || w.status === 'PUBLISHED').length;
  const activeSchedulesCount = schedules.filter((s) => s.status === 'SCHEDULED').length;
  const connectedPlatforms = new Set(credentials.map((c) => c.platform.toLowerCase())).size;

  const recentWorkflows = workflows.slice(0, 5);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-8)' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 'var(--space-4)' }}>
        <div>
          <h1 style={{ fontSize: '1.75rem', fontWeight: 800, letterSpacing: '-0.02em' }}>
            Automation Dashboard
          </h1>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.925rem' }}>
            Overview of multi-agent content pipelines, review queues, and publishing schedules.
          </p>
        </div>
        <div style={{ display: 'flex', gap: 'var(--space-3)' }}>
          <Button variant="secondary" size="sm" onClick={fetchDashboardData} leftIcon={<RefreshCw size={14} />}>
            Refresh
          </Button>
          <Link to="/workflows/new">
            <Button variant="primary" size="sm" leftIcon={<Plus size={16} />}>
              Create Workflow
            </Button>
          </Link>
        </div>
      </div>

      {/* Metrics Row */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
          gap: 'var(--space-4)',
        }}
      >
        <Card>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span style={{ color: 'var(--text-muted)', fontSize: '0.85rem', fontWeight: 600 }}>TOTAL RUNS</span>
            <Sparkles size={18} color="var(--accent-light)" />
          </div>
          <div style={{ fontSize: '1.8rem', fontWeight: 800, marginTop: 'var(--space-2)' }}>
            {workflows.length}
          </div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: 'var(--space-1)' }}>
            Workflow executions initiated
          </div>
        </Card>

        <Card>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span style={{ color: 'var(--text-muted)', fontSize: '0.85rem', fontWeight: 600 }}>AWAITING REVIEW</span>
            <Eye size={18} color="var(--warning)" />
          </div>
          <div style={{ fontSize: '1.8rem', fontWeight: 800, marginTop: 'var(--space-2)', color: reviewCount > 0 ? 'var(--warning)' : undefined }}>
            {reviewCount}
          </div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: 'var(--space-1)' }}>
            Drafts paused for human review
          </div>
        </Card>

        <Card>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span style={{ color: 'var(--text-muted)', fontSize: '0.85rem', fontWeight: 600 }}>APPROVED / PUBLISHED</span>
            <CheckCircle2 size={18} color="var(--success)" />
          </div>
          <div style={{ fontSize: '1.8rem', fontWeight: 800, marginTop: 'var(--space-2)' }}>
            {approvedCount}
          </div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: 'var(--space-1)' }}>
            High-quality verified posts
          </div>
        </Card>

        <Card>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span style={{ color: 'var(--text-muted)', fontSize: '0.85rem', fontWeight: 600 }}>SCHEDULED JOBS</span>
            <Calendar size={18} color="var(--info)" />
          </div>
          <div style={{ fontSize: '1.8rem', fontWeight: 800, marginTop: 'var(--space-2)' }}>
            {activeSchedulesCount}
          </div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: 'var(--space-1)' }}>
            Active upcoming publication tasks
          </div>
        </Card>

        <Card>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span style={{ color: 'var(--text-muted)', fontSize: '0.85rem', fontWeight: 600 }}>PLATFORMS</span>
            <KeyRound size={18} color="var(--accent-light)" />
          </div>
          <div style={{ fontSize: '1.8rem', fontWeight: 800, marginTop: 'var(--space-2)' }}>
            {connectedPlatforms}
          </div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: 'var(--space-1)' }}>
            Connected credentials
          </div>
        </Card>
      </div>

      {/* Review Banner if items pending */}
      {reviewCount > 0 && (
        <div
          style={{
            background: 'var(--warning-bg)',
            border: '1px solid var(--warning-border)',
            borderRadius: 'var(--radius-lg)',
            padding: 'var(--space-5) var(--space-6)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: 'var(--space-4)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)' }}>
            <Eye size={24} color="var(--warning)" />
            <div>
              <div style={{ fontWeight: 700, fontSize: '1rem', color: 'var(--text-primary)' }}>
                {reviewCount} {reviewCount === 1 ? 'Workflow Requires' : 'Workflows Require'} Human Attention
              </div>
              <div style={{ fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
                Inspect AI drafts, read critic feedback, approve, or submit revision feedback.
              </div>
            </div>
          </div>
          <Link to="/review">
            <Button variant="primary" size="sm" rightIcon={<ArrowRight size={16} />}>
              Open HITL Review Station
            </Button>
          </Link>
        </div>
      )}

      {/* Recent Workflows Section */}
      <Card
        header={
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <h3 style={{ fontSize: '1.05rem', fontWeight: 700 }}>Recent Workflows</h3>
            <Link to="/workflows" style={{ fontSize: '0.85rem', fontWeight: 600, display: 'inline-flex', alignItems: 'center', gap: 'var(--space-1)' }}>
              <span>View all ({workflows.length})</span>
              <ArrowRight size={14} />
            </Link>
          </div>
        }
      >
        {recentWorkflows.length === 0 ? (
          <EmptyState
            title="No workflows created yet"
            description="Initiate your first multi-agent research and content generation workflow."
            action={{
              label: 'Launch First Workflow',
              onClick: () => (window.location.href = '/workflows/new'),
            }}
          />
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.9rem' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border-subtle)', color: 'var(--text-muted)', fontSize: '0.8rem', textTransform: 'uppercase' }}>
                  <th style={{ padding: 'var(--space-3)' }}>Niche / Topic</th>
                  <th style={{ padding: 'var(--space-3)' }}>Platform</th>
                  <th style={{ padding: 'var(--space-3)' }}>Status</th>
                  <th style={{ padding: 'var(--space-3)' }}>Revisions</th>
                  <th style={{ padding: 'var(--space-3)', textAlign: 'right' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {recentWorkflows.map((wf) => (
                  <tr key={wf.id} style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                    <td style={{ padding: 'var(--space-4)', fontWeight: 600 }}>
                      <Link to={`/workflows/${wf.id}`} style={{ color: 'var(--text-primary)' }}>
                        {wf.niche}
                      </Link>
                    </td>
                    <td style={{ padding: 'var(--space-4)', textTransform: 'capitalize', color: 'var(--text-secondary)' }}>
                      {wf.target_platform}
                    </td>
                    <td style={{ padding: 'var(--space-4)' }}>
                      <StatusBadge status={wf.status} />
                    </td>
                    <td style={{ padding: 'var(--space-4)', color: 'var(--text-secondary)' }}>
                      {wf.revision_count}
                    </td>
                    <td style={{ padding: 'var(--space-4)', textAlign: 'right' }}>
                      {wf.status === 'WAITING_FOR_HUMAN_REVIEW' || wf.status === 'HUMAN_REVIEW' ? (
                        <Link to={`/review/${wf.id}`}>
                          <Button size="sm" variant="primary">
                            Review Draft
                          </Button>
                        </Link>
                      ) : (
                        <Link to={`/workflows/${wf.id}`}>
                          <Button size="sm" variant="ghost">
                            View Details
                          </Button>
                        </Link>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
};
