import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { Button } from '../src/components/ui/Button';
import { Card } from '../src/components/ui/Card';
import { StatusBadge } from '../src/components/ui/StatusBadge';
import { Modal } from '../src/components/ui/Modal';
import { Stepper } from '../src/components/ui/Stepper';
import { EmptyState, ErrorState } from '../src/components/ui/EmptyState';
import { Input, Textarea, Select } from '../src/components/ui/Input';

describe('UI Component Library', () => {
  it('renders Button with variants, loading state and click handler', () => {
    const handleClick = vi.fn();
    const { rerender } = render(
      <Button variant="primary" onClick={handleClick}>
        Submit Post
      </Button>
    );

    const btn = screen.getByRole('button', { name: /submit post/i });
    expect(btn).toBeInTheDocument();
    expect(btn).toHaveClass('btn-primary');

    fireEvent.click(btn);
    expect(handleClick).toHaveBeenCalledTimes(1);

    // Rerender with loading state
    rerender(
      <Button variant="primary" isLoading onClick={handleClick}>
        Submit Post
      </Button>
    );
    expect(btn).toBeDisabled();
  });

  it('renders Card with header and footer', () => {
    render(
      <Card header={<h2>Card Title</h2>} footer={<span>Footer Content</span>}>
        <p>Body Content</p>
      </Card>
    );

    expect(screen.getByText('Card Title')).toBeInTheDocument();
    expect(screen.getByText('Body Content')).toBeInTheDocument();
    expect(screen.getByText('Footer Content')).toBeInTheDocument();
  });

  it('renders StatusBadge mapping different workflow states correctly', () => {
    const { rerender } = render(<StatusBadge status="APPROVED" />);
    expect(screen.getByText('APPROVED')).toBeInTheDocument();

    rerender(<StatusBadge status="WAITING_FOR_HUMAN_REVIEW" />);
    expect(screen.getByText('REVIEW REQUIRED')).toBeInTheDocument();

    rerender(<StatusBadge status="RESEARCHING" />);
    expect(screen.getByText('RESEARCHING')).toBeInTheDocument();

    rerender(<StatusBadge status="FAILED" />);
    expect(screen.getByText('FAILED')).toBeInTheDocument();
  });

  it('renders Modal when isOpen is true and fires onClose', () => {
    const handleClose = vi.fn();
    const { rerender } = render(
      <Modal isOpen={false} onClose={handleClose} title="Test Modal">
        <p>Modal Body</p>
      </Modal>
    );

    expect(screen.queryByText('Test Modal')).not.toBeInTheDocument();

    rerender(
      <Modal isOpen={true} onClose={handleClose} title="Test Modal">
        <p>Modal Body</p>
      </Modal>
    );

    expect(screen.getByText('Test Modal')).toBeInTheDocument();
    expect(screen.getByText('Modal Body')).toBeInTheDocument();

    const closeBtn = screen.getByRole('button', { name: /close modal/i });
    fireEvent.click(closeBtn);
    expect(handleClose).toHaveBeenCalledTimes(1);
  });

  it('renders Stepper marking completed and active steps', () => {
    render(<Stepper currentStatus="WRITING" />);
    const stepper = screen.getByLabelText('Workflow progress steps');
    expect(stepper).toBeInTheDocument();
    expect(screen.getByText('Writing')).toBeInTheDocument();
  });

  it('renders EmptyState and ErrorState with retry action', () => {
    const handleAction = vi.fn();
    const handleRetry = vi.fn();

    render(
      <>
        <EmptyState
          title="No Workflows"
          description="Create one"
          action={{ label: 'Add', onClick: handleAction }}
        />
        <ErrorState message="Server unreachable" onRetry={handleRetry} />
      </>
    );

    expect(screen.getByText('No Workflows')).toBeInTheDocument();
    expect(screen.getByText('Server unreachable')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Add' }));
    expect(handleAction).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole('button', { name: 'Try Again' }));
    expect(handleRetry).toHaveBeenCalledTimes(1);
  });

  it('renders Form Controls (Input, Textarea, Select) with validation errors', () => {
    render(
      <>
        <Input label="Test Input" error="Input is required" />
        <Textarea label="Test Textarea" error="Textarea error" />
        <Select
          label="Test Select"
          options={[
            { label: 'Option 1', value: '1' },
            { label: 'Option 2', value: '2' },
          ]}
        />
      </>
    );

    expect(screen.getByLabelText('Test Input')).toBeInTheDocument();
    expect(screen.getByText('Input is required')).toBeInTheDocument();
    expect(screen.getByText('Textarea error')).toBeInTheDocument();
    expect(screen.getByLabelText('Test Select')).toBeInTheDocument();
  });
});
