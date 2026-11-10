import { render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ApprovalsPage from '@/app/dashboard/approvals/page';
import RequestsPage from '@/app/dashboard/requests/page';
import * as api from '@/lib/api';
import type { ProcurementRequestWithDetails } from '@/types/database';

vi.mock('next/link', () => ({
  default: ({ children, href }: { children: React.ReactNode; href: string }) => <a href={href}>{children}</a>,
}));

vi.mock('@/lib/hooks/useCommodityGroups', () => ({
  useCommodityGroups: () => ({
    data: [{ id: 15, category: 'Office & Administration', name: 'Office Equipment' }],
  }),
}));

vi.mock('@/lib/api', () => ({
  requests: { list: vi.fn(), decideApproval: vi.fn() },
  organizations: { getMine: vi.fn() },
}));

function request(
  id: string,
  title: string,
  approval: Pick<ProcurementRequestWithDetails, 'approval_status' | 'approved_by' | 'approved_at'>,
  total: number,
): ProcurementRequestWithDetails {
  return {
    id,
    user_id: 'u-requester',
    organization_id: 'org-acme',
    created_by: 'u-requester',
    requestor_name: 'Rene Requester',
    title,
    vendor_name: 'Würth',
    vat_id: null,
    commodity_group_id: 15,
    department: null,
    status: 'open',
    total_cost: total,
    created_at: '2026-11-10T09:00:00Z',
    updated_at: '2026-11-10T09:00:00Z',
    order_lines: [],
    commodity_groups: {
      id: 15,
      category: 'Office & Administration',
      name: 'Office Equipment',
      created_at: '2026-01-01T00:00:00Z',
    },
    ...approval,
  };
}

const autoApproved = request(
  'r-auto',
  'Desk lamp',
  { approval_status: 'approved', approved_by: null, approved_at: '2026-11-10T09:00:00Z' },
  1999.99,
);
const buyerApproved = request(
  'r-buyer',
  'Standing desk',
  { approval_status: 'approved', approved_by: 'u-buyer', approved_at: '2026-11-10T10:00:00Z' },
  1500,
);
const pending = request(
  'r-pending',
  'CNC mill',
  { approval_status: 'pending', approved_by: null, approved_at: null },
  45000,
);

function rowOf(title: string): HTMLElement {
  const row = screen.getByText(title).closest<HTMLElement>('tr, .divide-y > div');
  if (!row) throw new Error(`no row for ${title}`);
  return row;
}

describe('Auto chip on the request list', () => {
  beforeEach(() => {
    vi.mocked(api.requests.list).mockResolvedValue([autoApproved, buyerApproved, pending]);
  });

  it('shows Auto on a request approved under the limit', async () => {
    render(<RequestsPage />);
    await screen.findByText('Desk lamp');
    expect(within(rowOf('Desk lamp')).getByText('Auto')).toBeInTheDocument();
    expect(within(rowOf('Desk lamp')).getByText('Approved')).toBeInTheDocument();
  });

  it('shows no Auto on a request a buyer approved', async () => {
    render(<RequestsPage />);
    await screen.findByText('Standing desk');
    expect(within(rowOf('Standing desk')).getByText('Approved')).toBeInTheDocument();
    expect(within(rowOf('Standing desk')).queryByText('Auto')).not.toBeInTheDocument();
  });

  it('shows no Auto on a pending request', async () => {
    render(<RequestsPage />);
    await screen.findByText('CNC mill');
    expect(within(rowOf('CNC mill')).getByText('Pending')).toBeInTheDocument();
    expect(within(rowOf('CNC mill')).queryByText('Auto')).not.toBeInTheDocument();
    expect(screen.getAllByText('Auto')).toHaveLength(1);
  });
});

describe('Auto chip on the approvals page', () => {
  beforeEach(() => {
    vi.mocked(api.requests.list).mockResolvedValue([autoApproved, buyerApproved, pending]);
    vi.mocked(api.organizations.getMine).mockResolvedValue({
      id: 'org-acme',
      name: 'Acme',
      slug: 'acme',
      role: 'buyer',
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    });
  });

  it('marks only the auto-approved request among the decided ones', async () => {
    render(<ApprovalsPage />);
    await screen.findByText('Desk lamp');
    expect(within(rowOf('Desk lamp')).getByText('Auto')).toBeInTheDocument();
    expect(within(rowOf('Standing desk')).queryByText('Auto')).not.toBeInTheDocument();
    expect(within(rowOf('CNC mill')).queryByText('Auto')).not.toBeInTheDocument();
    expect(screen.getAllByText('Auto')).toHaveLength(1);
  });
});
