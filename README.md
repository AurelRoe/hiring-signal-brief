# Hiring Signal Brief

Turns public job postings into qualified company signals with an
evidence-backed personalization line — then measures whether the output
is actually true, and what it cost.

Built as a portfolio project. The pipeline is the apparatus; **the
evaluation is the result.**

> **Status: work in progress.** Data pipeline, frozen snapshot, hand
> labels for criterion 1 and the small-model run are done. Grounding
> labels and the large-model run are next. Every number below marked
> *not measured* is exactly that — no placeholder figures appear in this
> README.

## Result

| | small model<br>`claude-haiku-5-5` | large model<br>`claude-opus-5-5` | confidence-routed |
|---|---|---|---|
| signal accuracy (vs. hand labels) | 23 / 30 | *not measured* | *not measured* |
| share of grounded lines | *not measured* | *not measured* | *not measured* |
| line written without evidence | 0 / 30 | *not measured* | *not measured* |
| abstained (no line, no evidence) | 9 / 30 | *not measured* | *not measured* |
| tokens per record (in / out) | 8,516 / 864 | *not measured* | *not measured* |
| cost per record | $0.0013 | *not measured* | *not measured* |

**Baseline without any model:** the rule-based title filter alone is
right for 22 of 30 companies (73%; 95% Wilson interval roughly 56–86%).

Measured on 30 hand-labelled companies against a frozen data snapshot,
so both models see identical input. With 30 records, one record is about
3 percentage points: a gap of one or two records between two columns is
not a result. Cost is computed from the token counts the API reports, at
Anthropic's list prices at the time of the run; output tokens include
the model's thinking.

**What the small model does differently from the filter:** it rejects
all 8 companies the title filter wrongly let through, and never calls a
company "real" that the hand labels call false. It is too strict, not
too lenient: 7 companies labelled as real were rejected.

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
  cannot be checked. Small model: 0 of 30.
- **No line and no evidence** — the model judged the company not worth
  contacting and wrote nothing. Small model: 9 of 30, all with
  `is_real_signal = false`.

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
- **Tokens are the ground truth.** Every call, including failed ones, is
  logged with the token counts the API reports. Cost is derived from
  them, since prices change.

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
of a full run: *Fetch Arbeitnow* → `sql/export_snapshot.sql` →
`scripts/c1_sample.py` and hand labels → *Brief companies*.

The feasibility spike (fetches the live feed, prints how many companies
clear the threshold) still runs on its own:

```bash
python scripts/feasibility.py --pages 150
```

## Repo layout

```
n8n/           exported workflows: fetch-arbeitnow, brief-companies
sql/           schema, reset, snapshot export
prompts/       versioned prompt, read by n8n at run time
scripts/       feasibility.py (spike), c1_sample.py (evaluation sample)
data/labels/   rubric and hand labels — committed
data/raw/      frozen snapshot and review files — gitignored
build-order.md working plan with every stage's measured outcome
```

## Out of scope

No frontend, no deployment, no multi-client logic, no agent that decides
its own steps. A fixed pipeline, measured, with honest numbers.
