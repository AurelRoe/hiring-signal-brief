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

- [x] **A1. n8n + Postgres via Docker Compose.** Two services, named volume for
      Postgres, host port off the default to avoid collisions.
      *Done:* n8n reachable in the browser, `psql` connects.

- [x] **A2. Schema.** `sql/schema.sql`: one table for company results, one for
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

- [x] **B2. Fetch.** HTTP Request node paginating until an empty page. No
      filtering yet.
      *Done:* raw job count in n8n roughly matches the spike, and the real size
      of the feed is known — the API may only serve a time window, not the
      ~11,800 the website advertises.
      *Outcome (2026-11-20):* 17 requests (16 pages of jobs + the empty end
      page), 3,901 jobs, 3,681 unique slugs. The API
      serves about a third of what the website advertises, so it is a window,
      not the full board. ~5.6% duplicates across pages (the feed shifts while
      paging; the spike saw the same: 1,500 → 1,432 unique), so B3's dedupe is
      required, not defensive. The window's length in days is not measured.

- [x] **B3. Filter → dedupe → aggregate → pre-filter.** Title match per the role
      definition, dedupe on company + job id, aggregate per company (role count,
      first/latest posting, cities), keep companies with ≥2 roles.
      *Done — the Day 1 goal:* a list of real companies with signal counts in
      Postgres.
      *Outcome (2026-11-22):* 15 requests (14 pages + empty end page), 3,200
      unique jobs, 513 target-role jobs, 276 companies with ≥1 role, **69 with
      ≥2** (39 with ≥3, 15 with ≥5). All jobs are stored, not only matches; ≥2
      is a query, not a deletion. Dedupe is on `slug` (Arbeitnow's job id).
      Two additions to the plan: a `Create snapshot` node (jobs need a
      `snapshot_id`) and a `Drop empty page` filter (the empty end page became
      one blank item after Split Out; it drops exactly 1 item per run).
      *Findings:*
      - The feed shrank from 3,901 to 3,200 jobs in two days. Consistent with a
        moving window; not verified.
      - Five "companies" post identical template titles ("Graduate sales
        executive at …"): Privateequityinsights 21, Hrtechx 9, United Media 9,
        Retailinsights 9, Cfoinsights 9 — 57 roles, likely one sender. Not
        filtered in the pipeline; decide in C1 how many may enter the sample.
      - `cities` holds raw `location` text ("Paris, France; Bordeaux, …"), not
        clean city names. Cosmetic, left as is.

- [x] **B4. Freeze the snapshot.** Export qualifying companies and their job text
      to `data/raw/`. Everything downstream reads this file, never a live fetch.
      *Done:* the file exists, row count stable, and it is not committed.
      *Outcome (2026-11-22):* `data/raw/eval_snapshot_3.json` (2.2 MB) via
      `sql/export_snapshot.sql`, from snapshot 3: 69 companies, 306 target-role
      postings with full description (raw HTML), no empty descriptions,
      `role_count` matches the exported postings for every company. Exported
      twice, byte-identical. SHA-256:
      `00bf78c8a4de3cfcee6aa16a94982a7aa6ffcb858193913398630099d1c21ee1`.
      Done in `psql`, not n8n: the n8n container cannot see the repo.
      The older `arbeitnow_20261120T133926Z.json` in the same folder is the
      B1 spike's raw feed, not the evaluation input.

---

## Phase C — Models and evaluation

Two model paths, cheap and expensive, with a measured trade-off between them.

- [x] **C1. Sample and label criterion 1.** 30 companies from the snapshot.
      By hand, from the postings: *is this company actually hiring for that
      function?* No model involved yet.
      *Done:* 30 rows, each a yes/no; every "no" names the deciding rule
      from `data/labels/c1_rubric.md`.
      *Outcome (2026-11-23):* sample drawn by `scripts/c1_sample.py`
      (deterministic, seed `c1`, refuses a snapshot with a different hash).
      Labels in `data/labels/c1_signal.csv`, loaded into `labels_signal`.
      **22 of 30 correct, 8 false positives**, so the title pre-filter's
      precision is 73% (95% Wilson interval roughly 56–86%: 30 records is a
      small sample). False positives by rule: r2 not a sales/marketing role 3,
      r4 duplicate posting 3, r3 intern 2, r1 recruiter 0. Rubric refined
      during labelling: rule 2 now requires selling/marketing to be the main
      job, not one task among several.

- [x] **C2. LLM node, small model.** Structured JSON: `hiring_focus`,
      `team_context`, `personalization_line`, `confidence`, `evidence`. A
      response with an empty `evidence` field is logged as a failure, never
      repaired. Prompt versioned as a file. Output language fixed in the prompt,
      since input may be French.
      *Done:* 30 valid records with token counts for all of them.
      *Outcome (2026-11-23):* n8n workflow `Brief companies` →
      `claude-haiku-5-5`, effort `medium`, structured output (JSON schema),
      prompt `prompts/brief_v1.md` (run_label `v1`), no refusal fallback.
      n8n reads the frozen snapshot and the prompt through a read-only mount.
      30 calls, 30 briefs, all `end_turn`, all served by Haiku. Tokens:
      255,468 in (avg 8,516), 25,922 out incl. thinking (avg 864). Cost about
      $0.04 total, $0.0013 per record at list price ($0.10 / $0.50 per 1M).
      Two additions to the plan: an `is_real_signal` field (the model's own
      verdict on criterion 1, so signal accuracy can differ per model) and
      evidence ordered before the line in the schema.
      *Plan correction:* "empty `evidence` = failure" conflated two cases.
      9 of 30 records have empty evidence, but all 9 also have an empty line
      and `is_real_signal = false`: the model abstained rather than wrote an
      unsupported line. Lines written without evidence: 0. Stored data stays
      as returned (status `no_evidence`, never repaired); C4 reports
      "evidence missing on a written line" and "abstained" as separate rows.
      The "30 valid records" criterion is therefore read as 30 records with
      token counts, 21 of them with a line and evidence.
      *Early signal result (C4 material):* Haiku vs C1 labels 23/30. All 8
      title-filter false positives caught, 7 labelled-real companies
      rejected, 0 false "real". Too few records to call it better than the
      filter's 22/30; the error pattern (too strict, never too lenient) is
      the finding.

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