'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import * as api from '@/lib/api';
import { useCommodityGroups } from '@/lib/hooks/useCommodityGroups';
import { Button, Input, Alert, Loader } from '@/components/base';
import { AutoSetChip, AutoSetHelper, CorrectedNote, LockedGroupField, isStaff } from '@/components/CommodityAuto';
import {
  AlternativesBox,
  LineCheck,
  TotalsCheck,
  fillMissingPrice,
  markText,
  useOwnDepartment,
} from '@/components/ExtractionReview';
import {
  CatalogAddBox,
  CatalogLineNote,
  CatalogSwitchAllBar,
  freeLine,
  liveMatch,
  newLineKey,
  pickedLine,
  switchLine,
  toOrderLineInput,
  undoLine,
  useCatalogSuggest,
  type CatalogLine,
} from '@/components/CatalogSuggest';
import type { Commodity } from '@/types/database';

type OrderLine = CatalogLine;

function toFormLine(line: api.ExtractedOrderLine): OrderLine {
  return {
    key: newLineKey(),
    ...fillMissingPrice(line),
  };
}

const NOT_FOUND = 'Not found in the quote';
const CATEGORISE_DELAY_MS = 400;

function lineId(index: number): string {
  return `00000000-0000-4000-8000-${String(index).padStart(12, '0')}`;
}

async function categorise(lines: api.CategoriseLineInput[]) {
  return api.commodityGroups.categorise(lines);
}

