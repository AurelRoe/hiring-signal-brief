# Hiring Signal Brief

Turns public job postings into qualified company signals with an
evidence-backed personalization line — then measures whether the output
is actually true, and what it cost.

Built as a portfolio project. The pipeline is the apparatus; **the
evaluation is the result.**

> **Status: work in progress.** The feasibility spike is done and the
> data source is confirmed. The pipeline and the evaluation are not
> built yet. Every number below marked *not measured* is exactly that —
> no placeholder figures appear in this README.

## Result

| | small model | large model | confidence-routed |
|---|---|---|---|
| signal accuracy | *not measured* | *not measured* | *not measured* |
| share of grounded lines | *not measured* | *not measured* | *not measured* |
| tokens per record | *not measured* | *not measured* | *not measured* |
| cost per record | *not measured* | *not measured* | *not measured* |

Measured on 30 hand-labeled companies against a frozen data snapshot,
so both models see identical input.

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

## Pipeline

```
Schedule trigger (daily)
  -> HTTP request: Arbeitnow job board API (paginated)
  -> Filter: target roles only (title match)
  -> Dedupe: company + job id
  -> Aggregate per company: role count, first/latest posting, cities
  -> Pre-filter: keep companies with >= 2 open target roles   <- no LLM yet
  -> LLM: structured JSON { hiring_focus, team_context,
                            personalization_line, confidence, evidence }
  -> Postgres: results + token usage per call
  -> Export: CSV
```

The pre-filter before the LLM node is where the token cost is saved. It
is deliberately cheap and rule-based: a title match and a count, nothing
that needs a model.

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

## Data source

Job data comes from the [Arbeitnow job board API](https://www.arbeitnow.com/api/job-board-api)
— free, no API key, and their terms ask for attribution back to
[arbeitnow.com](https://www.arbeitnow.com). Jobs shown or processed here
originate from their board.

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
```

Feasibility check against the live feed (fetches, freezes a snapshot to
`data/raw/`, prints how many companies clear the threshold):

```bash
python scripts/feasibility.py --pages 150
```

n8n and Postgres run locally via Docker. *Setup instructions to follow
once the compose file exists.*

## Repo layout

```
scripts/     feasibility.py (spike), brief.py (Skill logic)
n8n/         exported workflow JSON
sql/         schema + queries
data/raw/    frozen API snapshot — gitignored, not refreshed mid-evaluation
```

## Out of scope

No frontend, no deployment, no multi-client logic, no agent that decides
its own steps. A fixed pipeline, measured, with honest numbers.