import type { MemberRole } from '@/lib/api';
import type { Commodity } from '@/types/database';

export function isStaff(role: MemberRole | null | undefined, commodity?: Commodity | null): boolean {
  if (role) return role !== 'requester';
  return Boolean(commodity?.can_override);
}

function orgLabel(orgName: string | null | undefined): string {
  return orgName?.trim() || 'your organisation';
}

export function ruleLine(commodity: Commodity, orgName: string | null | undefined): string {
  let text = `${orgLabel(orgName)} rule${commodity.rule_position ? ` ${commodity.rule_position}` : ''}`;
  if (commodity.matched_keyword) {
    text += `, "${commodity.matched_keyword}"`;
    if (commodity.matched_line) text += ` in "${commodity.matched_line}"`;
  }
  text += '.';
  const reason = commodity.reason?.trim().replace(/\.+$/, '');
  if (reason) text += ` ${reason}.`;
  return text;
}

export function AutoSetChip() {
  return (
    <span className="inline-flex items-center px-2.5 py-0.5 text-xs font-semibold rounded-full bg-accent-soft/40 text-accent-deep">
      Set automatically
    </span>
  );
}

function LockIcon() {
  return (
    <svg className="w-4 h-4 flex-none text-accent-deep" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
      <rect x="5" y="11" width="14" height="10" rx="2" strokeWidth={2} />
      <path d="M8 11V7a4 4 0 018 0v4" strokeWidth={2} strokeLinecap="round" />
    </svg>
  );
}

export function LockedGroupField({ name }: { name: string }) {
  return (
    <div
      aria-readonly="true"
      data-testid="commodity-locked"
      className="w-full flex items-center gap-2 px-3 py-2 border border-gray-300 rounded-lg bg-gray-50 text-gray-900"
    >
      <LockIcon />
      <span>{name}</span>
    </div>
  );
}

export function AutoSetHelper({
  commodity,
  staff,
  orgName,
}: {
  commodity: Commodity;
  staff: boolean;
  orgName: string | null | undefined;
}) {
  return (
    <p className="mt-1.5 text-xs text-ink/55">
      {staff
        ? ruleLine(commodity, orgName)
        : `Set by ${orgLabel(orgName)} for this item. Not right? Ask a buyer.`}
    </p>
  );
}

export function CorrectedNote({
  commodity,
  staff,
  orgName,
  groupName,
  fromName,
}: {
  commodity: Commodity | null | undefined;
  staff: boolean;
  orgName: string | null | undefined;
  groupName: string | null | undefined;
  fromName: string | null | undefined;
}) {
  if (!commodity?.corrected || !groupName) return null;
  return (
    <div className="mb-6 space-y-1" data-testid="commodity-corrected">
      <p className="text-sm text-ink/55">Commodity group set automatically to {groupName}.</p>
      {staff && fromName && (
        <p className="text-sm text-ink/55">
          Sent {fromName}, corrected by {orgLabel(orgName)} rule
          {commodity.rule_position ? ` ${commodity.rule_position}` : ''}. Logged.
        </p>
      )}
    </div>
  );
}
