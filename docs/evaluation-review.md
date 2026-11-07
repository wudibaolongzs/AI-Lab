# Evaluation review and latency

Collection never supplies human judgments. Export a blank worksheet (including already graded positions):

```sh
python -B -m evals.review export evals/tencent-paired-results.json reviews.csv
python -B -m evals.review import evals/tencent-paired-results.json reviews.csv --output reviewed.json
python -B -m evals.score reviewed.json --require-complete
```

Each row is keyed by `sample_id`, `level`, `side`. Only local and actual cloud hints require review; fallbacks and errors are excluded. Keep `hint` and `case_id` unchanged. A human reviewer enters exactly `true` or `false` into `evidence_ok`, `actionable`, and `answer_leaked`; blank remains JSON null and pending. Invalid values, duplicate/unknown/missing rows and changed text/cases are rejected before output is written. Import requires a separate output path and never changes the raw report.

Export prefixes report-controlled cells beginning with spreadsheet formula characters, whitespace/control characters, or an apostrophe with one apostrophe. Import removes that transport prefix before exact identity/text checks; literal initial apostrophes are doubled and restored. Keep this prefix unchanged when editing the CSV. The raw JSON text remains unchanged.

Optional `--reuse-local-from evals/local-baseline.json` reuses existing boolean local verdicts only where sample ID, level, side, hint text and case ID match exactly; it fills only blank fields. This is explicit opt-in, not a new human review. Cloud verdicts are never reused. Without this option all blanks remain pending.

Latency summaries include median, nearest-rank P95 (`sorted[ceil(.95*n)-1]`) and maximum in milliseconds for local, cloud, fallback and error groups. Empty groups have null statistics, singletons have identical values for all three. The scorer recomputes and checks every supplied metric, while historical reports lacking P95/max remain accepted. These timings describe recorded attempts, not production service guarantees.

Browser checks use `npm ci`, `npx playwright install chromium`, then `npm run test:browser`. The isolated web server runs on port 8020 with all provider keys blank and provider AgentArts, so no paid provider request can occur. Provider badges are tested with intercepted fixture responses; these are wiring checks and carry no cloud quality evidence.

Local verification: 28 evaluation unit tests passed. The initial Chromium run could not launch because its executable was absent; the browser download stalled. All 10 browser assertions passed using installed Microsoft Edge via PowerShell `$env:PLAYWRIGHT_CHANNEL='msedge'; npm run test:browser`. The default and CI configuration continue to use Playwright Chromium; omit `PLAYWRIGHT_CHANNEL` for that run.

