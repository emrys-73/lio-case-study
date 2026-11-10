import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import NewRequestPage from '@/app/dashboard/new-request/page';
import * as api from '@/lib/api';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), back: vi.fn(), refresh: vi.fn() }),
}));

vi.mock('@/lib/hooks/useCommodityGroups', () => ({
  useCommodityGroups: () => ({ data: [{ id: 45, category: 'Production', name: 'Production Machinery' }] }),
}));

vi.mock('@/lib/api', () => ({
  extraction: { fromPdf: vi.fn() },
  requests: { create: vi.fn(), uploadDocument: vi.fn() },
  auth: { me: vi.fn() },
}));

const LINE_OFF = "Quantity × price isn't this line's total. Check this line.";

const quote = {
  success: true,
  data: {
    title: 'Office supplies',
    vendorName: 'Bürobedarf GmbH',
    vatId: null,
    department: 'Vertrieb',
    orderLines: [
      { positionDescription: 'Desk', unitPrice: 300, amount: 2, unit: 'pcs', totalPrice: 540 },
      { positionDescription: 'Versandkosten', unitPrice: null, amount: null, unit: null, totalPrice: 4.9 },
    ],
    totalCost: 544.9,
    commodityGroupId: 45,
    commodityGroupName: 'Production Machinery',
    alternatives: [{ positionDescription: 'Desk lamp, optional', totalPrice: 39 }],
  },
  missingFields: ['VAT ID'],
  totals: { computed: 544.9, printed: 600, match: false },
};

function renderPage() {
  const client = new QueryClient();
  return render(
    <QueryClientProvider client={client}>
      <NewRequestPage />
    </QueryClientProvider>,
  );
}

async function upload(container: HTMLElement) {
  const input = container.querySelector<HTMLInputElement>('#pdf-upload')!;
  await userEvent.upload(input, new File(['%PDF-1.4'], 'quote.pdf', { type: 'application/pdf' }));
  await screen.findByDisplayValue('Bürobedarf GmbH');
}

function lineCard(description: string): HTMLElement {
  return screen.getByDisplayValue(description).closest('.border.rounded-lg') as HTMLElement;
}

describe('the new request form shows every extraction mistake', () => {
  beforeEach(() => {
    vi.mocked(api.extraction.fromPdf).mockResolvedValue(quote as never);
    vi.mocked(api.auth.me).mockResolvedValue({ profile: { department: 'Einkauf' } } as never);
  });

  it('gives a line with only a total its price, and says where it came from', async () => {
    const { container } = renderPage();
    await upload(container);

    const fee = within(lineCard('Versandkosten'));
    const [price, amount] = fee.getAllByRole('spinbutton');
    expect(price).toHaveValue(4.9);
    expect(fee.getByText('Not found in the quote, from the line total')).toBeInTheDocument();
    expect(fee.getByText('Not found in the quote')).toBeInTheDocument();

    fireEvent.change(amount, { target: { value: '2' } });
    expect(fee.getByText('€9.80')).toBeInTheDocument();
  });

  it('flags the line that does not add up until it is fixed', async () => {
    const { container } = renderPage();
    await upload(container);

    const desk = within(lineCard('Desk'));
    expect(desk.getByText(LINE_OFF)).toBeInTheDocument();
    expect(within(lineCard('Versandkosten')).queryByText(LINE_OFF)).not.toBeInTheDocument();

    fireEvent.change(desk.getAllByRole('spinbutton')[0], { target: { value: '270' } });
    expect(desk.queryByText(LINE_OFF)).not.toBeInTheDocument();
  });

  it('lets the requester add a left-out alternative back as a line', async () => {
    const { container } = renderPage();
    await upload(container);

    await userEvent.click(screen.getByRole('button', { name: '1 alternative, not included' }));
    await userEvent.click(screen.getByRole('button', { name: 'Add as a line' }));

    expect(screen.getByDisplayValue('Desk lamp, optional')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /alternative, not included/ })).not.toBeInTheDocument();
    expect(screen.getByText('€583.90')).toBeInTheDocument();
  });

  it('puts the totals warning under the total cost', async () => {
    const { container } = renderPage();
    await upload(container);

    const warning = screen.getByText(/The lines add up to €544.90, the quote says €600.00/);
    const total = screen.getByText('Total Cost');
    expect(total.compareDocumentPosition(warning) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('keeps the department from the profile, not the quote', async () => {
    const { container } = renderPage();
    await waitFor(() => expect(screen.getByLabelText('Department')).toHaveValue('Einkauf'));
    await upload(container);

    expect(screen.getByLabelText('Department')).toHaveValue('Einkauf');
  });
});
