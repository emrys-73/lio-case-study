# Extraction eval: fix7-ocr-and-page-pictures

- Model: `gpt-4o-mini-2024-07-18`, text from `pdf`, 3 runs per case
- Started 2026-11-10T15:55:33+00:00

| Metric | Result |
|---|---|
| Crashes (user gets nothing) | 0/15 (0%) |
| ... of which the model reply was usable | 0 |
| Fully correct quotes | 7/15 (47%) |
| Vendor name right | 15/15 (100%) |
| VAT ID right | 15/15 (100%) |
| Total = net cost | 9/15 (60%) |
| Total kinds | {'gross': 3, 'other': 3, 'net': 9} |
| Item lines found | 24/24 (100%) |
| Charge lines found (shipping, levy) | 15/15 (100%) |
| Line fields right (of found lines) | 95/105 (90%) |
| Alternatives counted as purchases | 3 |
| Extra lines | 6 |
| Lines sum to total | 10/15 (67%) |
| VAT amount right | 9/15 (60%) |
| Gross total right | 15/15 (100%) |
| Wrong with no warning in the form | 0/8 (0%) |
| Avg seconds per quote | 14.6 |
| Tokens in / out | 972,993 / 4,747 |
| OCR added text | 9/15 (60%) |
| Page pictures sent to the model | 6/15 (40%) |

| Case | Crashes | Fully correct | Total kind | Alternatives | Missing charges |
|---|---|---|---|---|---|
| apple-mba | 0/3 | 0/3 | gross, gross, gross | [0, 0, 0] | [0, 0, 0] |
| dream-in-green | 0/3 | 0/3 | other, other, other | [1, 1, 1] | [0, 0, 0] |
| gaertner-gregg | 0/3 | 3/3 | net, net, net | [0, 0, 0] | [0, 0, 0] |
| hoffmann | 0/3 | 3/3 | net, net, net | [0, 0, 0] | [0, 0, 0] |
| stylegreen | 0/3 | 1/3 | net, net, net | [0, 0, 0] | [0, 0, 0] |
