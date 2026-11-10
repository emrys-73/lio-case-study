import { render, screen, waitFor } from '@testing-library/react';
import { useState } from 'react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  AlternativesBox,
  LineCheck,
  TotalsCheck,
  lineAddsUp,
  PRICE_FROM_TOTAL,
  NOT_IN_QUOTE,
  alternativeLine,
  alternativesOf,
  fillMissingPrice,
  markText,
  useOwnDepartment,
} from '@/components/ExtractionReview';
import * as api from '@/lib/api';

vi.mock('@/lib/api', () => ({ auth: { me: vi.fn() } }));

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

describe('a line the quote gives no price for', () => {
  it('takes the price from the line total so the line adds up', () => {
    const line = fillMissingPrice({
      positionDescription: 'Lieferung und Montage',
      unitPrice: null,
      amount: null,
      unit: null,
      totalPrice: 4.9,
    });
    expect(line).toMatchObject({ unitPrice: 4.9, amount: 1, totalPrice: 4.9, unit: '' });
    expect(markText(line, 'unitPrice')).toBe(PRICE_FROM_TOTAL);
    expect(markText(line, 'amount')).toBe(NOT_IN_QUOTE);
  });

  it('splits the total over the amount when the amount is there', () => {
    const line = fillMissingPrice({ positionDescription: 'Cable', unitPrice: null, amount: 4, unit: 'pcs', totalPrice: 10 });
    expect(line).toMatchObject({ unitPrice: 2.5, amount: 4, totalPrice: 10 });
    expect(markText(line, 'unitPrice')).toBe(PRICE_FROM_TOTAL);
    expect(markText(line, 'amount')).toBeUndefined();
  });

  it('marks a price that is nowhere in the quote', () => {
    const line = fillMissingPrice({ positionDescription: 'Verpackung', unitPrice: null, amount: null, unit: null, totalPrice: null });
    expect(line).toMatchObject({ unitPrice: 0, amount: 1, totalPrice: 0 });
    expect(markText(line, 'unitPrice')).toBe(NOT_IN_QUOTE);
  });

  it('works out a missing line total from price times amount', () => {
    const line = fillMissingPrice({ positionDescription: 'Desk', unitPrice: 300, amount: 2, unit: 'pcs', totalPrice: null });
    expect(line).toMatchObject({ unitPrice: 300, amount: 2, totalPrice: 600 });
  });

  it('leaves a complete line alone and unmarked', () => {
    const line = fillMissingPrice({ positionDescription: 'Desk', unitPrice: 300, amount: 2, unit: 'pcs', totalPrice: 540 });
    expect(line).toMatchObject({ unitPrice: 300, amount: 2, totalPrice: 540 });
    expect(markText(line, 'unitPrice')).toBeUndefined();
    expect(markText(line, 'amount')).toBeUndefined();
  });

  it('drops the mark once the person types their own value', () => {
    const line = fillMissingPrice({ positionDescription: 'Fee', unitPrice: null, amount: null, unit: null, totalPrice: 4.9 });
    expect(markText({ ...line, unitPrice: 5 }, 'unitPrice')).toBeUndefined();
    expect(markText({ ...line, amount: 2 }, 'amount')).toBeUndefined();
  });
});

const desk = { positionDescription: 'Desk', unitPrice: 300, amount: 2, unit: 'pcs', totalPrice: 600 };
const LINE_OFF = "Quantity × price isn't this line's total. Check this line.";

describe('a line where quantity times price is not the line total', () => {
  it('adds up to the cent', () => {
    expect(lineAddsUp(desk)).toBe(true);
    expect(lineAddsUp({ ...desk, totalPrice: 540 })).toBe(false);
    expect(lineAddsUp({ ...desk, unitPrice: 33.3333, amount: 3, totalPrice: 100 })).toBe(true);
  });

  it('says which line is off and goes once the line adds up', () => {
    const { rerender } = render(<LineCheck line={{ ...desk, totalPrice: 540 }} />);
    expect(screen.getByText(LINE_OFF)).toBeInTheDocument();

    rerender(<LineCheck line={{ ...desk, totalPrice: 600 }} />);
    expect(screen.queryByText(LINE_OFF)).not.toBeInTheDocument();
  });
});

describe('totals check under the total', () => {
  it('says nothing when the quote printed no total', () => {
    const { container } = render(
      <TotalsCheck totalCost={17000} printedTotal={null} printedVat={null} printedGross={null} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('warns when the lines do not add up to the printed net total', () => {
    render(<TotalsCheck totalCost={17000} printedTotal={17230} printedVat={null} printedGross={null} />);
    expect(screen.getByText(/The lines add up to €17000.00, the quote says €17230.00/)).toBeInTheDocument();
  });

  it('warns when the lines do not fit the total with VAT', () => {
    render(<TotalsCheck totalCost={17000} printedTotal={17000} printedVat={3230} printedGross={20330} />);
    expect(screen.getByText(/That doesn't fit the\s+quote's total of €20330.00 with VAT/)).toBeInTheDocument();
  });

  it('trusts the gross total over a net read in pieces', () => {
    const { container } = render(
      <TotalsCheck totalCost={17000} printedTotal={15000} printedVat={2850} printedGross={20230} />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});

function DepartmentField({ start = '' }: { start?: string }) {
  const [department, setDepartment] = useState(start);
  useOwnDepartment(setDepartment);
  return <input aria-label="Department" value={department} onChange={(e) => setDepartment(e.target.value)} />;
}

describe('department from the requester, not the quote', () => {
  beforeEach(() => vi.mocked(api.auth.me).mockReset());

  it('fills it from the signed-in profile', async () => {
    vi.mocked(api.auth.me).mockResolvedValue({ profile: { department: 'Marketing' } } as never);
    render(<DepartmentField />);
    await waitFor(() => expect(screen.getByLabelText('Department')).toHaveValue('Marketing'));
  });

  it('never overwrites what is already typed', async () => {
    vi.mocked(api.auth.me).mockResolvedValue({ profile: { department: 'Marketing' } } as never);
    render(<DepartmentField start="Finance" />);
    await waitFor(() => expect(api.auth.me).toHaveBeenCalled());
    expect(screen.getByLabelText('Department')).toHaveValue('Finance');
  });

  it('stays empty when the profile has none', async () => {
    vi.mocked(api.auth.me).mockResolvedValue({ profile: { department: null } } as never);
    render(<DepartmentField />);
    await waitFor(() => expect(api.auth.me).toHaveBeenCalled());
    expect(screen.getByLabelText('Department')).toHaveValue('');
  });
});
