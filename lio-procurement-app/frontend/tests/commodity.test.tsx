import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import NewRequestPage from '@/app/dashboard/new-request/page';
import RequestDetailPage from '@/app/dashboard/requests/[id]/page';
import * as api from '@/lib/api';
import type { Commodity } from '@/types/database';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), back: vi.fn(), refresh: vi.fn() }),
  useParams: () => ({ id: 'r1' }),
}));

vi.mock('next/link', () => ({
  default: ({ children, href }: { children: React.ReactNode; href: string }) => <a href={href}>{children}</a>,
}));

vi.mock('@/lib/hooks/useCommodityGroups', () => ({
  useCommodityGroups: () => ({
    data: [
      { id: 11, category: 'Engineering', name: 'Electrical Engineering' },
      { id: 118, category: 'Production', name: 'Fasteners and Fixings' },
    ],
  }),
}));

vi.mock('@/lib/api', () => ({
  extraction: { fromPdf: vi.fn() },
  requests: {
    create: vi.fn(),
    update: vi.fn(),
    uploadDocument: vi.fn(),
    get: vi.fn(),
    getActivity: vi.fn(),
    documentUrl: vi.fn(),
  },
  organizations: { getMine: vi.fn() },
  commodityGroups: { categorise: vi.fn() },
}));

const ruleHit: Commodity = {
  group_id: 11,
  group_name: 'Electrical Engineering',
  source: 'rule',
  rule_id: 'r-1',
  rule_position: 1,
  matched_keyword: 'kabelbinder',
  matched_line: 'Kabelbinder 200 mm',
  reason: "Booked under Electrical Engineering in Acme's ledger",
  locked: true,
  can_override: false,
  corrected: false,
  corrected_from_group_id: null,
};

const noHit: Commodity = {
  ...ruleHit,
  group_id: null,
  group_name: null,
  source: 'none',
  rule_id: null,
  rule_position: null,
  matched_keyword: null,
  matched_line: null,
  reason: null,
  locked: false,
};

function signedInAs(role: 'requester' | 'buyer' | 'admin') {
  vi.mocked(api.organizations.getMine).mockResolvedValue({
    id: 'o1', name: 'Acme', slug: 'acme', role, created_at: '', updated_at: '',
  });
}

function categoriseReturns(commodity: Commodity) {
  vi.mocked(api.commodityGroups.categorise).mockResolvedValue({ lines: [], commodity });
}

function renderNew() {
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <NewRequestPage />
    </QueryClientProvider>,
  );
}

async function addLine(description: string) {
  await userEvent.click(screen.getByRole('button', { name: '+ Add Line' }));
  await userEvent.type(screen.getByPlaceholderText('Item description'), description);
}

describe('commodity group set automatically on a new request', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    signedInAs('requester');
    categoriseReturns(ruleHit);
  });

  it('locks the field for a requester and never mentions a rule', async () => {
    renderNew();
    await addLine('Kabelbinder 200 mm');

    expect(await screen.findByText('Set automatically', {}, { timeout: 2000 })).toBeInTheDocument();
    expect(screen.getByTestId('commodity-locked')).toHaveTextContent('Electrical Engineering');
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
    expect(
      await screen.findByText('Set by Acme for this item. Not right? Ask a buyer.'),
    ).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/rule/i);
  });

  it('sends the lines to categorise', async () => {
    renderNew();
    await addLine('Kabelbinder 200 mm');

    await waitFor(() => expect(api.commodityGroups.categorise).toHaveBeenCalled(), { timeout: 2000 });
    const lines = vi.mocked(api.commodityGroups.categorise).mock.calls.at(-1)![0];
    expect(lines).toEqual([
      { id: expect.any(String), description: 'Kabelbinder 200 mm', quantity: 1, unit_price: '0.00' },
    ]);
  });

  it('shows a buyer which rule set the group', async () => {
    signedInAs('buyer');
    renderNew();
    await addLine('Kabelbinder 200 mm');

    expect(
      await screen.findByText(
        `Acme rule 1, "kabelbinder" in "Kabelbinder 200 mm". Booked under Electrical Engineering in Acme's ledger.`,
        {},
        { timeout: 2000 },
      ),
    ).toBeInTheDocument();
    expect(screen.getByText('Set automatically')).toBeInTheDocument();
  });

  it('leaves the field editable when no rule fits', async () => {
    categoriseReturns(noHit);
    renderNew();
    await addLine('Something else');

    await waitFor(() => expect(api.commodityGroups.categorise).toHaveBeenCalled(), { timeout: 2000 });
    const select = screen.getByRole('combobox');
    await userEvent.selectOptions(select, '118');
    expect(select).toHaveValue('118');
    expect(screen.queryByText('Set automatically')).not.toBeInTheDocument();
  });

  it('unlocks and keeps the own choice when a later answer has no rule', async () => {
    renderNew();
    await userEvent.selectOptions(screen.getByRole('combobox'), '118');
    await addLine('Kabelbinder 200 mm');
    await screen.findByText('Set automatically', {}, { timeout: 2000 });

    categoriseReturns(noHit);
    await userEvent.clear(screen.getByPlaceholderText('Item description'));
    await userEvent.type(screen.getByPlaceholderText('Item description'), 'Stuhl');

    await waitFor(() => expect(screen.getByRole('combobox')).toHaveValue('118'), { timeout: 2000 });
    expect(screen.queryByText('Set automatically')).not.toBeInTheDocument();
  });

  it('keeps working when categorise fails', async () => {
    vi.mocked(api.commodityGroups.categorise).mockRejectedValue(new Error('Not Found'));
    renderNew();
    await addLine('Kabelbinder 200 mm');

    await waitFor(() => expect(api.commodityGroups.categorise).toHaveBeenCalled(), { timeout: 2000 });
    const select = screen.getByRole('combobox');
    await userEvent.selectOptions(select, '11');
    expect(select).toHaveValue('11');
    expect(screen.queryByText('Set automatically')).not.toBeInTheDocument();
  });

  it('keeps working when categorise is missing', async () => {
    vi.mocked(api.commodityGroups.categorise).mockImplementation(() => {
      throw new TypeError('categorise is not a function');
    });
    renderNew();
    await addLine('Kabelbinder 200 mm');

    await waitFor(() => expect(api.commodityGroups.categorise).toHaveBeenCalled(), { timeout: 2000 });
    expect(screen.getByRole('combobox')).toBeEnabled();
  });
});

