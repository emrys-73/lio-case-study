# Extraction eval: fix3d-vat-and-gross-fields

- Model: `gpt-4o-mini-2024-07-18`, text from `pypdf`, 3 runs per case
- Started 2026-11-10T15:44:29+00:00

| Metric | Result |
|---|---|
| Crashes (user gets nothing) | 0/15 (0%) |
| ... of which the model reply was usable | 0 |
| Fully correct quotes | 6/15 (40%) |
| Vendor name right | 15/15 (100%) |
| VAT ID right | 12/15 (80%) |
| Total = net cost | 9/15 (60%) |
| Total kinds | {'items_only_net': 3, 'other': 3, 'net': 9} |
| Item lines found | 24/24 (100%) |
| Charge lines found (shipping, levy) | 12/15 (80%) |
| Line fields right (of found lines) | 99/99 (100%) |
| Alternatives counted as purchases | 3 |
| Extra lines | 3 |
| Lines sum to total | 15/15 (100%) |
| Avg seconds per quote | 9.4 |
| Tokens in / out | 378,225 / 3,048 |

| Case | Crashes | Fully correct | Total kind | Alternatives | Missing charges |
|---|---|---|---|---|---|
| apple-mba | 0/3 | 0/3 | items_only_net, items_only_net, items_only_net | [0, 0, 0] | [1, 1, 1] |
| dream-in-green | 0/3 | 0/3 | other, other, other | [1, 1, 1] | [0, 0, 0] |
| gaertner-gregg | 0/3 | 3/3 | net, net, net | [0, 0, 0] | [0, 0, 0] |
| hoffmann | 0/3 | 3/3 | net, net, net | [0, 0, 0] | [0, 0, 0] |
| stylegreen | 0/3 | 0/3 | net, net, net | [0, 0, 0] | [0, 0, 0] |
