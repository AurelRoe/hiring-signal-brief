# CLAUDE.md

## What this repo is

An n8n pipeline that turns public job postings into qualified company
signals with an evidence-backed personalization line — evaluated for
accuracy and measured for token cost.

Portfolio project. The **evaluation is the deliverable**, not the
pipeline. Honest numbers beat a bigger feature set.

## Stack

- Orchestration: n8n (local, Docker)
- Data source: Arbeitnow free job board API (`/api/job-board-api`, no key)
- Storage: Postgres (Docker)
- LLM: one small + one large model, same prompt
- Skill: `SKILL.md` + `scripts/brief.py`

## Layout

```
scripts/     feasibility.py (throwaway spike, done), brief.py
n8n/         exported workflow JSON
sql/         schema + queries
data/raw/    frozen API snapshot (do not refresh mid-evaluation)
```

## Role definition (single source of truth)

Used in two places: the n8n filter node (step 3) and `scripts/brief.py`.
If they drift, the Skill returns a different result than the pipeline.

Match on **job title**, case-insensitive:

```
sales, vertrieb, account executive, account manager, sdr, bdr,
business development, marketing, kundenberater, außendienst,
inside sales, pre-sales, partner manager
```

Excluded deliberately: `growth` and `revenue` (matched engineering
roles). `marketing` does not count if the title also contains
`engineer`, `developer` or `linguist`.

Title only, never the description. Cheap and inspectable by design.

## No region filter

Decided 2026-11-20: the pipeline does **not** filter by country. The
API has no country field, `location` is free text, and a string filter
would drop postings with no way to measure what was lost. If you are
tempted to re-add one, it belongs in the README as a tradeoff, not in
the code as a silent cut.

## Non-negotiables

1. **The `evidence` field is mandatory.** Every LLM output quotes the
   source text it relied on. Without it, hallucination cannot be
   checked — and the grounding metric is the whole point.
2. **Two error types, measured separately.** "Is the signal correct?"
   and "is the line grounded in the evidence?" are different numbers.
   Never collapse them into one accuracy figure.
3. **Never scrape LinkedIn.** It violates their terms. This is a
   stated position in the README, not an oversight.
4. **Credit Arbeitnow as the source.** Their terms request it.
5. **No invented numbers.** If a metric wasn't measured, it says
   "not measured". Fabricated results would defeat the project.

## Conventions

- Rule-based filtering happens *before* any LLM call. That is where
  token cost is saved; keep the pre-filter cheap and dumb.
- The evaluation runs against the frozen snapshot in `data/raw/`, so
  both models see identical input. Don't re-fetch to "get fresh data".
- No secrets in committed files. Keys live in `.env`. n8n writes
  credentials into workflow JSON on export — strip them before commit.
- Python: stdlib + `requests` where possible. No framework unless it
  earns its place.
- `scripts/feasibility.py` is a finished spike. Don't polish it. New
  filter logic goes into the pipeline, not back into the spike.

## Out of scope

No frontend, no deployment, no multi-client logic, no agent that picks
its own steps. Fixed pipeline, measured, honest.

## Working with me on this

- Ask before adding a dependency or a pipeline step.
- Short commits, present tense, one concern each.
- When a plan assumption turns out false, say so instead of routing
  around it quietly.