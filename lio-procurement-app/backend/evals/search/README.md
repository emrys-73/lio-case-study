# Search eval

Measures the catalogue match behind `GET /articles/suggest`: one sure match or nothing. A wrong sure match is worse than none, so `wrong sure` must stay 0.

## Layout

- `cases/cases.jsonl`: 44 drafted cases (30 should match, 14 must return nothing). One row per case. Add a case = add a row, or a `cases/<id>.json` file with the same fields.
- `cases/holdout.jsonl`: 15 cases written after the word map was built and run blind once (`set: holdout`).
- `checked: false` on every row: the answer key is drafted from the real catalogue (`app/data/articles.py`) and still has to be checked by Adrian.
- `kind`: `match`, `near_miss` (same family, wrong spec), `off_catalogue`, `ambiguous` (two or more articles fit equally, so nothing is sure).
- `score.py`: pure scoring, no network. Unit tests in `tests/test_catalogue_search.py`.
- `run.py`: ranks every case against the 393 distinct catalogue descriptions, applies the sure gate, scores it.
- `results/<timestamp>_<label>/`: `runs.jsonl` (top 5 with scores per case), `summary.json`, `summary.md`. Never edited by hand.

## Scores

- `right`: sure match and it is the expected description.
- `wrong sure`: sure match that is wrong, or a match where nothing was expected. Must be 0.
- `missed`: nothing returned where a match was expected.
- `correct nothing`: nothing returned where nothing was expected.
- `top-5 hit`: expected description is in the top 5 of the ranking (what `GET /articles/search` shows).

The eval scores the description only. Which supplier's article is picked is a separate rule, tested in unit tests.

## Run

From `lio-procurement-app/`, with the stack up:

```sh
docker compose exec -T -e OPENAI_API_KEY= backend python -m evals.search.run --label words
docker compose exec -T backend python -m evals.search.run --method words --method embeddings --label compare
```

Options: `--method words|embeddings` (repeatable), `--threshold`, `--margin` (override the sure gate), `--case <id part>`.
`embeddings` needs `OPENAI_API_KEY` and calls the embedding model pinned in `app/core/config.py`; without a key it falls back to word match.

## Results 2026-11-10

| method | right | wrong sure | missed | correct nothing | top-5 hit | median ms |
|---|---|---|---|---|---|---|
| words, 44 tuned cases | 30/30 | 0 | 0 | 14/14 | 30/30 | 4.4 |
| words, 15 holdout, blind | 6/10 | 0 | 4 | 5/5 | 10/10 | 4.4 |
| words, all 59, after holdout fixes | 39/40 | 0 | 1 | 19/19 | 40/40 | 4.3 |
| embeddings, all 59, gate tuned to 0 wrong | 11/40 | 0 | 29 | 19/19 | 40/40 | 282 |

Words ships. Gate: score >= 0.48 and >= 0.05 ahead of the runner-up. It was 0.65 and 0.15, with 0 wrong on all 59 cases. Adrian lowered it on 10 Nov because a suggestion is only shown and the person switches by hand. Right stays 39/40. Two must-be-nothing cases now get a suggestion, both a real catalogue item of the right kind: "monitor 1440p" (24-inch 1440p IPS) and "Handschuhe Nitril" (safety gloves, not the lab ones). At 0.45 a wrong one gets through ("Kopierpapier A5" to book printing), so 0.48 is the floor. Embeddings put the right description first in 40/40, but near misses ("Fire extinguisher 2 kg CO2", "bolt M12x50") score as high as real matches, so a gate with 0 wrong sure only keeps 11.
