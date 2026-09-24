import React, { useState, useEffect, useCallback } from 'react';
import { scheduleService } from '../../services/schedules';
import { ScheduleResponse } from '../../types';
import { useToast } from '../../context/ToastContext';
import { ScheduleCard } from '../../components/schedule/ScheduleCard';
import { Button } from '../../components/ui/Button';
import { LoadingSpinner } from '../../components/ui/LoadingSpinner';
import { ErrorState } from '../../components/ui/ErrorState';
import { EmptyState } from '../../components/ui/EmptyState';
import { Calendar, RefreshCw } from 'lucide-react';

export const SchedulesPage: React.FC = () => {
  const [schedules, setSchedules] = useState<ScheduleResponse[]>([]);
  const [statusFilter, setStatusFilter] = useState<string>('ALL');
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [actionLoadingId, setActionLoadingId] = useState<string | null>(null);

  const { success, error: toastError } = useToast();

  const fetchSchedules = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const filter = statusFilter === 'ALL' ? undefined : statusFilter;
      const res = await scheduleService.listSchedules({ status: filter });
      setSchedules(res.schedules);
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Failed to load publication schedules.';
      setError(msg);
    } finally {
      setIsLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    fetchSchedules();
  }, [fetchSchedules]);

  const handleRunNow = async (scheduleId: string) => {
    setActionLoadingId(scheduleId);
    try {
      await scheduleService.runScheduleNow(scheduleId);
      success('Scheduled publication executed immediately!');
      await fetchSchedules();
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Failed to run schedule immediately.';
      toastError(msg);
    } finally {
      setActionLoadingId(null);
    }
  };

  const handleCancel = async (scheduleId: string) => {
    setActionLoadingId(scheduleId);
    try {
      await scheduleService.cancelSchedule(scheduleId);
      success('Schedule cancelled.');
      await fetchSchedules();
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Failed to cancel schedule.';
      toastError(msg);
    } finally {
      setActionLoadingId(null);
    }
  };

  const filterTabs = [
    { label: 'All Jobs', value: 'ALL' },
    { label: 'Scheduled (Upcoming)', value: 'SCHEDULED' },
    { label: 'Completed', value: 'COMPLETED' },
    { label: 'Failed', value: 'FAILED' },
    { label: 'Cancelled', value: 'CANCELLED' },
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-6)' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 'var(--space-4)' }}>
        <div>
          <h1 style={{ fontSize: '1.75rem', fontWeight: 800, letterSpacing: '-0.02em' }}>
            Publishing Schedules & Automation
          </h1>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.925rem' }}>
            APScheduler background job queue for automated social post publishing.
          </p>
        </div>
        <Button variant="secondary" size="sm" onClick={fetchSchedules} leftIcon={<RefreshCw size={14} />}>
          Refresh Queue
        </Button>
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
        <LoadingSpinner message="Loading schedule queue..." />
      ) : error ? (
        <ErrorState message={error} onRetry={fetchSchedules} />
      ) : schedules.length === 0 ? (
        <EmptyState
          title="No scheduled jobs found"
          description={
            statusFilter === 'ALL'
              ? 'Approve a workflow draft to schedule future publication.'
              : `No schedules found matching filter "${statusFilter}".`
          }
          icon={<Calendar size={32} />}
        />
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))', gap: 'var(--space-4)' }}>
          {schedules.map((sched) => (
            <ScheduleCard
              key={sched.id}
              schedule={sched}
              onRunNow={handleRunNow}
              onCancel={handleCancel}
              isActionLoading={actionLoadingId === sched.id}
            />
          ))}
        </div>
      )}
    </div>
  );
};
