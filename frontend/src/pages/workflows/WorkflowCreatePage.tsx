import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { workflowService } from '../../services/workflows';
import { useToast } from '../../context/ToastContext';
import { ResearchRequest } from '../../types';
import { WorkflowForm } from '../../components/workflow/WorkflowForm';

export const WorkflowCreatePage: React.FC = () => {
  const [isLoading, setIsLoading] = useState(false);
  const { success, error } = useToast();
  const navigate = useNavigate();

  const handleStartWorkflow = async (data: ResearchRequest) => {
    setIsLoading(true);
    try {
      const result = await workflowService.startWorkflow(data);
      success('Multi-agent pipeline started successfully!');

      if (result.status === 'WAITING_FOR_HUMAN_REVIEW' || result.status === 'HUMAN_REVIEW') {
        navigate(`/review/${result.id}`);
      } else {
        navigate(`/workflows/${result.id}`);
      }
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Failed to start workflow. Please check your inputs and try again.';
      error(msg);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div style={{ maxWidth: 760, margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 'var(--space-6)' }}>
      <div>
        <h1 style={{ fontSize: '1.75rem', fontWeight: 800, letterSpacing: '-0.02em' }}>
          Create Content Workflow
        </h1>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.925rem' }}>
          Specify your topic niche and audience. The Research, Planning, Writer, and Critic agents will automatically coordinate.
        </p>
      </div>

      <WorkflowForm onSubmit={handleStartWorkflow} isLoading={isLoading} />
    </div>
  );
};