export default function NewRequestPage() {
  const router = useRouter();
  const { data: commodityGroups } = useCommodityGroups();

  // Form state
  const [requestorName, setRequestorName] = useState('');
  const [title, setTitle] = useState('');
  const [vendorName, setVendorName] = useState('');
  const [vatId, setVatId] = useState('');
  const [department, setDepartment] = useState('');
  useOwnDepartment(setDepartment);
  const [commodityGroupId, setCommodityGroupId] = useState<number | null>(null);
  const [orderLines, setOrderLines] = useState<OrderLine[]>([]);
  const [totalCost, setTotalCost] = useState<number>(0);
  useCatalogSuggest(orderLines, setOrderLines, vendorName);

  // UI state
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [warning, setWarning] = useState('');
  const [extracting, setExtracting] = useState(false);
  const [notFound, setNotFound] = useState<string[]>([]);
  const [extraction, setExtraction] = useState<api.ExtractionResponse | undefined>();
  const [printedTotal, setPrintedTotal] = useState<number | null>(null);
  const [printedVat, setPrintedVat] = useState<number | null>(null);
  const [printedGross, setPrintedGross] = useState<number | null>(null);
  const [org, setOrg] = useState<api.MyOrganization | null>(null);
  const [commodity, setCommodity] = useState<Commodity | null>(null);
  const [savedCommodity, setSavedCommodity] = useState<Commodity | null>(null);
  const ownGroupId = useRef<number | null>(null);
  const categoriseRun = useRef(0);
  const lockedRef = useRef(false);
  const locked = Boolean(commodity?.locked && commodity.group_id);
  const staff = isStaff(org?.role, commodity ?? savedCommodity);
  const groupName = (id: number | null | undefined, fallback?: string | null) =>
    fallback || commodityGroups?.find((g) => g.id === id)?.name || (id ? `Group ${id}` : '');

  const chooseGroup = (id: number | null) => {
    ownGroupId.current = id;
    setCommodityGroupId(id);
  };

  useEffect(() => {
    Promise.resolve()
      .then(() => api.organizations.getMine())
      .then((mine) => setOrg(mine ?? null))
      .catch(() => setOrg(null));
  }, []);

  const categoriseKey = useMemo(
    () =>
      JSON.stringify(
        orderLines.map((line) => [line.positionDescription, line.amount, line.unitPrice]),
      ),
    [orderLines],
  );

  useEffect(() => {
    const run = ++categoriseRun.current;
    const lines: api.CategoriseLineInput[] = JSON.parse(categoriseKey).map(
      ([description, quantity, unitPrice]: [string, number, number], index: number) => ({
        id: lineId(index),
        description,
        quantity,
        unit_price: Number(unitPrice || 0).toFixed(2),
      }),
    );
    const release = () => {
      if (lockedRef.current) {
        lockedRef.current = false;
        setCommodityGroupId(ownGroupId.current);
      }
      setCommodity(null);
    };
    if (!lines.some((line) => line.description.trim())) {
      release();
      return;
    }
    const timer = setTimeout(() => {
      Promise.resolve()
        .then(() => categorise(lines))
        .then((result) => {
          if (run !== categoriseRun.current) return;
          const next = result?.commodity;
          if (next?.locked && next.group_id) {
            lockedRef.current = true;
            setCommodity(next);
            setCommodityGroupId(next.group_id);
          } else {
            release();
          }
        })
        .catch(() => {
          if (run === categoriseRun.current) release();
        });
    }, CATEGORISE_DELAY_MS);
    return () => clearTimeout(timer);
  }, [categoriseKey]);

  // Handle file upload and extraction
  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const uploadedFile = e.target.files?.[0];
    if (!uploadedFile) return;

    const isPdf =
      ['application/pdf', 'application/x-pdf'].includes(uploadedFile.type) ||
      uploadedFile.name.toLowerCase().endsWith('.pdf');
    if (!isPdf) {
      setError('Please upload a PDF file');
      return;
    }

    setFile(uploadedFile);
    setError('');
    setSuccess('');
    setWarning('');
    setExtraction(undefined);
    setExtracting(true);

    try {
      const extractionResult = await api.extraction.fromPdf(uploadedFile);
      
      if (!extractionResult.success || !extractionResult.data) {
        throw new Error(extractionResult.error || 'Failed to extract data');
      }

      const extracted = extractionResult.data;
      setExtraction(extractionResult);

      // Step 3: Auto-fill form (including commodity group from extraction)
      setTitle(extracted.title || '');
      setVendorName(extracted.vendorName || '');
      setVatId(extracted.vatId || '');
      setOrderLines((extracted.orderLines || []).map(toFormLine));
      setTotalCost(extracted.totalCost || 0);
      setNotFound(extractionResult.missingFields || []);
      setPrintedTotal(extractionResult.totals?.printed ?? null);
      setPrintedVat(extractionResult.totals?.vat ?? null);
      setPrintedGross(extractionResult.totals?.gross ?? null);
      
      // Set commodity group (now included in extraction)
      if (extracted.commodityGroupId) {
        ownGroupId.current = extracted.commodityGroupId;
        if (!lockedRef.current) setCommodityGroupId(extracted.commodityGroupId);
      }

      // Show warnings for missing fields
      if (extractionResult.missingFields && extractionResult.missingFields.length > 0) {
        setWarning(
          `⚠️ Could not extract: ${extractionResult.missingFields.join(', ')}. Please fill in these fields manually.`
        );
      }

      setSuccess('✓ PDF extracted successfully! Review and submit.');
      window.scrollTo({ top: 0, behavior: 'smooth' });
    } catch (err) {
      console.error('Extraction error:', err);
      setError(err instanceof Error ? err.message : 'Failed to extract data from PDF');
      window.scrollTo({ top: 0, behavior: 'smooth' });
    } finally {
      setExtracting(false);
    }
  };

  // Add order line manually
  const addOrderLine = () => {
    setOrderLines([
      ...orderLines,
      {
        key: newLineKey(),
        positionDescription: '',
        unitPrice: 0,
        amount: 1,
        unit: '',
        totalPrice: 0,
      },
    ]);
  };

  // Update order line
  const updateOrderLine = (index: number, field: keyof OrderLine, value: string | number) => {
    const updated = [...orderLines];
    updated[index] = { ...updated[index], [field]: value };
    
    // Auto-calculate total price
    if (field === 'unitPrice' || field === 'amount') {
      updated[index].totalPrice = updated[index].unitPrice * updated[index].amount;
    }
    
    setOrderLines(updated);
    
    // Update total cost
    const newTotal = updated.reduce((sum, line) => sum + line.totalPrice, 0);
    setTotalCost(newTotal);
  };

  const setLines = (updated: OrderLine[]) => {
    setOrderLines(updated);
    setTotalCost(updated.reduce((sum, line) => sum + line.totalPrice, 0));
  };
  const changeLine = (index: number, change: (line: OrderLine) => OrderLine) =>
    setLines(orderLines.map((line, i) => (i === index ? change(line) : line)));

  // Remove order line
  const removeOrderLine = (index: number) => {
    const updated = orderLines.filter((_, i) => i !== index);
    setOrderLines(updated);
    const newTotal = updated.reduce((sum, line) => sum + line.totalPrice, 0);
    setTotalCost(newTotal);
  };

  // Submit form
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setSuccess('');
    setWarning('');
    setSavedCommodity(null);

    // Validation with scroll to top on error
    if (!commodityGroupId) {
      setError('Please select a commodity group');
      window.scrollTo({ top: 0, behavior: 'smooth' });
      return;
    }

    if (orderLines.length === 0) {
      setError('Please add at least one order line');
      window.scrollTo({ top: 0, behavior: 'smooth' });
      return;
    }

    try {
      const created = await api.requests.create({
        requestorName,
        titleShortDescription: title,
        vendorName,
        vatId,
        commodityGroupId: commodityGroupId,
        totalCost,
        department,
        orderLines: orderLines.map(toOrderLineInput),
        extraction,
      });

      // Attach the original PDF (if one was uploaded) so it shows on the detail page.
      if (file) {
        try {
          await api.requests.uploadDocument(created.id, file);
        } catch {
          // Non-fatal — the request itself was created.
        }
      }

      setSavedCommodity(created?.commodity ?? null);
      setSuccess('Request created successfully! Redirecting...');
      window.scrollTo({ top: 0, behavior: 'smooth' });
      setTimeout(() => {
        router.push('/dashboard/requests');
        router.refresh();
      }, created?.commodity?.corrected ? 3000 : 1500);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create request');
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }
  };

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-semibold tracking-tight text-ink">New Procurement Request</h1>
        <p className="text-gray-600 mt-2">
          Upload a vendor offer PDF or fill in the details manually
        </p>
      </div>

      {error && <Alert variant="error" className="mb-6">{error}</Alert>}
      {warning && <Alert variant="warning" className="mb-6">{warning}</Alert>}
      {success && <Alert variant="success" className="mb-6">{success}</Alert>}
      {success && (
        <CorrectedNote
          commodity={savedCommodity}
          staff={staff}
          orgName={org?.name}
          groupName={groupName(savedCommodity?.group_id, savedCommodity?.group_name)}
          fromName={
            savedCommodity?.corrected_from_group_id
              ? groupName(savedCommodity.corrected_from_group_id)
              : null
          }
        />
      )}

      <form onSubmit={handleSubmit} className="space-y-8">
        {/* PDF Upload Section */}
        <div className="lio-card p-6">
          <h2 className="text-xl font-semibold tracking-tight text-ink mb-4">Upload Vendor Offer (Optional)</h2>
          <p className="text-sm text-gray-600 mb-4">
            Upload a PDF to automatically extract vendor details and order items
          </p>

          <div className="border-2 border-dashed border-gray-300 rounded-lg p-8 text-center hover:border-accent-deep/50 transition-colors">
            <input
              type="file"
              accept="application/pdf,.pdf"
              onChange={handleFileChange}
              className="hidden"
              id="pdf-upload"
              disabled={extracting}
            />
            <label htmlFor="pdf-upload" className="cursor-pointer">
              {extracting ? (
                <div className="flex flex-col items-center">
                  <Loader size="lg" />
                  <p className="mt-4 text-sm text-gray-600">Extracting data from PDF...</p>
                </div>
              ) : file ? (
                <div>
                  <svg
                    className="mx-auto h-12 w-12 text-green-500"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M5 13l4 4L19 7"
                    />
                  </svg>
                  <p className="mt-2 text-sm font-medium text-gray-900">{file.name}</p>
                  <p className="mt-1 text-xs text-gray-500">Click to upload a different file</p>
                </div>
              ) : (
                <div>
                  <svg
                    className="mx-auto h-12 w-12 text-gray-400"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
                    />
                  </svg>
                  <p className="mt-2 text-sm text-gray-600">
                    Click to upload or drag and drop
                  </p>
                  <p className="mt-1 text-xs text-gray-500">PDF up to 10MB</p>
                </div>
              )}
            </label>
          </div>
        </div>

        {/* Request Details */}
        <div className="lio-card p-6 space-y-4">
          <h2 className="text-xl font-semibold tracking-tight text-ink mb-4">Request Details</h2>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Input
              label="Requestor Name *"
              value={requestorName}
              onChange={(e) => setRequestorName(e.target.value)}
              required
              placeholder="John Doe"
            />

            <Input
              label="Department"
              value={department}
              onChange={(e) => setDepartment(e.target.value)}
              placeholder="IT Department"
              helperText={!department ? 'Not set on your profile' : undefined}
            />
          </div>

          <Input
            label="Title / Short Description *"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            required
            placeholder="Adobe Creative Cloud Subscription"
            helperText={notFound.includes('Title/Short Description') && !title ? NOT_FOUND : undefined}
          />
        </div>

        {/* Vendor Information */}
        <div className="lio-card p-6 space-y-4">
          <h2 className="text-xl font-semibold tracking-tight text-ink mb-4">Vendor Information</h2>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Input
              label="Vendor Name *"
              value={vendorName}
              onChange={(e) => setVendorName(e.target.value)}
              required
              placeholder="Adobe Systems"
              helperText={notFound.includes('Vendor Name') && !vendorName ? NOT_FOUND : undefined}
            />

            <Input
              label="VAT ID"
              value={vatId}
              onChange={(e) => setVatId(e.target.value)}
              placeholder="DE123456789"
              helperText={notFound.includes('VAT ID') && !vatId ? NOT_FOUND : undefined}
            />
          </div>

          <div>
            <label className="flex items-center gap-2 text-sm font-medium text-gray-700 mb-2">
              Commodity Group *
              {locked && <AutoSetChip />}
            </label>
            {locked && commodity ? (
              <>
                <LockedGroupField name={groupName(commodity.group_id, commodity.group_name)} />
                <AutoSetHelper commodity={commodity} staff={staff} orgName={org?.name} />
              </>
            ) : (
              <select
                value={commodityGroupId || ''}
                onChange={(e) => chooseGroup(e.target.value ? Number(e.target.value) : null)}
                required
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-gray-900 focus:ring-2 focus:ring-accent-deep/60 focus:border-accent-deep/40"
              >
                <option value="">
                  {commodityGroups ? 'Select a commodity group' : 'Loading...'}
                </option>
                {commodityGroups?.map((group) => (
                  <option key={group.id} value={group.id}>
                    {group.id} - {group.category} - {group.name}
                  </option>
                ))}
              </select>
            )}
          </div>
        </div>

        {/* Order Lines */}
        <div className="lio-card p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xl font-semibold tracking-tight text-ink">Order Lines *</h2>
            <Button type="button" onClick={addOrderLine} variant="outline" size="sm">
              + Add Line
            </Button>
          </div>

          <CatalogAddBox
            onPick={(article) => setLines([...orderLines, pickedLine(article)])}
            onFree={(text) => setLines([...orderLines, freeLine(text)])}
          />

          {extraction && (
            <CatalogSwitchAllBar
              lines={orderLines}
              onSwitchAll={() => setLines(orderLines.map((line) => (liveMatch(line) ? switchLine(line) : line)))}
            />
          )}

          {orderLines.length === 0 ? (
            <div className="text-center py-8 text-gray-500">
              No order lines yet. Add one to get started.
            </div>
          ) : (
            <div className="space-y-4">
              {orderLines.map((line, index) => (
                <div key={line.key} className="border border-gray-200 rounded-lg p-4">
                  <div className="flex items-start justify-between mb-4">
                    <h3 className="text-sm font-medium text-gray-700">Line {index + 1}</h3>
                    <button
                      type="button"
                      onClick={() => removeOrderLine(index)}
                      className="text-red-600 hover:text-red-700 text-sm"
                    >
                      Remove
                    </button>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
                    <div className="lg:col-span-2">
                      <Input
                        label="Description"
                        value={line.positionDescription}
                        onChange={(e) =>
                          updateOrderLine(index, 'positionDescription', e.target.value)
                        }
                        required
                        placeholder="Item description"
                      />
                    </div>

                    <Input
                      label="Unit Price (€)"
                      type="number"
                      step="0.01"
                      value={line.unitPrice}
                      onChange={(e) =>
                        updateOrderLine(index, 'unitPrice', parseFloat(e.target.value) || 0)
                      }
                      required
                      helperText={markText(line, 'unitPrice')}
                    />

                    <Input
                      label="Amount"
                      type="number"
                      step="0.01"
                      value={line.amount}
                      onChange={(e) =>
                        updateOrderLine(index, 'amount', parseFloat(e.target.value) || 1)
                      }
                      required
                      helperText={markText(line, 'amount')}
                    />

                    <Input
                      label="Unit"
                      value={line.unit}
                      onChange={(e) => updateOrderLine(index, 'unit', e.target.value)}
                      required
                      placeholder="pcs, licenses, etc."
                    />
                  </div>

                  <CatalogLineNote
                    line={line}
                    onSwitch={() => changeLine(index, switchLine)}
                    onUndo={() => changeLine(index, undoLine)}
                  />

                  <div className="mt-2 text-right">
                    <span className="text-sm text-gray-600">Total: </span>
                    <span className="text-lg font-semibold tracking-tight text-ink">
                      €{line.totalPrice.toFixed(2)}
                    </span>
                  </div>

                  <LineCheck line={line} />
                </div>
              ))}
            </div>
          )}

          <AlternativesBox
            extraction={extraction}
            onAdd={(line) => setLines([...orderLines, { ...line, key: newLineKey() }])}
          />
        </div>

        {/* Total Cost */}
        <div className="bg-accent-soft/20 border-2 border-accent/40 rounded-lg p-6">
          <div className="flex items-center justify-between">
            <span className="text-lg font-medium text-gray-900">Total Cost</span>
            <span className="text-3xl font-bold text-accent-deep">
              €{totalCost.toFixed(2)}
            </span>
          </div>
          <TotalsCheck
            totalCost={totalCost}
            printedTotal={printedTotal}
            printedVat={printedVat}
            printedGross={printedGross}
          />
        </div>

        {/* Submit */}
        <div className="flex items-center justify-end space-x-4">
          <Button
            type="button"
            variant="outline"
            onClick={() => router.back()}
          >
            Cancel
          </Button>
          <Button type="submit" size="lg">
            Create Request
          </Button>
        </div>
      </form>
    </div>
  );
}

