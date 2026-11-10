# Extraction eval: fix8-vat-lines-out

- Model: `gpt-4o-mini-2024-07-18`, text from `pdf`, 3 runs per case
- Started 2026-11-10T16:37:11+00:00

| Metric | Result |
|---|---|
| Crashes (user gets nothing) | 0/15 (0%) |
| ... of which the model reply was usable | 0 |
| Fully correct quotes | 10/15 (67%) |
| Vendor name right | 15/15 (100%) |
| VAT ID right | 15/15 (100%) |
| Total = net cost | 10/15 (67%) |
| Total kinds | {'net': 10, 'items_only_net': 2, 'other': 3} |
| Item lines found | 24/24 (100%) |
| Charge lines found (shipping, levy) | 13/15 (87%) |
| Line fields right (of found lines) | 101/101 (100%) |
| Alternatives counted as purchases | 3 |
| Extra lines | 3 |
| Lines sum to total | 15/15 (100%) |
| VAT amount right | 9/15 (60%) |
| Gross total right | 15/15 (100%) |
| Wrong with no warning in the form | 0/5 (0%) |
| Lines and total right but totals warning shown | 0/10 (0%) |
| Avg seconds per quote | 15.5 |
| Tokens in / out | 676,125 / 3,870 |
| OCR added text | 12/15 (80%) |
| Page pictures sent to the model | 3/15 (20%) |

| Case | Crashes | Fully correct | Total kind | Alternatives | Missing charges |
|---|---|---|---|---|---|
| apple-mba | 0/3 | 1/3 | net, items_only_net, items_only_net | [0, 0, 0] | [0, 1, 1] |
| dream-in-green | 0/3 | 0/3 | other, other, other | [1, 1, 1] | [0, 0, 0] |
| gaertner-gregg | 0/3 | 3/3 | net, net, net | [0, 0, 0] | [0, 0, 0] |
| hoffmann | 0/3 | 3/3 | net, net, net | [0, 0, 0] | [0, 0, 0] |
| stylegreen | 0/3 | 3/3 | net, net, net | [0, 0, 0] | [0, 0, 0] |
