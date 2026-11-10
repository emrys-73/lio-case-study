import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { AlternativesBox, alternativeLine, alternativesOf } from '@/components/ExtractionReview';
import type * as api from '@/lib/api';

function extractionWith(alternatives: unknown): api.ExtractionResponse {
  return {
    success: true,
    data: {
      title: 'Workstations',
      vendorName: 'Dell',
      vatId: null,
      department: null,
      orderLines: [],
      totalCost: 0,
      commodityGroupId: null,
      commodityGroupName: null,
      alternatives,
    } as api.ExtractedVendorData,
  };
}

const twoAlternatives = extractionWith([
  { positionDescription: 'Monitor 27 inch, optional', totalPrice: 249.9 },
  { positionDescription: 'Extended warranty', totalPrice: null },
]);

describe('alternatives the extraction left out of the order lines', () => {
  it('reads them from the extraction, none when missing', () => {
    expect(alternativesOf(twoAlternatives)).toHaveLength(2);
    expect(alternativesOf(extractionWith(undefined))).toEqual([]);
    expect(alternativesOf(undefined)).toEqual([]);
  });

  it('turns one into a line of one at its price', () => {
    expect(alternativeLine({ positionDescription: 'Monitor', totalPrice: 249.9 })).toEqual({
      positionDescription: 'Monitor',
      unitPrice: 249.9,
      amount: 1,
      unit: '',
      totalPrice: 249.9,
    });
  });

  it('shows nothing when there are none', () => {
    const { container } = render(<AlternativesBox extraction={extractionWith([])} onAdd={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('shows one quiet line that opens to list them', async () => {
    render(<AlternativesBox extraction={twoAlternatives} onAdd={vi.fn()} />);
    const toggle = screen.getByRole('button', { name: '2 alternatives, not included' });
    expect(screen.queryByText('Monitor 27 inch, optional')).not.toBeInTheDocument();

    await userEvent.click(toggle);
    expect(screen.getByText('Monitor 27 inch, optional')).toBeInTheDocument();
    expect(screen.getByText('€249.90')).toBeInTheDocument();
    expect(screen.getByText('No price')).toBeInTheDocument();
  });

  it('adds one as a line and takes it off the list', async () => {
    const onAdd = vi.fn();
    render(<AlternativesBox extraction={twoAlternatives} onAdd={onAdd} />);
    await userEvent.click(screen.getByRole('button', { name: '2 alternatives, not included' }));
    await userEvent.click(screen.getAllByRole('button', { name: 'Add as a line' })[0]);

    expect(onAdd).toHaveBeenCalledWith(
      expect.objectContaining({ positionDescription: 'Monitor 27 inch, optional', totalPrice: 249.9 }),
    );
    expect(screen.queryByText('Monitor 27 inch, optional')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '1 alternative, not included' })).toBeInTheDocument();
  });

  it('starts over when a new quote is read', async () => {
    const { rerender } = render(<AlternativesBox extraction={twoAlternatives} onAdd={vi.fn()} />);
    await userEvent.click(screen.getByRole('button', { name: '2 alternatives, not included' }));
    await userEvent.click(screen.getAllByRole('button', { name: 'Add as a line' })[0]);

    rerender(
      <AlternativesBox
        extraction={extractionWith([{ positionDescription: 'Docking station', totalPrice: 120 }])}
        onAdd={vi.fn()}
      />,
    );
    expect(screen.getByRole('button', { name: '1 alternative, not included' })).toBeInTheDocument();
  });
});
