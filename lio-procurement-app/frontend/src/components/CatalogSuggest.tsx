'use client';

import { useEffect, useRef, useState, type Dispatch, type SetStateAction } from 'react';
import * as api from '@/lib/api';
import { Button } from '@/components/base';

export type CatalogArticle = api.CatalogArticle;

interface LineValues {
  positionDescription: string;
  unitPrice: number;
  unit: string;
  totalPrice: number;
}

export type LineCatalog =
  | { kind: 'suggested'; query: string; match: CatalogArticle | null }
  | { kind: 'switched'; article: CatalogArticle; was: LineValues }
  | { kind: 'picked'; article: CatalogArticle };

export interface CatalogLine extends LineValues {
  key: string;
  amount: number;
  catalog?: LineCatalog;
}

export const SUGGEST_DELAY_MS = 400;
export const SEARCH_DELAY_MS = 250;
const MIN_SUGGEST_CHARS = 3;
const MIN_SEARCH_CHARS = 2;

let keySeed = 0;
export function newLineKey(): string {
  keySeed += 1;
  return `line-${Date.now().toString(36)}-${keySeed}`;
}

export function eur(n: number): string {
  return `€${(Number.isFinite(n) ? n : 0).toFixed(2)}`;
}

export function shortSupplier(name: string): string {
  return name.replace(/,?\s+(GmbH & Co\. KG|GmbH|B\.V\.|AG|SE|Ltd\.?|S\.A\.|KG|Inc\.?|LLC)$/, '');
}

function trimmed(line: { positionDescription: string }): string {
  return (line.positionDescription ?? '').trim();
}

export function liveMatch(line: CatalogLine): CatalogArticle | null {
  const c = line.catalog;
  if (c?.kind !== 'suggested' || !c.match) return null;
  return c.query === trimmed(line) ? c.match : null;
}

export function lineSaving(line: CatalogLine, article: CatalogArticle): number {
  return (line.unitPrice - article.unit_price) * line.amount;
}

function needsSuggest(line: CatalogLine): boolean {
  const text = trimmed(line);
  if (text.length < MIN_SUGGEST_CHARS) return false;
  if (!line.catalog) return true;
  return line.catalog.kind === 'suggested' && line.catalog.query !== text;
}

export function switchLine<L extends CatalogLine>(line: L): L {
  const article = liveMatch(line);
  if (!article) return line;
  return {
    ...line,
    positionDescription: article.description,
    unitPrice: article.unit_price,
    unit: article.unit,
    totalPrice: article.unit_price * line.amount,
    catalog: {
      kind: 'switched',
      article,
      was: {
        positionDescription: line.positionDescription,
        unitPrice: line.unitPrice,
        unit: line.unit,
        totalPrice: line.totalPrice,
      },
    },
  };
}

export function undoLine<L extends CatalogLine>(line: L): L {
  const c = line.catalog;
  if (c?.kind !== 'switched') return line;
  return {
    ...line,
    ...c.was,
    catalog: { kind: 'suggested', query: c.was.positionDescription.trim(), match: c.article },
  };
}

export function pickedLine(article: CatalogArticle): CatalogLine {
  return {
    key: newLineKey(),
    positionDescription: article.description,
    unitPrice: article.unit_price,
    amount: 1,
    unit: article.unit,
    totalPrice: article.unit_price,
    catalog: { kind: 'picked', article },
  };
}

export function freeLine(text: string): CatalogLine {
  return {
    key: newLineKey(),
    positionDescription: text,
    unitPrice: 0,
    amount: 1,
    unit: '',
    totalPrice: 0,
  };
}

export function catalogPayload(line: CatalogLine): api.OrderLineCatalog | undefined {
  const c = line.catalog;
  if (!c) return undefined;
  if (c.kind === 'picked') {
    return { status: 'picked', article_number: c.article.article_number, offer_price: null, catalog_price: c.article.unit_price };
  }
  if (c.kind === 'switched') {
    return {
      status: 'switched',
      article_number: c.article.article_number,
      offer_price: c.was.unitPrice,
      catalog_price: c.article.unit_price,
    };
  }
  if (c.query !== trimmed(line)) return undefined;
  if (!c.match) return { status: 'no_match', article_number: null, offer_price: null, catalog_price: null };
  return {
    status: 'ignored',
    article_number: c.match.article_number,
    offer_price: line.unitPrice,
    catalog_price: c.match.unit_price,
  };
}

