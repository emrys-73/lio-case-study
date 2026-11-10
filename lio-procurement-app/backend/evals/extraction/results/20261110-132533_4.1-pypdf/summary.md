# Extraction eval: 4.1-pypdf

- Model: `gpt-4.1`, text from `pypdf`, 3 runs per case
- Started 2026-11-10T13:25:33+00:00

| Metric | Result |
|---|---|
| Crashes (user gets nothing) | 6/15 (40%) |
| ... of which the model reply was usable | 6 |
| Fully correct quotes | 0/15 (0%) |
| Vendor name right | 9/15 (60%) |
| VAT ID right | 9/15 (60%) |
| Total = net cost | 0/15 (0%) |
| Total kinds | {'gross': 9} |
| Item lines found | 12/24 (50%) |
| Charge lines found (shipping, levy) | 6/15 (40%) |
| Line fields right (of found lines) | 48/48 (100%) |
| Alternatives counted as purchases | 9 |
| Extra lines | 9 |
| Lines sum to total | 0/15 (0%) |
| Avg seconds per quote | 3.4 |
| Tokens in / out | 371,256 / 4,673 |

| Case | Crashes | Fully correct | Total kind | Alternatives | Missing charges |
|---|---|---|---|---|---|
| apple-mba | 0/3 | 0/3 | gross, gross, gross | [0, 0, 0] | [1, 1, 1] |
| dream-in-green | 0/3 | 0/3 | gross, gross, gross | [1, 1, 1] | [0, 0, 0] |
| gaertner-gregg | 0/3 | 0/3 | gross, gross, gross | [2, 2, 2] | [0, 0, 0] |
| hoffmann | 3/3 | 0/3 | crash, crash, crash | [None, None, None] | [None, None, None] |
| stylegreen | 3/3 | 0/3 | crash, crash, crash | [None, None, None] | [None, None, None] |

Errors:
- `1 validation error for ExtractedVendorData
vatId
  Input should be a valid string [type=string_type, input_value=None, input_type=NoneType]
    For further info`
