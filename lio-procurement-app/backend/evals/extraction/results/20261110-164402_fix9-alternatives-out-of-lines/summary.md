# Extraction eval: fix9-alternatives-out-of-lines

- Model: `gpt-4o-mini-2024-07-18`, text from `pdf`, 3 runs per case
- Started 2026-11-10T16:44:02+00:00

| Metric | Result |
|---|---|
| Crashes (user gets nothing) | 0/15 (0%) |
| ... of which the model reply was usable | 0 |
| Fully correct quotes | 12/15 (80%) |
| Vendor name right | 15/15 (100%) |
| VAT ID right | 15/15 (100%) |
| Total = net cost | 13/15 (87%) |
| Total kinds | {'items_only_net': 2, 'net': 13} |
| Item lines found | 24/24 (100%) |
| Charge lines found (shipping, levy) | 13/15 (87%) |
| Line fields right (of found lines) | 99/101 (98%) |
| Alternatives counted as purchases | 0 |
| Extra lines | 0 |
| Lines sum to total | 14/15 (93%) |
| VAT amount right | 9/15 (60%) |
| Gross total right | 15/15 (100%) |
| Wrong with no warning in the form | 1/3 (33%) |
| Lines and total right but totals warning shown | 0/13 (0%) |
| Avg seconds per quote | 11.8 |
| Tokens in / out | 676,125 / 3,845 |
| OCR added text | 12/15 (80%) |
| Page pictures sent to the model | 3/15 (20%) |

| Case | Crashes | Fully correct | Total kind | Alternatives | Missing charges |
|---|---|---|---|---|---|
| apple-mba | 0/3 | 1/3 | items_only_net, net, items_only_net | [0, 0, 0] | [1, 0, 1] |
| dream-in-green | 0/3 | 3/3 | net, net, net | [0, 0, 0] | [0, 0, 0] |
| gaertner-gregg | 0/3 | 3/3 | net, net, net | [0, 0, 0] | [0, 0, 0] |
| hoffmann | 0/3 | 3/3 | net, net, net | [0, 0, 0] | [0, 0, 0] |
| stylegreen | 0/3 | 2/3 | net, net, net | [0, 0, 0] | [0, 0, 0] |
