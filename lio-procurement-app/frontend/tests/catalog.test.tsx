import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import NewRequestPage from '@/app/dashboard/new-request/page';
import * as api from '@/lib/api';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), back: vi.fn(), refresh: vi.fn() }),
}));

vi.mock('@/lib/hooks/useCommodityGroups', () => ({
  useCommodityGroups: () => ({
    data: [{ id: 45, category: 'Office', name: 'Office Supplies' }],
  }),
}));

vi.mock('@/lib/api', () => ({
  extraction: { fromPdf: vi.fn() },
  requests: { create: vi.fn(), uploadDocument: vi.fn() },
  articles: { suggest: vi.fn(), search: vi.fn() },
}));

const toner: api.CatalogArticle = {
  article_number: 'LIN-00862',
  description: 'Toner cartridge black, high-yield',
  supplier_name: 'Lindqvist Supply B.V.',
  unit: 'piece',
  unit_price: 186,
  currency: 'EUR',
};

const paper: api.CatalogArticle = {
  article_number: 'LIN-00854',
  description: 'Copy paper A4 recycled 80 g',
  supplier_name: 'Lindqvist Supply B.V.',
  unit: 'pack',
  unit_price: 8.56,
  currency: 'EUR',
};

const cyan: api.CatalogArticle = {
  article_number: 'LIN-00863',
  description: 'Toner cartridge cyan',
  supplier_name: 'Lindqvist Supply B.V.',
  unit: 'piece',
  unit_price: 177,
  currency: 'EUR',
};

const catalogue: Record<string, api.CatalogArticle> = {
  'Toner schwarz XL': toner,
  'Kopierpapier A4 recycling': paper,
};

const offer = {
  success: true,
  data: {
    title: 'Printer toner',
    vendorName: 'Bürohaus Meyer GmbH',
    vatId: 'DE123456789',
    department: 'Office',
    orderLines: [
      { positionDescription: 'Toner schwarz XL', unitPrice: 240, amount: 4, unit: 'Stk', totalPrice: 960 },
      { positionDescription: 'Kopierpapier A4 recycling', unitPrice: 11.2, amount: 20, unit: 'Pck', totalPrice: 224 },
      { positionDescription: 'USB-C Kabel 2 m', unitPrice: 9.9, amount: 6, unit: 'Stk', totalPrice: 59.4 },
    ],
    totalCost: 1243.4,
    commodityGroupId: 45,
    commodityGroupName: 'Office Supplies',
  },
  missingFields: [],
};

function renderPage() {
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <NewRequestPage />
    </QueryClientProvider>,
  );
}

async function uploadOffer(container: HTMLElement) {
  const input = container.querySelector<HTMLInputElement>('#pdf-upload')!;
  await userEvent.upload(input, new File(['%PDF-1.4'], 'offer.pdf', { type: 'application/pdf' }));
  await screen.findByDisplayValue('Bürohaus Meyer GmbH');
}

async function addTypedLine(description: string) {
  await userEvent.click(screen.getByRole('button', { name: '+ Add Line' }));
  const inputs = screen.getAllByPlaceholderText('Item description');
  await userEvent.type(inputs[inputs.length - 1], description);
}

async function submit() {
  await userEvent.type(screen.getByLabelText('Requestor Name *'), 'Rene');
  if (!(screen.getByLabelText('Title / Short Description *') as HTMLInputElement).value) {
    await userEvent.type(screen.getByLabelText('Title / Short Description *'), 'Office');
  }
  if (!(screen.getByLabelText('Vendor Name *') as HTMLInputElement).value) {
    await userEvent.type(screen.getByLabelText('Vendor Name *'), 'Bürohaus Meyer GmbH');
  }
  for (const unit of screen.getAllByPlaceholderText('pcs, licenses, etc.') as HTMLInputElement[]) {
    if (!unit.value) await userEvent.type(unit, 'pcs');
  }
  const select = document.querySelector('select');
  if (select && !select.value) await userEvent.selectOptions(select, '45');
  await userEvent.click(screen.getByRole('button', { name: 'Create Request' }));
  await waitFor(() => expect(api.requests.create).toHaveBeenCalled());
  return vi.mocked(api.requests.create).mock.calls.at(-1)![0];
}

