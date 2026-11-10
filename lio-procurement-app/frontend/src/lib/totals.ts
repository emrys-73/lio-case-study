const VAT_RATES = [0.19, 0.07];
const ROUNDING = 0.02;

const cents = (value: number) => Math.round(value * 100);

export function grossFits(net: number, vat: number | null, gross: number): boolean {
  const netC = cents(net);
  const grossC = cents(gross);
  if (vat !== null && netC + cents(vat) === grossC) return true;
  if (!vat && netC === grossC) return true;
  return VAT_RATES.some((rate) => Math.abs(netC * (1 + rate) - grossC) <= cents(ROUNDING));
}
