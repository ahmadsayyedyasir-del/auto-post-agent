import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { ToastProvider } from '../src/context/ToastContext';
import { WorkflowCreatePage } from '../src/pages/workflows/WorkflowCreatePage';
import { WorkflowListPage } from '../src/pages/workflows/WorkflowListPage';
import { WorkflowDetailPage } from '../src/pages/workflows/WorkflowDetailPage';
import { workflowService } from '../src/services/workflows';
import { WorkflowDetailResponse } from '../src/types';

vi.mock('../src/services/workflows', () => ({
  workflowService: {
    startWorkflow: vi.fn(),
    listWorkflows: vi.fn(),
    getWorkflow: vi.fn(),
    submitReview: vi.fn(),
    getRevisions: vi.fn(),
  },
}));

vi.mock('../src/services/publications', () => ({
  publicationService: {
    publishWorkflow: vi.fn(),
    getWorkflowPublications: vi.fn().mockResolvedValue({ publications: [], total: 0 }),
  },
}));

vi.mock('../src/services/schedules', () => ({
  scheduleService: {
    createSchedule: vi.fn(),
    listSchedules: vi.fn().mockResolvedValue({ schedules: [], total: 0 }),
  },
}));

const mockWorkflowData: WorkflowDetailResponse = {
  id: 'wf-123',
  niche: 'AI Agent Architecture',
  target_platform: 'linkedin',
  audience: 'Software Engineers',
  language: 'English',
  status: 'WAITING_FOR_HUMAN_REVIEW',
  current_stage: 'human_review',
  revision_count: 1,
  agent_revision_count: 1,
  human_revision_count: 0,
  max_revisions: 2,
  research_data: { trends: [{ topic: 'LangGraph', summary: 'State machines for agents' }] },
  content_plan: { topic: 'LangGraph Agents', hook: 'Are your agents reliable?', key_points: ['Determinism', 'Checkpoints'] },
  error_message: null,
  posts: [
    {
      id: 'post-123',
      platform: 'linkedin',
      topic: 'LangGraph Agents',
      content: 'Multi-agent state machines provide predictable workflow execution.',
      status: 'IN_REVIEW',
      content_type: 'single_post',
      language: 'English',
      hashtags: ['#AI', '#Tech'],
      cta: 'What is your experience with LangGraph?',
      source_references: ['https://example.com/langgraph'],
      revisions: [],
    },
  ],
  feedbacks: [
    {
      id: 'fb-123',
      feedback_source: 'CRITIC',
      decision: 'APPROVED',
      issues: [],
      feedback_items: [],
      reviewer_notes: 'Complies with length and citations.',
    },
  ],
  publications: [],
  schedules: [],
};

describe('Workflow Studio & Detail Views', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('submits workflow creation form with required niche and parameters', async () => {
    vi.mocked(workflowService.startWorkflow).mockResolvedValue(mockWorkflowData);

    render(
      <MemoryRouter initialEntries={['/workflows/new']}>
        <ToastProvider>
          <WorkflowCreatePage />
        </ToastProvider>
      </MemoryRouter>
    );

    const nicheInput = screen.getByLabelText(/research niche/i);
    fireEvent.change(nicheInput, { target: { value: 'Autonomous AI in DevOps' } });

    const submitBtn = screen.getByRole('button', { name: /launch multi-agent pipeline/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(workflowService.startWorkflow).toHaveBeenCalledWith({
        niche: 'Autonomous AI in DevOps',
        platform: 'linkedin',
        audience: 'Tech Founders & Engineers',
        language: 'English',
        max_trends: 3,
        days_back: 7,
      });
    });
  });

  it('renders Workflow List page and displays table rows', async () => {
    vi.mocked(workflowService.listWorkflows).mockResolvedValue([mockWorkflowData]);

    render(
      <MemoryRouter initialEntries={['/workflows']}>
        <ToastProvider>
          <WorkflowListPage />
        </ToastProvider>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText('AI Agent Architecture')).toBeInTheDocument();
      expect(screen.getByText('REVIEW REQUIRED')).toBeInTheDocument();
    });
  });

  it('renders Workflow Detail page with Stepper, PostPreview, and CriticPanel', async () => {
    vi.mocked(workflowService.getWorkflow).mockResolvedValue(mockWorkflowData);

    render(
      <MemoryRouter initialEntries={['/workflows/wf-123']}>
        <ToastProvider>
          <Routes>
            <Route path="/workflows/:id" element={<WorkflowDetailPage />} />
          </Routes>
        </ToastProvider>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText('AI Agent Architecture')).toBeInTheDocument();
      expect(screen.getByText(/Multi-agent state machines provide predictable/i)).toBeInTheDocument();
      expect(screen.getByText(/Critic Evaluation Report/i)).toBeInTheDocument();
    });
  });
});
