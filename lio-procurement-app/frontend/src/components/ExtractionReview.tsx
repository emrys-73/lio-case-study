'use client';

import { useEffect, useState, type Dispatch, type SetStateAction } from 'react';
import { Alert, Button } from '@/components/base';
import { grossFits } from '@/lib/totals';
import * as api from '@/lib/api';

export interface Alternative {
  positionDescription: string | null;
  totalPrice: number | null;
}

export interface LineValues {
  positionDescription: string;
  unitPrice: number;
  amount: number;
  unit: string;
  totalPrice: number;
}

function money(n: number): string {
  return `€${(Number.isFinite(n) ? n : 0).toFixed(2)}`;
}

export const NOT_IN_QUOTE = 'Not found in the quote';
export const PRICE_FROM_TOTAL = 'Not found in the quote, from the line total';

interface Mark {
  value: number;
  text: string;
}

export interface Marks {
  unitPrice?: Mark;
  amount?: Mark;
}

export type MarkedLine = LineValues & { marks?: Marks };

export function fillMissingPrice(line: api.ExtractedOrderLine): MarkedLine {
  const marks: Marks = {};
  const amount = line.amount ?? 1;
  if (line.amount == null) marks.amount = { value: amount, text: NOT_IN_QUOTE };
  let unitPrice = line.unitPrice;
  if (unitPrice == null) {
    const fromTotal = line.totalPrice != null && amount !== 0;
    unitPrice = fromTotal ? Math.round(((line.totalPrice as number) / amount) * 10000) / 10000 : 0;
    marks.unitPrice = { value: unitPrice, text: fromTotal ? PRICE_FROM_TOTAL : NOT_IN_QUOTE };
  }
  return {
    positionDescription: line.positionDescription ?? '',
    unitPrice,
    amount,
    unit: line.unit ?? '',
    totalPrice: line.totalPrice ?? unitPrice * amount,
    marks,
  };
}

export function markText(line: LineValues, field: keyof Marks): string | undefined {
  const mark = (line as MarkedLine).marks?.[field];
  return mark && line[field] === mark.value ? mark.text : undefined;
}

export function alternativesOf(extraction?: api.ExtractionResponse | null): Alternative[] {
  const data = extraction?.data as
    | (api.ExtractedVendorData & { alternatives?: Alternative[] | null })
    | undefined;
  return data?.alternatives ?? [];
}

export function alternativeLine(alternative: Alternative): LineValues {
  const price = alternative.totalPrice ?? 0;
  return {
    positionDescription: alternative.positionDescription ?? '',
    unitPrice: price,
    amount: 1,
    unit: '',
    totalPrice: price,
  };
}

export function AlternativesBox({
  extraction,
  onAdd,
}: {
  extraction?: api.ExtractionResponse | null;
  onAdd: (line: LineValues) => void;
}) {
  const [seen, setSeen] = useState({ source: extraction, added: [] as number[], open: false });
  if (seen.source !== extraction) {
    setSeen({ source: extraction, added: [], open: false });
  }
  const left = alternativesOf(extraction)
    .map((alternative, index) => ({ alternative, index }))
    .filter(({ index }) => !seen.added.includes(index));
  if (left.length === 0) return null;

  const add = (alternative: Alternative, index: number) => {
    setSeen({ ...seen, added: [...seen.added, index] });
    onAdd(alternativeLine(alternative));
  };

  return (
    <div className="mb-4 text-sm text-ink/60">
      <button
        type="button"
        aria-expanded={seen.open}
        onClick={() => setSeen({ ...seen, open: !seen.open })}
        className="hover:text-ink hover:underline underline-offset-2"
      >
        {left.length} {left.length === 1 ? 'alternative' : 'alternatives'}, not included
      </button>
      {seen.open && (
        <ul className="mt-2 space-y-2">
          {left.map(({ alternative, index }) => (
            <li
              key={index}
              className="flex items-center justify-between gap-4 rounded-lg border border-line px-3 py-2"
            >
              <span className="text-ink">{alternative.positionDescription || 'No description'}</span>
              <span className="flex flex-none items-center gap-3">
                <span>{alternative.totalPrice == null ? 'No price' : money(alternative.totalPrice)}</span>
                <Button type="button" variant="outline" size="sm" onClick={() => add(alternative, index)}>
                  Add as a line
                </Button>
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

const cents = (value: number) => Math.round(value * 100);

export function lineAddsUp(line: LineValues): boolean {
  return cents(line.unitPrice * line.amount) === cents(line.totalPrice);
}

export function LineCheck({ line }: { line: LineValues }) {
  if (lineAddsUp(line)) return null;
  return (
    <p className="mt-2 text-sm text-amber-700">
      Quantity × price isn&apos;t this line&apos;s total. Check this line.
    </p>
  );
}

export function TotalsCheck({
  totalCost,
  printedTotal,
  printedVat,
  printedGross,
}: {
  totalCost: number;
  printedTotal: number | null;
  printedVat: number | null;
  printedGross: number | null;
}) {
  if (printedGross !== null) {
    if (grossFits(totalCost, printedVat, printedGross)) return null;
    return (
      <Alert variant="warning" className="mt-4">
        The lines add up to €{totalCost.toFixed(2)} before VAT. That doesn&apos;t fit the
        quote&apos;s total of €{printedGross.toFixed(2)} with VAT. Check the lines before you
        submit.
      </Alert>
    );
  }
  if (printedTotal === null || Math.abs(totalCost - printedTotal) < 0.005) return null;
  return (
    <Alert variant="warning" className="mt-4">
      The lines add up to €{totalCost.toFixed(2)}, the quote says €{printedTotal.toFixed(2)}.
      Check the lines before you submit.
    </Alert>
  );
}

export function useOwnDepartment(setDepartment: Dispatch<SetStateAction<string>>) {
  useEffect(() => {
    let live = true;
    Promise.resolve()
      .then(() => api.auth.me())
      .then((me) => {
        const own = me?.profile?.department?.trim();
        if (live && own) setDepartment((current) => current || own);
      })
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [setDepartment]);
}
