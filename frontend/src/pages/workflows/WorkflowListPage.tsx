import React, { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { workflowService } from '../../services/workflows';
import { WorkflowDetailResponse } from '../../types';
import { Card } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { StatusBadge } from '../../components/ui/StatusBadge';
import { LoadingSpinner } from '../../components/ui/LoadingSpinner';
import { ErrorState } from '../../components/ui/ErrorState';
import { EmptyState } from '../../components/ui/EmptyState';
import { Plus, RefreshCw, Sparkles } from 'lucide-react';

export const WorkflowListPage: React.FC = () => {
  const [workflows, setWorkflows] = useState<WorkflowDetailResponse[]>([]);
  const [statusFilter, setStatusFilter] = useState<string>('ALL');
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchWorkflows = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const filter = statusFilter === 'ALL' ? undefined : statusFilter;
      const data = await workflowService.listWorkflows(filter);
      setWorkflows(data);
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Failed to load workflows.';
      setError(msg);
    } finally {
      setIsLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    fetchWorkflows();
  }, [fetchWorkflows]);

  const filterTabs = [
    { label: 'All', value: 'ALL' },
    { label: 'Review Pending', value: 'WAITING_FOR_HUMAN_REVIEW' },
    { label: 'Approved', value: 'APPROVED' },
    { label: 'Published', value: 'PUBLISHED' },
    { label: 'Failed / Rejected', value: 'FAILED' },
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-6)' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 'var(--space-4)' }}>
        <div>
          <h1 style={{ fontSize: '1.75rem', fontWeight: 800, letterSpacing: '-0.02em' }}>
            Workflow Executions
          </h1>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.925rem' }}>
            Manage and track your autonomous multi-agent content pipelines.
          </p>
        </div>
        <div style={{ display: 'flex', gap: 'var(--space-3)' }}>
          <Button variant="secondary" size="sm" onClick={fetchWorkflows} leftIcon={<RefreshCw size={14} />}>
            Refresh
          </Button>
          <Link to="/workflows/new">
            <Button variant="primary" size="sm" leftIcon={<Plus size={16} />}>
              New Workflow
            </Button>
          </Link>
        </div>
      </div>

      {/* Filter Tabs */}
      <div style={{ display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap', borderBottom: '1px solid var(--border-subtle)', paddingBottom: 'var(--space-2)' }}>
        {filterTabs.map((tab) => (
          <button
            key={tab.value}
            onClick={() => setStatusFilter(tab.value)}
            className={`btn btn-sm ${statusFilter === tab.value ? 'btn-primary' : 'btn-ghost'}`}
            style={{ fontSize: '0.85rem' }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {isLoading ? (
        <LoadingSpinner message="Fetching workflows..." />
      ) : error ? (
        <ErrorState message={error} onRetry={fetchWorkflows} />
      ) : workflows.length === 0 ? (
        <EmptyState
          title="No workflows found"
          description={
            statusFilter === 'ALL'
              ? 'Get started by creating your first automated generation pipeline.'
              : `No workflows with status "${statusFilter}".`
          }
          icon={<Sparkles size={28} />}
          action={
            statusFilter === 'ALL'
              ? {
                  label: 'Launch First Workflow',
                  onClick: () => (window.location.href = '/workflows/new'),
                }
              : undefined
          }
        />
      ) : (
        <Card>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.9rem' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border-subtle)', color: 'var(--text-muted)', fontSize: '0.8rem', textTransform: 'uppercase' }}>
                  <th style={{ padding: 'var(--space-3)' }}>Niche / Angle</th>
                  <th style={{ padding: 'var(--space-3)' }}>Platform</th>
                  <th style={{ padding: 'var(--space-3)' }}>Audience</th>
                  <th style={{ padding: 'var(--space-3)' }}>Status</th>
                  <th style={{ padding: 'var(--space-3)' }}>Revisions</th>
                  <th style={{ padding: 'var(--space-3)', textAlign: 'right' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {workflows.map((wf) => (
                  <tr key={wf.id} style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                    <td style={{ padding: 'var(--space-4)', fontWeight: 600 }}>
                      <Link to={`/workflows/${wf.id}`} style={{ color: 'var(--text-primary)' }}>
                        {wf.niche}
                      </Link>
                    </td>
                    <td style={{ padding: 'var(--space-4)', textTransform: 'capitalize', color: 'var(--text-secondary)' }}>
                      {wf.target_platform}
                    </td>
                    <td style={{ padding: 'var(--space-4)', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                      {wf.audience || 'General'}
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
                          <Button size="sm" variant="secondary">
                            View
                          </Button>
                        </Link>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
};
