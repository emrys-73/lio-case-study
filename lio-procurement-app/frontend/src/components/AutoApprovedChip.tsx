import type { ProcurementRequest } from '@/types/database';

type ApprovalFields = Pick<ProcurementRequest, 'approval_status' | 'approved_by'>;

export function isAutoApproved(request: ApprovalFields): boolean {
  return request.approval_status === 'approved' && request.approved_by === null;
}

export function AutoApprovedChip({ request }: { request: ApprovalFields }) {
  if (!isAutoApproved(request)) return null;
  return (
    <span
      title="Approved automatically, the total is under your company's approval limit"
      className="inline-flex px-2 py-1 text-xs font-semibold rounded-full bg-accent-soft/40 text-accent-deep"
    >
      Auto
    </span>
  );
}
