# Extraction eval: fix1-schema-accepts-empty

- Model: `gpt-4o-mini-2024-07-18`, text from `pypdf`, 3 runs per case
- Started 2026-11-10T15:20:27+00:00

| Metric | Result |
|---|---|
| Crashes (user gets nothing) | 0/15 (0%) |
| ... of which the model reply was usable | 0 |
| Fully correct quotes | 0/15 (0%) |
| Vendor name right | 12/15 (80%) |
| VAT ID right | 12/15 (80%) |
| Total = net cost | 0/15 (0%) |
| Total kinds | {'gross': 12, 'other': 3} |
| Item lines found | 24/24 (100%) |
| Charge lines found (shipping, levy) | 6/15 (40%) |
| Line fields right (of found lines) | 87/87 (100%) |
| Alternatives counted as purchases | 9 |
| Extra lines | 9 |
| Lines sum to total | 0/15 (0%) |
| Avg seconds per quote | 6.0 |
| Tokens in / out | 371,256 / 3,669 |

| Case | Crashes | Fully correct | Total kind | Alternatives | Missing charges |
|---|---|---|---|---|---|
| apple-mba | 0/3 | 0/3 | gross, gross, gross | [0, 0, 0] | [1, 1, 1] |
| dream-in-green | 0/3 | 0/3 | gross, gross, gross | [1, 1, 1] | [1, 1, 1] |
| gaertner-gregg | 0/3 | 0/3 | gross, gross, gross | [2, 2, 2] | [0, 0, 0] |
| hoffmann | 0/3 | 0/3 | other, other, gross | [0, 0, 0] | [0, 0, 0] |
| stylegreen | 0/3 | 0/3 | gross, other, gross | [0, 0, 0] | [1, 1, 1] |
