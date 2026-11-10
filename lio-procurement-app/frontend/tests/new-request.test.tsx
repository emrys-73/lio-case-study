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
});
