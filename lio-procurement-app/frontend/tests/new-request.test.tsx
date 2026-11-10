import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import NewRequestPage from '@/app/dashboard/new-request/page';
import * as api from '@/lib/api';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), back: vi.fn(), refresh: vi.fn() }),
}));

vi.mock('@/lib/hooks/useCommodityGroups', () => ({
  useCommodityGroups: () => ({
    data: [{ id: 45, category: 'Production', name: 'Production Machinery' }],
  }),
}));

vi.mock('@/lib/api', () => ({
  pdf: { parse: vi.fn() },
  extraction: { extract: vi.fn() },
  requests: { create: vi.fn(), uploadDocument: vi.fn() },
}));

const hoffmann = {
  success: true,
  data: {
    title: 'Grinding machine',
    vendorName: 'Hoffmann Nürnberg GmbH',
    vatId: null,
    department: null,
    orderLines: [
      { positionDescription: 'Schleifmaschine HN-GS 450', unitPrice: 15000, amount: 1, unit: 'pieces', totalPrice: 15000 },
      { positionDescription: 'Lieferung und Montage', unitPrice: null, amount: null, unit: null, totalPrice: 2000 },
      { positionDescription: 'Verpackung', unitPrice: null, amount: null, unit: null, totalPrice: null },
    ],
    totalCost: 17000,
    commodityGroupId: 45,
    commodityGroupName: 'Production Machinery',
  },
  missingFields: ['VAT ID', 'Department'],
};

function renderPage() {
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <NewRequestPage />
    </QueryClientProvider>,
  );
}

async function uploadQuote(container: HTMLElement) {
  const input = container.querySelector<HTMLInputElement>('#pdf-upload')!;
  const quote = new File(['%PDF-1.4'], 'hoffmann.pdf', { type: 'application/pdf' });
  await userEvent.upload(input, quote);
}

describe('new request from a PDF quote', () => {
  beforeEach(() => {
    vi.mocked(api.pdf.parse).mockResolvedValue({ text: 'Angebot' });
    vi.mocked(api.extraction.extract).mockResolvedValue(hoffmann as never);
  });

  it('fills the form from the extraction', async () => {
    const { container } = renderPage();
    await uploadQuote(container);

    expect(await screen.findByDisplayValue('Hoffmann Nürnberg GmbH')).toBeInTheDocument();
    expect(screen.getByDisplayValue('Schleifmaschine HN-GS 450')).toBeInTheDocument();
    expect(screen.getByDisplayValue('Lieferung und Montage')).toBeInTheDocument();
    expect(screen.getByText('€17000.00')).toBeInTheDocument();
  });

  it('lists the fields it could not find', async () => {
    const { container } = renderPage();
    await uploadQuote(container);

    expect(await screen.findByText(/Could not extract: VAT ID, Department/)).toBeInTheDocument();
  });

  it('marks an empty field as not found in the quote', async () => {
    const { container } = renderPage();
    await uploadQuote(container);

    const vatId = await screen.findByLabelText('VAT ID');
    expect(vatId).toHaveValue('');
    expect(vatId.parentElement).toHaveTextContent('Not found in the quote');
  });

  it('keeps a line whose values are empty', async () => {
    const { container } = renderPage();
    await uploadQuote(container);

    expect(await screen.findByText('€2000.00')).toBeInTheDocument();
    expect(screen.getByDisplayValue('Verpackung')).toBeInTheDocument();
    expect(screen.getAllByPlaceholderText('pcs, licenses, etc.')[1]).toHaveValue('');
  });

  it('warns when the lines do not add up to the total on the quote', async () => {
    vi.mocked(api.extraction.extract).mockResolvedValue({
      ...hoffmann,
      totals: { computed: 17000, printed: 17230, match: false },
    } as never);
    const { container } = renderPage();
    await uploadQuote(container);

    expect(
      await screen.findByText(/The lines add up to €17000.00, the quote says €17230.00/),
    ).toBeInTheDocument();
  });

  it('says nothing about totals when they match', async () => {
    vi.mocked(api.extraction.extract).mockResolvedValue({
      ...hoffmann,
      totals: { computed: 17000, printed: 17000, match: true },
    } as never);
    const { container } = renderPage();
    await uploadQuote(container);

    await screen.findByDisplayValue('Hoffmann Nürnberg GmbH');
    expect(screen.queryByText(/The lines add up to/)).not.toBeInTheDocument();
  });

  it('warns when the lines plus VAT do not make the gross on the quote', async () => {
    vi.mocked(api.extraction.extract).mockResolvedValue({
      ...hoffmann,
      totals: { computed: 17000, printed: 17000, match: true, vat: 3230, gross: 20330, grossMatch: false },
    } as never);
    const { container } = renderPage();
    await uploadQuote(container);

    expect(
      await screen.findByText(/The lines plus VAT come to €20230.00, the quote's gross is €20330.00/),
    ).toBeInTheDocument();
  });

  it('sends what the extraction returned along with the new request', async () => {
    const complete = {
      ...hoffmann,
      data: {
        ...hoffmann.data,
        orderLines: [
          { positionDescription: 'Schleifmaschine HN-GS 450', unitPrice: 15000, amount: 1, unit: 'pieces', totalPrice: 15000 },
          { positionDescription: 'Lieferung und Montage', unitPrice: 2000, amount: 1, unit: 'lump sum', totalPrice: 2000 },
        ],
      },
    };
    vi.mocked(api.extraction.extract).mockResolvedValue(complete as never);
    vi.mocked(api.requests.create).mockResolvedValue({ id: 'r1' } as never);
    const { container } = renderPage();
    await uploadQuote(container);
    await screen.findByDisplayValue('Hoffmann Nürnberg GmbH');

    await userEvent.type(screen.getByLabelText('Requestor Name *'), 'Rene');
    await userEvent.click(screen.getByRole('button', { name: 'Create Request' }));

    expect(api.requests.create).toHaveBeenCalledWith(
      expect.objectContaining({ extraction: complete, vendorName: 'Hoffmann Nürnberg GmbH' }),
    );
  });
});