export function toOrderLineInput(line: CatalogLine): api.OrderLineInput {
  const input: api.OrderLineInput = {
    positionDescription: line.positionDescription,
    unitPrice: line.unitPrice,
    amount: line.amount,
    unit: line.unit,
    totalPrice: line.totalPrice,
  };
  const catalog = catalogPayload(line);
  if (catalog) input.catalog = catalog;
  return input;
}

export function useCatalogSuggest<L extends CatalogLine>(
  lines: L[],
  setLines: Dispatch<SetStateAction<L[]>>,
  vendorName: string,
) {
  const vendor = useRef(vendorName);
  const pending = useRef(new Map<string, { query: string; timer: ReturnType<typeof setTimeout> }>());

  useEffect(() => {
    vendor.current = vendorName;
  }, [vendorName]);

  const wantedKey = JSON.stringify(lines.filter(needsSuggest).map((line) => [line.key, trimmed(line)]));

  useEffect(() => {
    const want = new Map<string, string>(JSON.parse(wantedKey));
    for (const [key, entry] of pending.current) {
      if (want.get(key) !== entry.query) {
        clearTimeout(entry.timer);
        pending.current.delete(key);
      }
    }
    for (const [key, query] of want) {
      if (pending.current.has(key)) continue;
      const timer = setTimeout(() => {
        Promise.resolve()
          .then(() => api.articles.suggest(query, vendor.current))
          .then((result) => {
            const match = result?.match ?? null;
            setLines((prev) =>
              prev.map((line) =>
                line.key === key && trimmed(line) === query && needsSuggest(line)
                  ? { ...line, catalog: { kind: 'suggested', query, match } }
                  : line,
              ),
            );
          })
          .catch(() => undefined)
          .finally(() => {
            if (pending.current.get(key)?.timer === timer) pending.current.delete(key);
          });
      }, SUGGEST_DELAY_MS);
      pending.current.set(key, { query, timer });
    }
  }, [wantedKey, setLines]);

  useEffect(() => {
    const map = pending.current;
    return () => {
      for (const entry of map.values()) clearTimeout(entry.timer);
      map.clear();
    };
  }, []);
}

const chipCatalog =
  'inline-flex items-center px-2.5 py-0.5 text-xs font-semibold rounded-full bg-accent-soft/40 text-accent-deep';
const chipOff = 'inline-flex items-center gap-1.5 px-2.5 py-0.5 text-xs font-semibold rounded-full bg-gray-100 text-gray-600';

export function CatalogLineNote({
  line,
  onSwitch,
  onUndo,
}: {
  line: CatalogLine;
  onSwitch: () => void;
  onUndo: () => void;
}) {
  const c = line.catalog;
  if (c?.kind === 'picked') {
    return (
      <div className="mt-3 flex items-center gap-2" data-testid="catalog-note">
        <span className={chipCatalog}>Catalog</span>
        <span className="text-xs text-ink/55">{shortSupplier(c.article.supplier_name)}</span>
      </div>
    );
  }
  if (c?.kind === 'switched') {
    return (
      <div className="mt-3 flex flex-wrap items-center gap-2" data-testid="catalog-note">
        <span className={chipCatalog}>Catalog</span>
        <span className={chipOff}>
          Was “{c.was.positionDescription}”, {eur(c.was.unitPrice)}
        </span>
        <span className="flex-1" />
        <Button type="button" variant="outline" size="sm" onClick={onUndo}>
          Undo
        </Button>
      </div>
    );
  }
  const match = liveMatch(line);
  if (!match) return null;
  const saving = lineSaving(line, match);
  return (
    <div
      className="mt-3 flex flex-wrap items-center gap-2 rounded-lg border border-accent/40 bg-accent-soft/20 px-3 py-2"
      data-testid="catalog-note"
    >
      <span className="text-xs text-ink/55">Did you mean</span>
      <span className={chipCatalog}>
        {match.description}, {shortSupplier(match.supplier_name)}
      </span>
      <span className="text-sm">
        {line.unitPrice > 0 && line.unitPrice !== match.unit_price && (
          <span className="mr-2 text-ink/45 line-through">{eur(line.unitPrice)}</span>
        )}
        <span className="font-semibold text-accent-deep">{eur(match.unit_price)}</span>
        {match.unit && <span className="text-ink/55"> / {match.unit}</span>}
      </span>
      <span className="flex-1" />
      <Button type="button" variant="accent" size="sm" onClick={onSwitch}>
        {saving > 0 ? `Switch, −${eur(saving)}` : 'Switch'}
      </Button>
    </div>
  );
}

