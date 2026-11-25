---
name: signal-brief
description: Write an evidence-backed hiring-signal brief for one named company from its public Arbeitnow job postings — is it building a sales or marketing team, and what cold-email opener could a salesperson use. Use when the user runs /signal-brief <company> or asks for a signal brief, hiring signal or personalization line for a specific company.
---

# Signal brief for one company

Same rules as the evaluated pipeline, for one company on demand.

## Steps

1. **Gather the postings.** From the repo root run:

   ```bash
   python scripts/brief.py "<company>"
   ```

   It fetches the live Arbeitnow feed (one to two minutes: the API
   rate-limits, and the script waits rather than skip pages) and applies the
   pipeline's role definition, read from `n8n/fetch-arbeitnow.json`. Add
   `--snapshot` to use the frozen evaluation data instead. If it finds no
   postings, or fewer target roles than the threshold, say so and stop:
   there is nothing to brief.

2. **Write the brief by the measured prompt.** Read
   `prompts/brief_v1.md` and apply it as written, to the script's output
   only. Do not add rules, and do not use knowledge about the company
   from anywhere else.

3. **Check before answering.**
   - The evidence must appear word for word in the script output. Search
     for it; if it is not there, pick a passage that is, or leave
     evidence and line empty.
   - Every claim in the line must be in the evidence or in the job titles
     and locations. Drop or rewrite any claim that is not.
   - If `is_real_signal` is false, write no personalization line. The
     CSV export applies the same filter.

## Output

A short table: real signal (yes/no) and confidence, hiring focus, team
context, the evidence quote, the personalization line. Then the posting
links and the line "Job data: Arbeitnow (arbeitnow.com)".

## Known limits, from the evaluation

Tell the user when one applies:

- **Consultancies and agencies.** Both evaluated models wrongly rejected
  real hiring at consultancies staffing their own people and at agencies
  with client-facing account roles. If the verdict is "no" for such a
  company, say that a human should check it.
- **Confidence does not flag grounding errors.** The user should read the
  quote next to the line before sending it.
- **This skill itself is not evaluated.** The README's numbers come from
  the n8n pipeline (Claude Haiku 5.5 and Opus 5.5 via the API, effort
  medium). Here, the model is whatever this session runs, so those
  numbers do not automatically apply.
