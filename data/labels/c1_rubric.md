# C1 rubric — criterion 1: is the signal correct?

Written before labelling, fixed before any model runs. Every label in
`c1_signal.csv` follows these rules. If a case fits none of them, decide it,
then add the rule here so later labels stay consistent.

## The question

> Is this company genuinely hiring for at least **two** distinct
> sales or marketing openings?

`is_correct = true` means the pipeline's signal holds. `false` means it was a
false positive of the title filter.

## What counts as an opening

1. **The named company is the employer.** A staffing agency or recruiter
   posting for an unnamed client does not count: the company the signal
   names is not the one hiring.
2. **The role's actual job is selling or marketing to customers.** Counts:
   account executives, account managers, SDR/BDR, business development,
   field and inside sales, pre-sales and sales engineers (pre-sales is in the
   role definition), marketing roles. Does not count, whatever the title
   says: recruiters ("Sales Talent Acquisition"), artists and designers
   ("Marketing Video Artist"), post-sales support ("Technical Account
   Manager"), tax/finance roles that mention sales.
   Counts only if selling or marketing processes are the main job. A role where
   sales-related work is one task among several does not count.
3. **No internships or working students** (Praktikum, Werkstudent, stage,
   intern, graduate programme). They rarely mean a team is being built.
4. **Distinct openings only.** The same job posted twice (identical title,
   or only the gender suffix differs: m/w/d vs m/f/d) is one opening. The
   same role in different cities counts once per city: that is real
   headcount.

## Label format

- `is_correct`: `true` or `false`
- `reason`, kept short on purpose. The accuracy number uses only
  `is_correct`; reasons exist to break down the false positives.

| Case | `reason` |
|---|---|
| Obvious `true` | empty |
| `false` | the deciding rule: `r1`, `r2`, `r3` or `r4` |
| Unclear, or no rule fits | one short sentence (quoted if it has a comma) |

Rule numbers: **r1** recruiter for a client · **r2** not a sales/marketing
role · **r3** intern / working student · **r4** duplicate posting.

```
1,Example Corp,true,
2,Example Staffing GmbH,false,r1
3,Example Games,false,"r2; artist role, judged as design"
```

Judge from the posting text in the review file only. No company websites,
no model output.
