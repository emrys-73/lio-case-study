# Extraction eval: fix4-buyer-name

- Model: `gpt-4o-mini-2024-07-18`, text from `pypdf`, 3 runs per case
- Started 2026-11-10T15:33:04+00:00

| Metric | Result |
|---|---|
| Crashes (user gets nothing) | 0/15 (0%) |
| ... of which the model reply was usable | 0 |
| Fully correct quotes | 6/15 (40%) |
| Vendor name right | 15/15 (100%) |
| VAT ID right | 12/15 (80%) |
| Total = net cost | 6/15 (40%) |
| Total kinds | {'items_only_net': 9, 'net': 6} |
| Item lines found | 24/24 (100%) |
| Charge lines found (shipping, levy) | 15/15 (100%) |
| Line fields right (of found lines) | 105/105 (100%) |
| Alternatives counted as purchases | 3 |
| Extra lines | 6 |
| Lines sum to total | 6/15 (40%) |
| Avg seconds per quote | 7.8 |
| Tokens in / out | 377,175 / 2,986 |

| Case | Crashes | Fully correct | Total kind | Alternatives | Missing charges |
|---|---|---|---|---|---|
| apple-mba | 0/3 | 0/3 | items_only_net, items_only_net, items_only_net | [0, 0, 0] | [0, 0, 0] |
| dream-in-green | 0/3 | 0/3 | items_only_net, items_only_net, items_only_net | [1, 1, 1] | [0, 0, 0] |
| gaertner-gregg | 0/3 | 3/3 | net, net, net | [0, 0, 0] | [0, 0, 0] |
| hoffmann | 0/3 | 3/3 | net, net, net | [0, 0, 0] | [0, 0, 0] |
| stylegreen | 0/3 | 0/3 | items_only_net, items_only_net, items_only_net | [0, 0, 0] | [0, 0, 0] |
