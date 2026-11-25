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
      token counts: 20 with a line and evidence, 1 with evidence but no
      line, 9 with neither (corrected 2026-11-24; first recorded as 21 lines
      by counting non-empty evidence instead of non-empty lines).
      *Early signal result (C4 material):* Haiku vs C1 labels 23/30. All 8
      title-filter false positives caught, 7 labelled-real companies
      rejected, 0 false "real". Too few records to call it better than the
      filter's 22/30; the error pattern (too strict, never too lenient) is
      the finding.

- [x] **C3. Label criterion 2, then the large model.** Per record: *is the line
      supported by the quoted evidence, or invented?* Then the same 30 through
      the large model and label again.
      *Done:* both models labelled on both criteria, same 30 companies.
      *Setup:* rubric `data/labels/c3_rubric.md`, written before labelling:
      a claim may rest on the quote or on the company's job titles and
      locations; one unsupported claim fails the line (g1); inferences are
      allowed only if they add no new fact (g2); a quote not found in the
      postings supports nothing (g3). `scripts/c3_review.py` checks
      mechanically whether each quote appears word for word (whitespace
      ignored, since n8n's HTML-to-text differs from the script's) and writes
      a review file that hides the model's verdict and confidence.
      *Opus run (2026-11-24):* same workflow, only `MODEL` changed. 30 calls,
      all `end_turn`, all served by Opus, input tokens identical to Haiku for
      all 30 companies. Tokens: 255,468 in, 16,878 out incl. thinking (avg
      563). Cost about $1.36 total, $0.045 per record at list price ($4 /
      $20 per 1M), about 35× Haiku. Opus writes a line far more often: 29
      lines, 1 abstention (Haiku: 20 lines, 9 abstentions), including 14
      lines for companies it calls not real.
      *Result (2026-11-24):*
      | | Haiku | Opus |
      |---|---|---|
      | written lines | 20 | 29 |
      | quotes verbatim (script) | 20 / 20 | 29 / 29 |
      | **grounded (hand label)** | **17 / 20** | **29 / 29** |
      | not grounded | 3 (all g1, unsupported claim) | 0 |
      Labels in `data/labels/c3_grounded_<model>.csv`, loaded into
      `labels_grounded`.
      *Script bug, found and fixed:* the verbatim check first reported one
      databricks quote per model as not real, and both were labelled g3.
      Both models had returned the identical 196-character quote, which two
      models would not invent independently. Cause: 7 of the 30 companies
      store double-escaped HTML (`&lt;strong&gt;`), and the script removed
      tags before decoding them. Fixed (decode, then strip tags); the script
      now refreshes its own `evidence_verbatim` column without touching
      labels. Both databricks rows re-judged by hand on the corrected basis.
      *Finding — input cleaning gap:* for those 7 companies (Viralnation,
      Retailinsights, Deliveroo, databricks, Rubrik, thequalitygroupgmbh1,
      wppmedia) both models received HTML tags as visible text, since the
      n8n conversion decoded the escaping only once. Same input for both
      models, so the comparison holds; it costs tokens and adds noise. Four
      of the seven are among the companies where a model's signal verdict
      disagreed with the C1 label: noted as an open question, not measured.
      *Signal verdicts:* both models 23 / 30 against C1 labels and agree
      with each other on 28 of 30. On 6 companies both say "not real" where
      the C1 label says real. Whether to review those labels (documented
      second pass, original labels stay the headline) is decided in C4.

- [x] **C4. The table.** Signal accuracy, share of grounded lines, tokens per
      record, cost per record, per model. Then a confidence threshold routing
      only uncertain cases to the large model, and the blended cost.
      *Done:* no empty cells, and the `evidence` failure rate reported as a
      result in its own right.
      *Decided before computing (2026-11-25):* routing rule = Haiku answers
      all 30; where Haiku's confidence is below **0.85**, Opus's answer is
      used instead (the least confident third: 10 of 30). That is the
      headline routed column. A sweep over every threshold is shown below
      it, with no "best" threshold claimed: Haiku's confidence takes only
      seven values, so choosing after the fact would fit these 30 companies.
      Signal accuracy uses the C1 labels as made, blind.
      *Outcome (2026-11-25):* `sql/eval_table.sql` recomputes everything from
      stored tokens and labels (list prices are the only typed-in values).
      | | Haiku | Opus | routed (< 0.85) |
      |---|---|---|---|
      | signal accuracy | 23 / 30 | 23 / 30 | 23 / 30 |
      | lines written | 20 | 29 | 24 |
      | grounded | 17 / 20 (85%) | 29 / 29 (100%) | 22 / 24 (92%) |
      | line without evidence | 0 | 0 | 0 |
      | abstained | 9 | 1 | 5 |
      | tokens per record in / out | 8,516 / 864 | 8,516 / 563 | 11,560 / 1,089 |
      | cost per record | $0.0013 | $0.0453 | $0.0180 |
      | sent to Opus | – | – | 10 of 30 |
      *Findings:*
      - Haiku's confidence is a weak router. Of Haiku's 3 ungrounded lines,
        two carry confidence ≥ 0.90, among its most confident answers.
        Routing the least confident third catches one of them at 40% of
        Opus's cost; removing all three needs essentially every company sent
        to Opus. Self-reported confidence did not flag the unsupported
        claims.
      - Signal accuracy is 23 / 30 at every threshold: the models agree on
        28 of 30 companies and their two disagreements cancel out.
      - Lines without evidence: 0 for every variant. The evidence failure
        the plan feared did not occur; abstention did, mostly in Haiku.
      - 30 companies, 20–29 lines per model: "3 ungrounded vs 0" is a real
        observation but a small sample, reported as counts, not rates.
      *Second look at disputed C1 labels (2026-11-25):* on 6 companies both
      models said "not real" where the blind label said real. Selected by
      query (`scripts/c1_second_look.py`), re-read against the unchanged
      rubric from postings only, logged in `data/labels/c1_second_look.csv`
      and table `labels_signal_review`; `c1_signal.csv` untouched. Not blind:
      model verdicts were known. Result: **1 of 6 changed** (MY Humancapital,
      r1 recruiter for unnamed clients), 5 kept. With reviewed labels: title
      filter 21 / 30, each model and the routed variant 24 / 30. The
      impression that all six were obvious labelling errors did not hold.
      In the five kept cases the models are wrong against the labels, and
      their stored `hiring_focus` / `team_context` show two misreadings:
      a consultancy staffing its own people on client projects read as a
      recruiter for an unnamed client (rule 1: Wavestone both models,
      prettyTELCO Opus); client-facing account roles at agencies and
      service companies read as "not mainly selling" (rule 2: Viralnation,
      wppmedia, Zefir both models, prettyTELCO Haiku). Labeller's reading:
      these firms employ the people they advertise for. Possible prompt v2
      fix (state that a consultancy is the employer of its own consultants),
      untested. Context, not
      cause: the C1 review file showed raw HTML tags for the 7
      double-escaped companies, 2 of the 6 among them.

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