describe('catalogue suggestions on order lines', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.articles.suggest).mockImplementation(async (q: string) => ({ match: catalogue[q] ?? null }));
    vi.mocked(api.articles.search).mockResolvedValue({ items: [] });
    vi.mocked(api.extraction.fromPdf).mockResolvedValue(offer as never);
    vi.mocked(api.requests.create).mockResolvedValue({ id: 'r1' } as never);
  });

  it('shows "Did you mean" with the article and Switch on a line with a sure match', async () => {
    renderPage();
    await addTypedLine('Toner schwarz XL');

    const note = await screen.findByTestId('catalog-note', {}, { timeout: 2000 });
    expect(note).toHaveTextContent('Did you mean');
    expect(note).toHaveTextContent('Toner cartridge black, high-yield, Lindqvist Supply');
    expect(note).toHaveTextContent('€186.00');
    expect(within(note).getByRole('button', { name: 'Switch' })).toBeInTheDocument();
    expect(api.articles.suggest).toHaveBeenCalledWith('Toner schwarz XL', '');
    expect(document.body.textContent).not.toMatch(/%|maybe/i);
  });

  it('passes the vendor name to suggest when filled', async () => {
    renderPage();
    await userEvent.type(screen.getByLabelText('Vendor Name *'), 'Lindqvist');
    await addTypedLine('Toner schwarz XL');

    await screen.findByTestId('catalog-note', {}, { timeout: 2000 });
    expect(api.articles.suggest).toHaveBeenLastCalledWith('Toner schwarz XL', 'Lindqvist');
  });

  it('switches description, price and unit, and Undo restores them', async () => {
    const { container } = renderPage();
    await uploadOffer(container);

    const note = (await screen.findAllByTestId('catalog-note', {}, { timeout: 2000 }))[0];
    await userEvent.click(within(note).getByRole('button', { name: 'Switch, −€216.00' }));

    expect(screen.getByDisplayValue('Toner cartridge black, high-yield')).toBeInTheDocument();
    expect(screen.getByDisplayValue('186')).toBeInTheDocument();
    expect(screen.getByDisplayValue('piece')).toBeInTheDocument();
    expect(screen.getByDisplayValue('Bürohaus Meyer GmbH')).toBeInTheDocument();
    expect(screen.getByText('Was “Toner schwarz XL”, €240.00')).toBeInTheDocument();
    expect(screen.getByText('€744.00')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Undo' }));
    expect(screen.getByDisplayValue('Toner schwarz XL')).toBeInTheDocument();
    expect(screen.getByDisplayValue('240')).toBeInTheDocument();
    expect(screen.getAllByDisplayValue('Stk')).toHaveLength(2);
    expect(screen.queryByText(/Was “/)).not.toBeInTheDocument();
  });

  it('shows nothing on a line with no match', async () => {
    renderPage();
    await addTypedLine('Something unusual');

    await waitFor(() => expect(api.articles.suggest).toHaveBeenCalledWith('Something unusual', ''), { timeout: 2000 });
    expect(screen.queryByTestId('catalog-note')).not.toBeInTheDocument();
    expect(screen.queryByText('Did you mean')).not.toBeInTheDocument();
  });

  it('shows one Switch all bar after a PDF and switches every matched line', async () => {
    const { container } = renderPage();
    await uploadOffer(container);

    const bar = await screen.findByTestId('catalog-switch-all', {}, { timeout: 2000 });
    expect(bar).toHaveTextContent('2 of 3 in catalog');
    await userEvent.click(within(bar).getByRole('button', { name: 'Switch all, −€268.80' }));

    expect(screen.getByDisplayValue('Toner cartridge black, high-yield')).toBeInTheDocument();
    expect(screen.getByDisplayValue('Copy paper A4 recycled 80 g')).toBeInTheDocument();
    expect(screen.getByDisplayValue('USB-C Kabel 2 m')).toBeInTheDocument();
    expect(screen.getByDisplayValue('Bürohaus Meyer GmbH')).toBeInTheDocument();
    expect(screen.queryByTestId('catalog-switch-all')).not.toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: 'Undo' })).toHaveLength(2);
  });

  it('adds a filled line from the add box and a plain line from the typed text', async () => {
    vi.mocked(api.articles.search).mockResolvedValue({ items: [toner, cyan] });
    renderPage();

    const box = screen.getByLabelText('Add item');
    await userEvent.type(box, 'toner sch');
    await screen.findByRole('option', { name: /Toner cartridge black/ });
    const results = screen.getByRole('listbox');
    expect(results).toHaveTextContent('Toner cartridge black, high-yield');
    expect(results).toHaveTextContent('Lindqvist Supply');
    expect(results).toHaveTextContent('€186.00');
    expect(api.articles.search).toHaveBeenLastCalledWith('toner sch', 5);

    await userEvent.click(within(results).getByRole('option', { name: /Toner cartridge black/ }));
    expect(screen.getByDisplayValue('Toner cartridge black, high-yield')).toBeInTheDocument();
    expect(screen.getByDisplayValue('186')).toBeInTheDocument();
    expect(screen.getByDisplayValue('piece')).toBeInTheDocument();
    expect(box).toHaveValue('');

    await userEvent.type(box, 'kabelbinder');
    await userEvent.click(await screen.findByRole('option', { name: '+ “kabelbinder”' }));
    expect(screen.getByDisplayValue('kabelbinder')).toBeInTheDocument();
    expect(screen.getAllByPlaceholderText('Item description')).toHaveLength(2);
  });

  it('does not suggest on a picked line', async () => {
    vi.mocked(api.articles.search).mockResolvedValue({ items: [toner] });
    renderPage();

    await userEvent.type(screen.getByLabelText('Add item'), 'toner');
    await userEvent.click(await screen.findByRole('option', { name: /Toner cartridge black/ }));
    await new Promise((r) => setTimeout(r, 600));
    expect(api.articles.suggest).not.toHaveBeenCalled();
    expect(screen.queryByText('Did you mean')).not.toBeInTheDocument();
  });

  it('sends the catalogue status of each line with the new request', async () => {
    vi.mocked(api.articles.search).mockResolvedValue({ items: [cyan] });
    let answerUsb: (v: { match: null }) => void = () => {};
    vi.mocked(api.articles.suggest).mockImplementation((q: string) => {
      if (q === 'USB-C Kabel 2 m') return new Promise((resolve) => (answerUsb = resolve));
      return Promise.resolve({ match: catalogue[q] ?? null });
    });
    const { container } = renderPage();
    await uploadOffer(container);

    const notes = await screen.findAllByTestId('catalog-note', {}, { timeout: 2000 });
    await userEvent.click(within(notes[0]).getByRole('button', { name: /Switch/ }));
    await userEvent.type(screen.getByLabelText('Add item'), 'cyan');
    await userEvent.click(await screen.findByRole('option', { name: /Toner cartridge cyan/ }));
    await addTypedLine('Something unusual');
    await waitFor(() => expect(api.articles.suggest).toHaveBeenCalledWith('Something unusual', 'Bürohaus Meyer GmbH'), {
      timeout: 2000,
    });
    await new Promise((r) => setTimeout(r, 50));

    const payload = await submit();
    const byText = Object.fromEntries(payload.orderLines.map((l) => [l.positionDescription, l]));
    expect(byText['Toner cartridge black, high-yield'].catalog).toEqual({
      status: 'switched', article_number: 'LIN-00862', offer_price: 240, catalog_price: 186,
    });
    expect(byText['Kopierpapier A4 recycling'].catalog).toEqual({
      status: 'ignored', article_number: 'LIN-00854', offer_price: 11.2, catalog_price: 8.56,
    });
    expect(byText['Toner cartridge cyan'].catalog).toEqual({
      status: 'picked', article_number: 'LIN-00863', offer_price: null, catalog_price: 177,
    });
    expect(byText['Something unusual'].catalog).toEqual({
      status: 'no_match', article_number: null, offer_price: null, catalog_price: null,
    });
    expect(byText['USB-C Kabel 2 m']).not.toHaveProperty('catalog');
    expect(byText['USB-C Kabel 2 m']).not.toHaveProperty('key');
    answerUsb({ match: null });
  });

  it('keeps the form working when suggest and search fail', async () => {
    vi.mocked(api.articles.suggest).mockRejectedValue(new Error('404'));
    vi.mocked(api.articles.search).mockRejectedValue(new Error('404'));
    const { container } = renderPage();
    await uploadOffer(container);

    await userEvent.type(screen.getByLabelText('Add item'), 'kabel');
    await userEvent.click(await screen.findByRole('option', { name: '+ “kabel”' }));
    await waitFor(() => expect(api.articles.suggest).toHaveBeenCalled(), { timeout: 2000 });
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.queryByTestId('catalog-note')).not.toBeInTheDocument();
    expect(screen.queryByTestId('catalog-switch-all')).not.toBeInTheDocument();

    const payload = await submit();
    expect(payload.orderLines).toHaveLength(4);
    expect(payload.orderLines.every((l) => !('catalog' in l))).toBe(true);
  });
});
