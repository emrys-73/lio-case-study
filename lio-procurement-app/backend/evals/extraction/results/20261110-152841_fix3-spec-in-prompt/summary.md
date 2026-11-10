# Extraction eval: fix3-spec-in-prompt

- Model: `gpt-4o-mini-2024-07-18`, text from `pypdf`, 3 runs per case
- Started 2026-11-10T15:28:41+00:00

| Metric | Result |
|---|---|
| Crashes (user gets nothing) | 0/15 (0%) |
| ... of which the model reply was usable | 0 |
| Fully correct quotes | 6/15 (40%) |
| Vendor name right | 12/15 (80%) |
| VAT ID right | 12/15 (80%) |
| Total = net cost | 6/15 (40%) |
| Total kinds | {'items_only_net': 9, 'net': 6} |
| Item lines found | 24/24 (100%) |
| Charge lines found (shipping, levy) | 15/15 (100%) |
| Line fields right (of found lines) | 105/105 (100%) |
| Alternatives counted as purchases | 3 |
| Extra lines | 6 |
| Lines sum to total | 6/15 (40%) |
| Avg seconds per quote | 13.0 |
| Tokens in / out | 375,921 / 3,042 |

| Case | Crashes | Fully correct | Total kind | Alternatives | Missing charges |
|---|---|---|---|---|---|
| apple-mba | 0/3 | 0/3 | items_only_net, items_only_net, items_only_net | [0, 0, 0] | [0, 0, 0] |
| dream-in-green | 0/3 | 0/3 | items_only_net, items_only_net, items_only_net | [1, 1, 1] | [0, 0, 0] |
| gaertner-gregg | 0/3 | 3/3 | net, net, net | [0, 0, 0] | [0, 0, 0] |
| hoffmann | 0/3 | 3/3 | net, net, net | [0, 0, 0] | [0, 0, 0] |
| stylegreen | 0/3 | 0/3 | items_only_net, items_only_net, items_only_net | [0, 0, 0] | [0, 0, 0] |
