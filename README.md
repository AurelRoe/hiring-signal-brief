# Hiring Signal Brief

Turns public job postings into qualified company signals with an
evidence-backed personalization line — then measures whether the output
is actually true, and what it cost.

Built as a portfolio project. The pipeline is the apparatus; **the
evaluation is the result.**

> **Status: evaluation complete, project work in progress.** Pipeline,
> frozen snapshot, hand labels and both model runs are done. Still to
> come: a CSV export and a Claude Skill for single-company briefs.

## Result

| | small model<br>`claude-haiku-5-5` | large model<br>`claude-opus-5-5` | routed<br>Haiku, Opus where Haiku's confidence < 0.85 |
|---|---|---|---|
| signal accuracy (vs. blind hand labels) | 23 / 30 | 23 / 30 | 23 / 30 |
| lines written | 20 | 29 | 24 |
| **lines grounded in their evidence** | **17 / 20** | **29 / 29** | **22 / 24** |
| line written without evidence | 0 | 0 | 0 |
| no line written (abstained) | 10 | 1 | 6 |
| tokens per record (in / out) | 8,516 / 864 | 8,516 / 563 | 11,560 / 1,089 |
| **cost per record** | **$0.0013** | **$0.0453** | **$0.0180** |

**Baseline without any model:** the rule-based title filter alone is
right for 22 of 30 companies (73%; 95% Wilson interval roughly 56–86%).

Measured on 30 hand-labelled companies against a frozen data snapshot;
both models received byte-identical input (identical input token counts
for all 30). Every number is recomputed from stored tokens and labels by
[sql/eval_table.sql](sql/eval_table.sql). Cost uses Anthropic's list
prices at the time of the runs; output tokens include the model's
thinking. With 30 records, one record is about 3 percentage points: a gap
of one or two records between two columns is not a result.

### What the numbers say

- **The models differ on grounding, not on the signal.** Both reach
  23 / 30 on the signal and agree with each other on 28 of 30 companies.
  Opus grounded every one of its 29 lines; 3 of Haiku's 20 lines contain
  a claim its quote does not support.
- **Opus costs about 35× as much per record** ($0.045 vs $0.0013).
- **Self-reported confidence is a weak router.** Two of Haiku's three
  ungrounded lines carry confidence ≥ 0.90, among its most confident
  answers. Routing the least confident third to Opus catches one of them
  at 40% of Opus's cost; catching all three means sending nearly every
  company to Opus. The threshold (0.85) was fixed before the results were
  computed; the full sweep is in the query output, with no "best"
  threshold claimed.
- **Haiku declines far more often.** It wrote no line for 10 companies,
  Opus for 1. Opus writes a line even for companies it calls not worth
  contacting.
- **Both models make the same kind of error: they reject real hiring at
  consultancies and agencies.** Both rejected all 8 companies the title
  filter wrongly let through, but also 6 companies the hand labels call
  real. A documented second look at those 6 changed one label (a
  recruiter posting for unnamed clients) and confirmed five. With the
  reviewed labels: title filter 21 / 30, every model variant 24 / 30. The
  blind labels remain the headline. The models' own stated reasons show
  two misreadings behind the five errors:
  - **A consultancy staffing its own people on client projects read as a
    recruiter posting for someone else** (rubric rule 1): Wavestone (both
    models), prettyTELCO (Opus).
  - **Client-facing account roles at agencies and service companies read
    as "not mainly selling"** (rubric rule 2): Viralnation, wppmedia,
    Zefir (both models), prettyTELCO (Haiku).

  These are errors against the labels, not extra caution: the companies
  employ the people they advertise for, in roles the rubric counts. A
  sentence in the prompt stating that a consultancy is the employer of
  its own consultants might fix the first pattern; that is untested.

## Why two accuracy numbers instead of one

Most "AI enrichment" demos report a single quality figure. That hides
the error type that matters:

1. **Is the signal correct?** Is this company actually hiring for that
   function? A wrong signal wastes a sales rep's time.
2. **Is the line grounded?** Is the personalization line supported by
   the text the model quoted, or did the model invent it? A fabricated
   line that reads plausibly gets sent to a real prospect.

The second is the dangerous one, and it is only measurable because every
LLM response must return an `evidence` field quoting the source text it
relied on. Without that field, grounding cannot be checked at all.

### Missing evidence is not one thing

The plan counted every empty `evidence` field as a failure. The first
run showed two different cases behind it:

- **A line written without evidence** — the real failure: a claim that
  cannot be checked. Both models: 0.