describe('quiet note after a corrected save', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    categoriseReturns(ruleHit);
  });

  async function saveWith(commodity: Commodity) {
    vi.mocked(api.requests.create).mockResolvedValue({ id: 'r1', commodity } as never);
    const { container } = renderNew();
    await addLine('Kabelbinder 200 mm');
    await screen.findByText('Set automatically', {}, { timeout: 2000 });
    fireEvent.submit(container.querySelector('form')!);
    await waitFor(() => expect(api.requests.create).toHaveBeenCalled());
    await screen.findByText(/Request created successfully/);
  }

  it('tells a requester the group was set automatically', async () => {
    signedInAs('requester');
    await saveWith({ ...ruleHit, corrected: true, corrected_from_group_id: 118 });

    expect(
      screen.getByText('Commodity group set automatically to Electrical Engineering.'),
    ).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/rule/i);
  });

  it('tells a buyer what was sent and which rule corrected it', async () => {
    signedInAs('buyer');
    await saveWith({ ...ruleHit, corrected: true, corrected_from_group_id: 118 });

    expect(
      screen.getByText('Commodity group set automatically to Electrical Engineering.'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('Sent Fasteners and Fixings, corrected by Acme rule 1. Logged.'),
    ).toBeInTheDocument();
  });

  it('says nothing when the save was not corrected', async () => {
    signedInAs('requester');
    await saveWith(ruleHit);

    expect(screen.queryByText(/Commodity group set automatically to/)).not.toBeInTheDocument();
  });
});

describe('request detail', () => {
  const request = {
    id: 'r1',
    title: 'Cable ties',
    requestor_name: 'Lena Vogt',
    vendor_name: 'Würth',
    vat_id: null,
    department: null,
    status: 'open',
    approval_status: 'pending',
    total_cost: 480,
    commodity_group_id: 11,
    commodity_groups: { id: 11, category: 'Engineering', name: 'Electrical Engineering', created_at: '' },
    order_lines: [],
    commodity: ruleHit,
  };

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.requests.get).mockResolvedValue(request as never);
    vi.mocked(api.requests.getActivity).mockResolvedValue([]);
    vi.mocked(api.requests.documentUrl).mockResolvedValue(null);
  });

  it('shows a requester the group was set automatically, without the rule', async () => {
    signedInAs('requester');
    render(<RequestDetailPage />);

    expect(await screen.findByText('Set automatically')).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/rule/i);
  });

  it('shows a buyer the rule beside the group', async () => {
    signedInAs('buyer');
    render(<RequestDetailPage />);

    expect(await screen.findByText('Set automatically')).toBeInTheDocument();
    expect(
      screen.getByText(
        `Acme rule 1, "kabelbinder" in "Kabelbinder 200 mm". Booked under Electrical Engineering in Acme's ledger.`,
      ),
    ).toBeInTheDocument();
  });

  it('shows the group as before when nothing set it automatically', async () => {
    signedInAs('buyer');
    vi.mocked(api.requests.get).mockResolvedValue({ ...request, commodity: undefined } as never);
    render(<RequestDetailPage />);

    expect(await screen.findByText('Engineering, Electrical Engineering')).toBeInTheDocument();
    expect(screen.queryByText('Set automatically')).not.toBeInTheDocument();
  });

  it('shows the quiet note after an edit is corrected', async () => {
    signedInAs('requester');
    vi.mocked(api.requests.update).mockResolvedValue({
      ...request,
      commodity: { ...ruleHit, corrected: true, corrected_from_group_id: 118 },
    } as never);
    render(<RequestDetailPage />);

    await userEvent.click(await screen.findByRole('button', { name: 'Edit' }));
    await userEvent.click(screen.getByRole('button', { name: 'Save Changes' }));

    expect(
      await screen.findByText('Commodity group set automatically to Electrical Engineering.'),
    ).toBeInTheDocument();
  });
});
