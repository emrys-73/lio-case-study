# Extraction eval: fix12-totals-block-rows

- Model: `gpt-4o-mini-2024-07-18`, text from `pdf`, 3 runs per case
- Started 2026-11-10T17:01:30+00:00

| Metric | Result |
|---|---|
| Crashes (user gets nothing) | 0/15 (0%) |
| ... of which the model reply was usable | 0 |
| Fully correct quotes | 12/15 (80%) |
| Vendor name right | 15/15 (100%) |
| VAT ID right | 15/15 (100%) |
| Total = net cost | 12/15 (80%) |
| Total kinds | {'net': 12, 'other': 3} |
| Item lines found | 24/24 (100%) |
| Charge lines found (shipping, levy) | 15/15 (100%) |
| Line fields right (of found lines) | 105/105 (100%) |
| Alternatives counted as purchases | 3 |
| Extra lines | 3 |
| Lines sum to total | 15/15 (100%) |
| VAT amount right | 15/15 (100%) |
| Gross total right | 15/15 (100%) |
| Wrong with no warning in the form | 0/3 (0%) |
| Lines and total right but totals warning shown | 0/12 (0%) |
| Avg seconds per quote | 19.0 |
| Tokens in / out | 678,213 / 5,409 |
| OCR added text | 12/15 (80%) |
| Page pictures sent to the model | 3/15 (20%) |

| Case | Crashes | Fully correct | Total kind | Alternatives | Missing charges |
|---|---|---|---|---|---|
| apple-mba | 0/3 | 3/3 | net, net, net | [0, 0, 0] | [0, 0, 0] |
| dream-in-green | 0/3 | 0/3 | other, other, other | [1, 1, 1] | [0, 0, 0] |
| gaertner-gregg | 0/3 | 3/3 | net, net, net | [0, 0, 0] | [0, 0, 0] |
| hoffmann | 0/3 | 3/3 | net, net, net | [0, 0, 0] | [0, 0, 0] |
| stylegreen | 0/3 | 3/3 | net, net, net | [0, 0, 0] | [0, 0, 0] |
