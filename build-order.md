# Build Order

Working plan for the project. Four phases. Each stage has a definition of done.

Ordering principles, since three stages sit earlier than feels natural:

1. **Token logging before the first LLM call.** Retrofitting it means re-running
   every record, and that one costs money.
2. **Labels before model output.** Once you have read a confident-sounding
   answer, your own label is anchored to it and the accuracy number stops
   meaning anything.
3. **Freeze the input before any model runs.** The feed changes daily. Both
   models must score the same 30 companies or the cost comparison is not a
   comparison.

---

## Phase A — Infrastructure

No data, no models. Services that come up and a schema that holds results.

- [ ] **A1. n8n + Postgres via Docker Compose.** Two services, named volume for
      Postgres, host port off the default to avoid collisions.
      *Done:* n8n reachable in the browser, `psql` connects.

- [ ] **A2. Schema.** `sql/schema.sql`: one table for company results, one for
      token usage per LLM call (model, prompt tokens, completion tokens,
      company, timestamp). The usage table exists now, not in Phase C.
      *Done:* applies cleanly against an empty database.

---

## Phase B — Data

- [x] **B1. Feasibility spike.** `scripts/feasibility.py` against the live API.
      *Outcome:* 1,500 jobs (~13% of the feed), 245 role matches, 158 companies
      with ≥1 target role, 45 with ≥2. Enough companies exist. Also killed the
      DACH filter (no country field, ~80% of matches dropped for nothing) and
      exposed the `growth`/`revenue`/`marketing` false positives now excluded in
      the role definition. The script is finished; it does not get polished.

- [ ] **B2. Fetch.** HTTP Request node paginating until an empty page. No
      filtering yet.
      *Done:* raw job count in n8n roughly matches the spike, and the real size
      of the feed is known — the API may only serve a time window, not the
      ~11,800 the website advertises.

- [ ] **B3. Filter → dedupe → aggregate → pre-filter.** Title match per the role
      definition, dedupe on company + job id, aggregate per company (role count,
      first/latest posting, cities), keep companies with ≥2 roles.
      *Done — the Day 1 goal:* a list of real companies with signal counts in
      Postgres.

- [ ] **B4. Freeze the snapshot.** Export qualifying companies and their job text
      to `data/raw/`. Everything downstream reads this file, never a live fetch.
      *Done:* the file exists, row count stable, and it is not committed.

---

## Phase C — Models and evaluation

Two model paths, cheap and expensive, with a measured trade-off between them.

- [ ] **C1. Sample and label criterion 1.** 30 companies from the snapshot.
      By hand, from the postings: *is this company actually hiring for that
      function?* No model involved yet.
      *Done:* 30 rows, each a yes/no with a one-line reason.

- [ ] **C2. LLM node, small model.** Structured JSON: `hiring_focus`,
      `team_context`, `personalization_line`, `confidence`, `evidence`. A
      response with an empty `evidence` field is logged as a failure, never
      repaired. Prompt versioned as a file. Output language fixed in the prompt,
      since input may be French.
      *Done:* 30 valid records with token counts for all of them.

- [ ] **C3. Label criterion 2, then the large model.** Per record: *is the line
      supported by the quoted evidence, or invented?* Then the same 30 through
      the large model and label again.
      *Done:* both models labelled on both criteria, same 30 companies.

- [ ] **C4. The table.** Signal accuracy, share of grounded lines, tokens per
      record, cost per record, per model. Then a confidence threshold routing
      only uncertain cases to the large model, and the blended cost.
      *Done:* no empty cells, and the `evidence` failure rate reported as a
      result in its own right.

---

## Phase D — Surface

- [ ] **D1. CSV export.** Export node over the results table.
      *Done:* a file a salesperson could actually open.

- [ ] **D2. README.** The table at the top, then what the numbers mean and where
      each model failed.
      *Done:* someone who has never seen the repo understands the result from the
      README alone.

- [ ] **D3. Claude Skill — cuttable.** `SKILL.md` (quality rules, when to output
      nothing rather than guess) + `scripts/brief.py` for `/signal-brief
      <company>`.
      *Done:* a brief for one company, same rules the pipeline applies.

The cost/accuracy table and the grounding rate are the deliverable. Everything
else exists to make them credible.

---

## Risk notes

- **Pagination may be capped.** B2 either confirms the feed is large or shows the
  API serves a window. If the latter, the 30-company set still holds at ~13% of
  the feed, so this is a README caveat, not a blocker.
- **Empty `evidence` fields** are the one failure that breaks the grounding
  metric. If the small model omits the field often, that is a finding about the
  small model — report the rate, don't prompt around it until it is measured.
- **One role definition, two consumers.** The n8n filter node and
  `scripts/brief.py` must match. If they drift, the Skill answers differently
  than the pipeline and the demo contradicts the table.
- **Snapshot hygiene.** `data/raw/` stays gitignored; the full feed with job
  descriptions runs to hundreds of MB.
- **Scope.** Phase C carries the weight. If time disappears, it comes out of
  Phase D, and D3 goes first.