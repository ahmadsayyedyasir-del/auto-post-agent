import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { ToastProvider } from '../src/context/ToastContext';
import { WorkflowDetailPage } from '../src/pages/workflows/WorkflowDetailPage';
import { Stepper } from '../src/components/ui/Stepper';
import { workflowService } from '../src/services/workflows';
import { WorkflowDetailResponse } from '../src/types';

vi.mock('../src/services/workflows', () => ({
  workflowService: {
    startWorkflow: vi.fn(),
    listWorkflows: vi.fn(),
    getWorkflow: vi.fn(),
    submitReview: vi.fn(),
    getRevisions: vi.fn(),
    deleteWorkflow: vi.fn(),
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

const createBaseWorkflow = (overrides: Partial<WorkflowDetailResponse> = {}): WorkflowDetailResponse => ({
  id: 'wf-test-100',
  niche: 'Autonomous Systems',
  target_platform: 'linkedin',
  audience: 'Software Engineers',
  language: 'English',
  status: 'RESEARCHING',
  current_stage: 'RESEARCHING',
  revision_count: 0,
  agent_revision_count: 0,
  human_revision_count: 0,
  human_rejection_count: 0,
  max_human_rejections: 3,
  max_revisions: 2,
  research_data: null,
  content_plan: null,
  error_message: null,
  posts: [],
  feedbacks: [],
  publications: [],
  schedules: [],
  ...overrides,
});

describe('Pipeline Visibility & Execution Stage Display', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Stepper Component Stage States', () => {
    it('marks RESEARCHING as active step with correct subtitle', () => {
      render(<Stepper currentStatus="RESEARCHING" currentStage="RESEARCHING" />);
      const researchStep = screen.getByText('Research').closest('.stepper-step');
      expect(researchStep).toHaveClass('active');
      expect(screen.getByText('Searching current trends and sources...')).toBeInTheDocument();
      const planningStep = screen.getByText('Planning').closest('.stepper-step');
      expect(planningStep).not.toHaveClass('active');
      expect(planningStep).not.toHaveClass('completed');
    });

    it('marks PLANNING as active and Research as completed', () => {
      render(<Stepper currentStatus="PLANNING" currentStage="PLANNING" />);
      const researchStep = screen.getByText('Research').closest('.stepper-step');
      const planningStep = screen.getByText('Planning').closest('.stepper-step');
      expect(researchStep).toHaveClass('completed');
      expect(planningStep).toHaveClass('active');
      expect(screen.getByText('Selecting topic, angle and content strategy...')).toBeInTheDocument();
    });

    it('marks WRITING as active and earlier stages as completed', () => {
      render(<Stepper currentStatus="WRITING" currentStage="WRITING" />);
      expect(screen.getByText('Research').closest('.stepper-step')).toHaveClass('completed');
      expect(screen.getByText('Planning').closest('.stepper-step')).toHaveClass('completed');
      expect(screen.getByText('Writing').closest('.stepper-step')).toHaveClass('active');
      expect(screen.getByText('Generating platform-specific content...')).toBeInTheDocument();
      expect(screen.getByText('Critic').closest('.stepper-step')).not.toHaveClass('active');
    });

    it('marks CRITIQUING as active and earlier stages as completed', () => {
      render(<Stepper currentStatus="CRITIQUING" currentStage="CRITIQUING" />);
      expect(screen.getByText('Research').closest('.stepper-step')).toHaveClass('completed');
      expect(screen.getByText('Planning').closest('.stepper-step')).toHaveClass('completed');
      expect(screen.getByText('Writing').closest('.stepper-step')).toHaveClass('completed');
      expect(screen.getByText('Critic').closest('.stepper-step')).toHaveClass('active');
      expect(screen.getByText('Checking quality, relevance and platform constraints...')).toBeInTheDocument();
    });

    it('marks WAITING_FOR_HUMAN_REVIEW as waiting on Human Review step', () => {
      render(<Stepper currentStatus="WAITING_FOR_HUMAN_REVIEW" currentStage="WAITING_FOR_HUMAN_REVIEW" />);
      expect(screen.getByText('Research').closest('.stepper-step')).toHaveClass('completed');
      expect(screen.getByText('Planning').closest('.stepper-step')).toHaveClass('completed');
      expect(screen.getByText('Writing').closest('.stepper-step')).toHaveClass('completed');
      expect(screen.getByText('Critic').closest('.stepper-step')).toHaveClass('completed');
      expect(screen.getByText('Review').closest('.stepper-step')).toHaveClass('waiting');
      expect(screen.getByText('Waiting for your approval, revision or rejection...')).toBeInTheDocument();
    });

    it('marks correct stage as FAILED without defaulting to Research', () => {
      // Writing failed
      const { rerender } = render(
        <Stepper currentStatus="FAILED" currentStage="WRITING" errorMessage="LLM Rate Limit Reached" />
      );
      expect(screen.getByText('Research').closest('.stepper-step')).toHaveClass('completed');
      expect(screen.getByText('Planning').closest('.stepper-step')).toHaveClass('completed');
      expect(screen.getByText('Writing').closest('.stepper-step')).toHaveClass('failed');
      expect(screen.getByText('LLM Rate Limit Reached')).toBeInTheDocument();

      // Planning failed
      rerender(
        <Stepper currentStatus="FAILED" currentStage="PLANNING" errorMessage="Schema parse failed" />
      );
      expect(screen.getByText('Research').closest('.stepper-step')).toHaveClass('completed');
      expect(screen.getByText('Planning').closest('.stepper-step')).toHaveClass('failed');
      expect(screen.getByText('Schema parse failed')).toBeInTheDocument();

      // Critic failed
      rerender(
        <Stepper currentStatus="FAILED" currentStage="CRITIQUING" errorMessage="Critic check crashed" />
      );
      expect(screen.getByText('Writing').closest('.stepper-step')).toHaveClass('completed');
      expect(screen.getByText('Critic').closest('.stepper-step')).toHaveClass('failed');
      expect(screen.getByText('Critic check crashed')).toBeInTheDocument();
    });

    it('marks all completed on APPROVED and PUBLISHED', () => {
      const { rerender } = render(<Stepper currentStatus="APPROVED" />);
      expect(screen.getByText('Research').closest('.stepper-step')).toHaveClass('completed');
      expect(screen.getByText('Review').closest('.stepper-step')).toHaveClass('completed');
      expect(screen.getByText('Published').closest('.stepper-step')).toHaveClass('completed');

      rerender(<Stepper currentStatus="PUBLISHED" />);
      expect(screen.getByText('Research').closest('.stepper-step')).toHaveClass('completed');
      expect(screen.getByText('Review').closest('.stepper-step')).toHaveClass('completed');
      expect(screen.getByText('Published').closest('.stepper-step')).toHaveClass('completed');
    });
  });

  describe('WorkflowDetailPage Failure and Review Rendering', () => {
    it('renders error callout with failed stage and error message when workflow fails', async () => {
      const failedWorkflow = createBaseWorkflow({
        id: 'wf-fail-1',
        status: 'FAILED',
        current_stage: 'WRITING',
        error_message: 'Anthropic API connection dropped midway',
      });
      vi.mocked(workflowService.getWorkflow).mockResolvedValue(failedWorkflow);

      render(
        <MemoryRouter initialEntries={['/workflows/wf-fail-1']}>
          <ToastProvider>
            <Routes>
              <Route path="/workflows/:id" element={<WorkflowDetailPage />} />
            </Routes>
          </ToastProvider>
        </MemoryRouter>
      );

      await waitFor(() => {
        expect(screen.getByText(/Execution Failed during stage:/i)).toBeInTheDocument();
        expect(screen.getAllByText('Anthropic API connection dropped midway').length).toBeGreaterThan(0);
      });
    });

    it('renders human review button and pending badge when status is WAITING_FOR_HUMAN_REVIEW', async () => {
      const reviewWorkflow = createBaseWorkflow({
        id: 'wf-review-1',
        status: 'WAITING_FOR_HUMAN_REVIEW',
        current_stage: 'human_review',
        posts: [
          {
            id: 'post-99',
            platform: 'linkedin',
            topic: 'Autonomous Agents',
            content: 'Draft content for review',
            status: 'IN_REVIEW',
            content_type: 'single_post',
            language: 'English',
            hashtags: ['#AI'],
            cta: 'Share thoughts',
            source_references: [],
            revisions: [],
          },
        ],
      });
      vi.mocked(workflowService.getWorkflow).mockResolvedValue(reviewWorkflow);

      render(
        <MemoryRouter initialEntries={['/workflows/wf-review-1']}>
          <ToastProvider>
            <Routes>
              <Route path="/workflows/:id" element={<WorkflowDetailPage />} />
            </Routes>
          </ToastProvider>
        </MemoryRouter>
      );

      await waitFor(() => {
        expect(screen.getByText('Review Draft (Action Required)')).toBeInTheDocument();
        expect(screen.getAllByText(/Review/i).length).toBeGreaterThan(0);
      });
    });
  });

  describe('Delete Workflow', () => {
    it('renders Delete Workflow button for terminal workflows', async () => {
      const approvedWorkflow = createBaseWorkflow({
        id: 'wf-del-1',
        status: 'APPROVED',
        current_stage: 'completed',
      });
      vi.mocked(workflowService.getWorkflow).mockResolvedValue(approvedWorkflow);

      render(
        <MemoryRouter initialEntries={['/workflows/wf-del-1']}>
          <ToastProvider>
            <Routes>
              <Route path="/workflows/:id" element={<WorkflowDetailPage />} />
            </Routes>
          </ToastProvider>
        </MemoryRouter>
      );

      await waitFor(() => {
        expect(screen.getByText('Delete Workflow')).toBeInTheDocument();
      });
    });

    it('does NOT render Delete button for actively executing workflows', async () => {
      const activeWorkflow = createBaseWorkflow({
        id: 'wf-active-1',
        status: 'WRITING',
        current_stage: 'WRITING',
      });
      vi.mocked(workflowService.getWorkflow).mockResolvedValue(activeWorkflow);

      render(
        <MemoryRouter initialEntries={['/workflows/wf-active-1']}>
          <ToastProvider>
            <Routes>
              <Route path="/workflows/:id" element={<WorkflowDetailPage />} />
            </Routes>
          </ToastProvider>
        </MemoryRouter>
      );

      await waitFor(() => {
        expect(screen.getByText('Generating platform-specific content...')).toBeInTheDocument();
      });
      expect(screen.queryByText('Delete Workflow')).not.toBeInTheDocument();
    });

    it('shows confirmation dialog when Delete is clicked', async () => {
      const failedWorkflow = createBaseWorkflow({
        id: 'wf-del-2',
        status: 'FAILED',
        current_stage: 'WRITING',
        error_message: 'LLM timeout',
      });
      vi.mocked(workflowService.getWorkflow).mockResolvedValue(failedWorkflow);

      render(
        <MemoryRouter initialEntries={['/workflows/wf-del-2']}>
          <ToastProvider>
            <Routes>
              <Route path="/workflows/:id" element={<WorkflowDetailPage />} />
            </Routes>
          </ToastProvider>
        </MemoryRouter>
      );

      await waitFor(() => {
        expect(screen.getByText('Delete Workflow')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('Delete Workflow'));

      await waitFor(() => {
        expect(screen.getByText('Delete Permanently')).toBeInTheDocument();
        expect(screen.getByText(/permanently delete this workflow/i)).toBeInTheDocument();
      });
    });
  });

  describe('Manual Refresh and Polling Behavior', () => {
    it('triggers manual refresh when Refresh button is clicked', async () => {
      const activeWorkflow = createBaseWorkflow({
        id: 'wf-refresh-1',
        status: 'WRITING',
        current_stage: 'WRITING',
      });
      vi.mocked(workflowService.getWorkflow).mockResolvedValue(activeWorkflow);

      render(
        <MemoryRouter initialEntries={['/workflows/wf-refresh-1']}>
          <ToastProvider>
            <Routes>
              <Route path="/workflows/:id" element={<WorkflowDetailPage />} />
            </Routes>
          </ToastProvider>
        </MemoryRouter>
      );

      await waitFor(() => {
        expect(workflowService.getWorkflow).toHaveBeenCalledTimes(1);
      });

      const refreshBtn = screen.getByRole('button', { name: /refresh/i });
      fireEvent.click(refreshBtn);

      await waitFor(() => {
        expect(workflowService.getWorkflow).toHaveBeenCalledTimes(2);
      });
    });

    it('stops polling when workflow is in a terminal status', async () => {
      const completedWorkflow = createBaseWorkflow({
        id: 'wf-term-1',
        status: 'APPROVED',
        current_stage: 'completed',
      });
      vi.mocked(workflowService.getWorkflow).mockResolvedValue(completedWorkflow);

      render(
        <MemoryRouter initialEntries={['/workflows/wf-term-1']}>
          <ToastProvider>
            <Routes>
              <Route path="/workflows/:id" element={<WorkflowDetailPage />} />
            </Routes>
          </ToastProvider>
        </MemoryRouter>
      );

      await waitFor(() => {
        expect(workflowService.getWorkflow).toHaveBeenCalledTimes(1);
      });

      // Terminal status should not trigger further polling calls
      expect(workflowService.getWorkflow).toHaveBeenCalledTimes(1);
    });
  });
});
