import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { CorrectionProposalCard } from './CorrectionProposalCard';
import { MessageBubble } from './MessageBubble';
import type { CorrectionProposal, Message } from '../../types/caReview';

describe('CorrectionProposalCard', () => {
  const sampleProposal: CorrectionProposal = {
    id: 'prop-123',
    conversation_id: 'conv-1',
    target_agent: 'accounting_review',
    target_entity_type: 'extracted_row',
    target_entity_id: '101',
    title: 'Correction of Sales Figure: Invoice INV-002',
    description: 'The sales figure is incorrect. Verified invoice shows Rs. 450,000 instead of Rs. 500,000.',
    original_data: {
      recorded_amount: 500000,
      reference: 'INV-002',
    },
    proposed_data: {
      corrected_amount: 450000,
      difference: -50000,
    },
    status: 'pending',
    reexecution_plan: ['accounting_review', 'adjustments', 'reporting'],
    reexecution_result: {},
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  };

  it('renders proposal details, diff values, and action buttons', () => {
    const onReview = vi.fn().mockResolvedValue(undefined);
    render(
      <CorrectionProposalCard
        proposal={sampleProposal}
        onReview={onReview}
        canApprove={true}
      />,
    );

    expect(screen.getByText(/Correction of Sales Figure: Invoice INV-002/i)).toBeInTheDocument();
    expect(screen.getByText(/PKR 500,000.00/i)).toBeInTheDocument();
    expect(screen.getByText(/PKR 450,000.00/i)).toBeInTheDocument();
    expect(screen.getByText(/Approve & Re-execute Pipeline/i)).toBeInTheDocument();
    expect(screen.getByText(/Reject Proposal/i)).toBeInTheDocument();
  });

  it('opens approval dialog when clicking approve', () => {
    const onReview = vi.fn().mockResolvedValue(undefined);
    render(
      <CorrectionProposalCard
        proposal={sampleProposal}
        onReview={onReview}
        canApprove={true}
      />,
    );

    const approveBtn = screen.getByText(/Approve & Re-execute Pipeline/i);
    fireEvent.click(approveBtn);

    expect(screen.getByText(/Approve & Re-execute Agents/i)).toBeInTheDocument();
    expect(screen.getByText(/Confirm & Execute/i)).toBeInTheDocument();
  });
});

describe('MessageBubble', () => {
  it('renders user message bubble correctly', () => {
    const userMsg: Message = {
      id: 'm1',
      conversation_id: 'c1',
      sender_type: 'user',
      content: 'The sales figure is incorrect. Invoice shows Rs. 450,000 instead of Rs. 500,000. Correct it.',
      created_at: new Date().toISOString(),
    };

    render(
      <MessageBubble
        message={userMsg}
        onReviewProposal={vi.fn()}
      />,
    );

    expect(screen.getByText(/The sales figure is incorrect/i)).toBeInTheDocument();
  });

  it('renders assistant response with intent badge', () => {
    const assistantMsg: Message = {
      id: 'm2',
      conversation_id: 'c1',
      sender_type: 'assistant',
      content: 'I have identified the affected transaction and prepared a traceable Correction Proposal.',
      intent: 'correction_request',
      created_at: new Date().toISOString(),
    };

    render(
      <MessageBubble
        message={assistantMsg}
        onReviewProposal={vi.fn()}
      />,
    );

    expect(screen.getByText(/Correction Proposal/i)).toBeInTheDocument();
    expect(screen.getByText(/prepared a traceable Correction Proposal/i)).toBeInTheDocument();
  });
});
