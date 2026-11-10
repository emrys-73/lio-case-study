# Extraction eval: fix3b-vat-and-alternativ-headings

- Model: `gpt-4o-mini-2024-07-18`, text from `pypdf`, 3 runs per case
- Started 2026-11-10T15:38:37+00:00

| Metric | Result |
|---|---|
| Crashes (user gets nothing) | 0/15 (0%) |
| ... of which the model reply was usable | 0 |
| Fully correct quotes | 6/15 (40%) |
| Vendor name right | 15/15 (100%) |
| VAT ID right | 12/15 (80%) |
| Total = net cost | 9/15 (60%) |
| Total kinds | {'gross': 1, 'other': 5, 'net': 9} |
| Item lines found | 24/24 (100%) |
| Charge lines found (shipping, levy) | 15/15 (100%) |
| Line fields right (of found lines) | 95/105 (90%) |
| Alternatives counted as purchases | 3 |
| Extra lines | 8 |
| Lines sum to total | 10/15 (67%) |
| Avg seconds per quote | 7.6 |
| Tokens in / out | 377,895 / 3,085 |

| Case | Crashes | Fully correct | Total kind | Alternatives | Missing charges |
|---|---|---|---|---|---|
| apple-mba | 0/3 | 0/3 | gross, other, other | [0, 0, 0] | [0, 0, 0] |
| dream-in-green | 0/3 | 0/3 | other, other, other | [1, 1, 1] | [0, 0, 0] |
| gaertner-gregg | 0/3 | 3/3 | net, net, net | [0, 0, 0] | [0, 0, 0] |
| hoffmann | 0/3 | 3/3 | net, net, net | [0, 0, 0] | [0, 0, 0] |
| stylegreen | 0/3 | 0/3 | net, net, net | [0, 0, 0] | [0, 0, 0] |