- **No line written** — the model judged the company not worth
  contacting and wrote nothing. Haiku: 10 (9 with no quote either, 1
  with a quote but no line), all with `is_real_signal = false`. Opus: 1.

Counting the second as a failure would punish the model for declining
to guess. The stored data is left exactly as returned; the two cases are
reported as separate rows.

## Pipeline

Two n8n workflows, both started by hand. The evaluation runs against a
frozen snapshot, so there is no schedule: a daily trigger is what a
production version would add, not what a measurement needs.

```
Fetch Arbeitnow   (n8n/fetch-arbeitnow.json)
  -> create snapshot row (provenance for everything below)
  -> HTTP request: Arbeitnow API, paginated until an empty page
  -> split into jobs, drop the empty end page, dedupe on job id
  -> tag: title match against target roles, normalised company key
  -> Postgres: every job, plus one aggregate row per company
               (role count, first/latest posting, cities)

Freeze            (sql/export_snapshot.sql)
  -> companies with >= 2 target roles + their postings
     -> data/raw/eval_snapshot_3.json, SHA-256 recorded       <- no LLM yet

Brief companies   (n8n/brief-companies.json)
  -> read the frozen snapshot and the prompt file (read-only mount)
  -> per company: postings as plain text, identical descriptions sent once
  -> Claude API, structured JSON { is_real_signal, hiring_focus,
                                   team_context, evidence,
                                   personalization_line, confidence }
  -> Postgres: the brief + token usage per call (failed calls too)
```

The pre-filter before the LLM step is where the token cost is saved. It
is deliberately cheap and rule-based: a title match and a count, nothing
that needs a model. The CSV export is not built yet.

## Signal definition

A company qualifies when it has **two or more open target roles**. The
assumption: a company posting multiple sales or marketing positions is
building out that function, and that is a reason to reach out.

Target roles are matched on job title, case-insensitive:

```
sales, vertrieb, account executive, account manager, sdr, bdr,
business development, marketing, kundenberater, außendienst,
inside sales, pre-sales, partner manager
```

`growth` and `revenue` are excluded on purpose — they matched
engineering roles ("Growth Engineer", "Revenue Operations"). `marketing`
does not count when the title also contains `engineer`, `developer` or
`linguist`; without that exclusion, one translation company contributed
five "marketing" roles, none of them a sales hire.

Matching runs on the title only, never the job description. That misses
some roles, and it is inspectable in a way that a model-based classifier
would not be.

The hand labels apply a stricter test than the filter: the
[rubric](data/labels/c1_rubric.md) excludes recruiters posting for
clients, roles where selling is a side task, internships, and the same
job posted twice. The gap between the filter's rule and the rubric is
exactly what the 22 / 30 baseline measures.

## How it is measured

- **Frozen input.** Snapshot 3: 69 companies with ≥ 2 target roles, 306
  postings. Exported once, byte-identical on re-export, SHA-256 recorded
  in [build-order.md](build-order.md). Nothing downstream reads the live
  API.
- **Sample.** 30 of the 69, drawn deterministically by
  [scripts/c1_sample.py](scripts/c1_sample.py) (seed `c1`; the script
  refuses a snapshot with a different hash).
- **Criterion 1, labelled before any model ran.** By hand, from the
  posting text only, following the written
  [rubric](data/labels/c1_rubric.md). Labels in
  [data/labels/c1_signal.csv](data/labels/c1_signal.csv). Labelling after
  seeing a model's confident answer would anchor the label to it.
- **Each model gives its own verdict.** `is_real_signal` is compared to
  the hand label, so signal accuracy can differ between models.
- **Criterion 2, per written line.** Is the line supported by the quoted
  evidence? Labelled by hand per model; one model is labelled completely
  before the other runs, so lines are never compared side by side.
- **Same conditions for both models.** Same
  [prompt](prompts/brief_v1.md), same input, same effort setting,
  structured output. The API's refusal fallback is off: it would
  silently answer with a different model than the one being scored.
- **Quotes are checked by script, not by eye.**
  [scripts/c3_review.py](scripts/c3_review.py) tests whether each
  evidence quote appears word for word in the postings. All 49 quotes
  (Haiku 20, Opus 29) do. The first version of the check wrongly flagged
  one quote per model; both models had returned the identical quote, which
  pointed to the script. Cause and fix are documented in
  [build-order.md](build-order.md).
- **Routing threshold fixed in advance.** Written into the plan, dated,
  before the routed numbers were computed.