export function CatalogSwitchAllBar({
  lines,
  onSwitchAll,
}: {
  lines: CatalogLine[];
  onSwitchAll: () => void;
}) {
  const open = lines.filter((line) => liveMatch(line));
  if (open.length === 0) return null;
  const onCatalog = lines.filter((line) => line.catalog?.kind === 'switched' || line.catalog?.kind === 'picked').length;
  const saving = open.reduce((sum, line) => sum + Math.max(0, lineSaving(line, liveMatch(line)!)), 0);
  return (
    <div
      className="mb-4 flex flex-wrap items-center gap-3 rounded-lg border border-accent/40 bg-accent-soft/30 px-4 py-3 text-ink"
      data-testid="catalog-switch-all"
    >
      <span className="flex-1 text-sm">
        <b>
          {open.length + onCatalog} of {lines.length}
        </b>{' '}
        in catalog
      </span>
      <Button type="button" variant="accent" size="sm" onClick={onSwitchAll}>
        {saving > 0 ? `Switch all, −${eur(saving)}` : 'Switch all'}
      </Button>
    </div>
  );
}

export function CatalogAddBox({
  onPick,
  onFree,
}: {
  onPick: (article: CatalogArticle) => void;
  onFree: (text: string) => void;
}) {
  const [text, setText] = useState('');
  const [items, setItems] = useState<CatalogArticle[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const run = useRef(0);
  const query = text.trim();

  useEffect(() => {
    const current = ++run.current;
    if (query.length < MIN_SEARCH_CHARS) {
      setItems([]);
      return;
    }
    const timer = setTimeout(() => {
      Promise.resolve()
        .then(() => api.articles.search(query, 5))
        .then((result) => {
          if (current === run.current) setItems(result?.items ?? []);
        })
        .catch(() => {
          if (current === run.current) setItems([]);
        });
    }, SEARCH_DELAY_MS);
    return () => clearTimeout(timer);
  }, [query]);

  const reset = () => {
    setText('');
    setItems([]);
    setActive(0);
  };
  const pick = (article: CatalogArticle) => {
    onPick(article);
    reset();
  };
  const addFree = () => {
    if (!query) return;
    onFree(query);
    reset();
  };

  const showDrop = open && query.length > 0;
  const count = items.length + 1;

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      if (!query) return;
      if (active < items.length) pick(items[active]);
      else addFree();
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      setOpen(true);
      setActive((a) => Math.min(a + 1, count - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActive((a) => Math.max(a - 1, 0));
    } else if (e.key === 'Escape') {
      setOpen(false);
    }
  };

  const rowClass = (i: number) =>
    `w-full flex items-center gap-3 px-3 py-2 text-left text-sm border-t border-gray-100 first:border-t-0 hover:bg-accent-soft/30 ${
      i === active ? 'bg-accent-soft/30' : ''
    }`;

  return (
    <div className="relative mb-4">
      <input
        type="text"
        value={text}
        aria-label="Add item"
        placeholder="Add item"
        autoComplete="off"
        aria-autocomplete="list"
        aria-controls="catalog-add-results"
        onChange={(e) => {
          setText(e.target.value);
          setActive(0);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onKeyDown={onKeyDown}
        className="w-full px-3 py-2 border border-gray-300 rounded-lg text-gray-900 focus:ring-2 focus:ring-accent-deep/60 focus:border-accent-deep/40"
      />
      {showDrop && (
        <div
          id="catalog-add-results"
          role="listbox"
          className="absolute z-20 mt-1 w-full overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm"
        >
          {items.map((article, i) => (
            <button
              key={`${article.article_number}-${i}`}
              type="button"
              role="option"
              aria-selected={i === active}
              className={rowClass(i)}
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => pick(article)}
            >
              <span className="flex-1 min-w-0">
                <span className="block truncate text-ink">{article.description}</span>
                <span className="block text-xs text-ink/55">{shortSupplier(article.supplier_name)}</span>
              </span>
              <span className="font-semibold text-ink whitespace-nowrap">
                {eur(article.unit_price)}
                {article.unit && <span className="font-normal text-ink/55"> / {article.unit}</span>}
              </span>
            </button>
          ))}
          <button
            type="button"
            role="option"
            aria-selected={active === items.length}
            className={`${rowClass(items.length)} text-ink/55`}
            onMouseDown={(e) => e.preventDefault()}
            onClick={addFree}
          >
            + “{query}”
          </button>
        </div>
      )}
    </div>
  );
}
