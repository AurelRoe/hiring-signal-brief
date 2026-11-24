# C3 rubric — criterion 2: is the line grounded?

Written before labelling, applied identically to both models. Every label in
`c3_grounded_<model>.csv` follows these rules. If a case fits none of them,
decide it, add the rule here, and re-check earlier labels of **both** models.

## The question

> Is every claim in the personalization line supported by the evidence
> quote or by the job titles and locations of this company's postings?

Only briefs with a written line are labelled. A brief with no line
(abstained) has nothing to check and gets no grounding label.

## What may support a claim

1. **The evidence quote**, if the script found it verbatim in the postings
   (`evidence_verbatim = true`).
2. **The job titles and locations** of this company's postings, listed in
   the review file. These are visible facts, not inventions.

Nothing else: not the rest of the posting text, not general knowledge about
the company, not the model's other fields.

## Rules

- **g1 — unsupported claim.** One claim not covered by 1 or 2 fails the
  whole line, even if everything else is right. A salesperson sends the
  whole sentence.
- **g2 — invented inference.** A conclusion is fine if it follows directly
  from supported facts and adds no new fact. "Hiring two AEs, so the team is
  growing" is fine. A conclusion that brings in a new fact — a number, a
  date, a first/only/fastest, a reason, a stage of growth, a name — is a
  claim and needs its own support.
- **g3 — quote not real.** If `evidence_verbatim = false`, the quote cannot
  support anything. Judge the line on titles and locations alone.
- **Not claims:** friendly framing ("I noticed", "I saw that", "so I wanted
  to reach out") and addressing the reader ("your team").

## Label format

| Case | `is_grounded` | `reason` |
|---|---|---|
| Every claim supported | `true` | empty |
| Not grounded | `false` | the deciding rule: `g1`, `g2` or `g3` |
| Unclear, or no rule fits | either | one short sentence (quoted if it has a comma) |

Judge from the review file only. The model's verdict and confidence are
deliberately not shown there, and the other model's line for the same
company is never looked at while labelling.