- **Disputed labels: documented second look, not silent correction.**
  Where both models disagreed with a hand label, the postings were re-read
  against the unchanged rubric
  ([c1_second_look.csv](data/labels/c1_second_look.csv)). The original
  labels file is untouched; the reviewed result is reported next to the
  headline, never instead of it.
- **Tokens are the ground truth.** Every call, including failed ones, is
  logged with the token counts the API reports. Cost is derived from
  them, since prices change.

## Limitations

- **30 companies, one labeller.** Differences of a few records are within
  noise; results are reported as counts for that reason.
- **Two models from one family.** Haiku and Opus agree on 28 of 30
  verdicts. That agreement is not independent confirmation: they share a
  provider and received the same rubric in the prompt, and they share the
  same misreading of consultancies and agencies.
- **The second look was not blind.** The model verdicts were known when
  the six disputed labels were re-read.
- **Input cleaning gap.** 7 of the 30 companies store double-escaped HTML;
  both models received those postings with HTML tags as visible text.
  Same input for both, so the comparison holds, but it cost tokens and
  added noise. The same 7 appeared tag-cluttered in the hand-labelling
  file.
- **One prompt version.** Every result is for `prompts/brief_v1.md` at
  one effort setting. Neither was tuned.

## Data source

Job data comes from the [Arbeitnow job board API](https://www.arbeitnow.com/api/job-board-api)
— free, no API key, and their terms ask for attribution back to
[arbeitnow.com](https://www.arbeitnow.com). Jobs shown or processed here
originate from their board.

The API serves a moving window, not the whole board: 3,901 jobs on
2026-11-20, 3,200 on 2026-11-22, against roughly 11,800 advertised on
the website. That is one more reason the evaluation runs on a frozen
snapshot.

### Why not LinkedIn

LinkedIn would be the obvious richer source and is the wrong call.
Scraping it violates their terms of service. A portfolio project exists
to show judgment as much as capability, and building on a data source
that could not survive contact with a legal review would demonstrate the
opposite. A free API with a clear license is the better engineering
decision, not merely the safer one.

### Why there is no region filter

An earlier version of the plan filtered to DACH. It was dropped.

The API has no country field. `location` is free text — `Berlin`,
`Berlin; Munich`, `Issy-les-Moulineaux, Île-de-France, France`, `Remote`,
and sometimes empty. Filtering it by string matching would have dropped
postings with no way to measure what was lost: a silent, unmeasurable
cut in a project whose whole point is measurement. It also removed about
four fifths of all matches while adding nothing a reviewer would care
about.

So the pipeline processes the feed as it comes. The consequence is
visible in the output rather than hidden in a filter.

## Setup

```bash
git clone <repo-url> && cd hiring-signal-brief
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # set POSTGRES_PASSWORD and N8N_ENCRYPTION_KEY
```

Start Postgres and n8n, then apply the schema:

```bash
docker compose up -d
docker compose exec -T postgres psql -U hsb -d hiring_signal < sql/schema.sql
```

n8n runs at http://localhost:5678. Two credentials are needed there, and
neither is stored in this repo:

- **Postgres** — host `postgres`, port `5432` (the Docker network, not
  `localhost:5434`), database and user from `.env`.
- **Header Auth** — name `x-api-key`, value: an Anthropic API key.

Import the two workflows from `n8n/` and attach the credentials. Order
of a full run:

1. *Fetch Arbeitnow* (n8n), then `sql/export_snapshot.sql` to freeze
2. `scripts/c1_sample.py`, then signal labels by hand
3. *Brief companies* (n8n), once per model (`MODEL` in *Build requests*)
4. `scripts/c3_review.py <model>`, then grounding labels by hand
5. `scripts/c1_second_look.py` for labels both models dispute
6. `sql/eval_table.sql` for the table

The feasibility spike (fetches the live feed, prints how many companies
clear the threshold) still runs on its own:

```bash
python scripts/feasibility.py --pages 150
```

## Repo layout

```
n8n/           exported workflows: fetch-arbeitnow, brief-companies
sql/           schema, reset, snapshot export, evaluation table
prompts/       versioned prompt, read by n8n at run time
scripts/       feasibility.py (spike), c1_sample.py (sample),
               c3_review.py (quote check + review), c1_second_look.py
data/labels/   rubrics, hand labels, second look — committed
data/raw/      frozen snapshot and review files — gitignored
build-order.md working plan with every stage's measured outcome
```

## Out of scope

No frontend, no deployment, no multi-client logic, no agent that decides
its own steps. A fixed pipeline, measured, with honest numbers.
