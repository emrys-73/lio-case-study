# Extraction eval

Measures how well the PDF quote extraction works, on real quotes, against the real OpenAI API. Nothing is mocked.

## Layout

- `cases/<id>.json`: one answer key per quote. Add a quote = add a file. `status` says if a human checked it.
- `score.py`: pure scoring, no network. Unit tests in `tests/test_eval_score.py`.
- `run.py`: runs every case through `extract_quote` (the upload path), logs every model call and the raw reply, scores it.
- `inputs/layout/`: `pdftotext -layout` text, used with `--text-source layout` to test the input step on its own.
- `results/<timestamp>_<label>/`: `runs.jsonl` (every run in full), `summary.json`, `summary.md`. Never edited by hand.

## Rules the key follows

- Total = the net cost Acme pays: items plus charges (shipping, levies), before VAT.
- Charges are order lines, so the lines add up to the total.
- Alternatives and heading-only positions are not order lines.
- Title, department and commodity group are recorded, not scored.

## Run

From `lio-procurement-app/`, with the stack up and `OPENAI_API_KEY` in `.env`:

```sh
docker compose run --rm -T -v "$PWD/../quotes:/quotes:ro" \
  backend python -m evals.extraction.run --runs 3 --label baseline
```

Options: `--model gpt-4.1`, `--text-source pypdf` (text layer only, the path before OCR), `--text-source layout`, `--case hoffmann`, `--without-group-list`, `--buyer "Acme Corp"` (the signed-in company as the app passes it; default is each quote's addressee).
The default `--text-source pdf` runs `extract_quote`, the same path as an upload: text layer, OCR, and page pictures when needed.
Each full run is 15 calls, about 370k input tokens.
