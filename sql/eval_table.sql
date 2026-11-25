-- C4: the evaluation table, recomputed from stored tokens and hand labels.
--   docker compose exec -T postgres psql -U hsb -d hiring_signal < sql/eval_table.sql
--
-- Nothing here is typed in by hand except list prices: every count comes
-- from briefs, llm_calls, labels_signal and labels_grounded.
--
-- Routing rule, fixed before this query was first run (build-order.md, C4):
-- Haiku answers every company; where Haiku's confidence < 0.85, Opus's
-- answer is used instead. Cost of a routed record = Haiku call + Opus call.

\pset pager off

-- List prices per 1M tokens at the time of the runs (2026-11). Haiku's
-- price holds for prompts up to 100K tokens; the largest prompt here is
-- about 26K. Cost is derived from tokens, so a price change only needs an
-- edit here.
create temp view price (model, usd_in, usd_out) as values
    ('claude-haiku-5-5', 0.10, 0.50),
    ('claude-opus-5-5',  4.00, 20.00);

-- One row per company per model, with everything the table needs.
create temp view rec as
select b.company_id,
       b.model,
       b.is_real_signal,
       b.confidence,
       ls.is_correct                                         as label,
       coalesce(rv.reviewed_is_correct, ls.is_correct)       as label_reviewed,
       btrim(coalesce(b.personalization_line, '')) <> ''     as has_line,
       btrim(coalesce(b.evidence, '')) <> ''                 as has_evidence,
       lg.is_grounded,
       lc.prompt_tokens,
       lc.completion_tokens,
       (lc.prompt_tokens * p.usd_in + lc.completion_tokens * p.usd_out) / 1e6 as cost
from briefs b
join companies c       on c.id = b.company_id and c.in_eval_set
join labels_signal ls  on ls.company_id = b.company_id
left join labels_signal_review rv on rv.company_id = b.company_id
left join labels_grounded lg on lg.brief_id = b.id
join llm_calls lc      on lc.brief_id = b.id
join price p           on p.model = b.model
where b.run_label = 'v1';

-- Routed records for every threshold t: route to Opus when Haiku conf < t.
create temp view routed as
select t.t,
       h.company_id,
       h.confidence < t.t                                                    as to_opus,
       case when h.confidence < t.t then o.is_real_signal else h.is_real_signal end as verdict,
       h.label,
       h.label_reviewed,
       case when h.confidence < t.t then o.has_line     else h.has_line     end as has_line,
       case when h.confidence < t.t then o.has_evidence else h.has_evidence end as has_evidence,
       case when h.confidence < t.t then o.is_grounded  else h.is_grounded  end as is_grounded,
       h.prompt_tokens     + case when h.confidence < t.t then o.prompt_tokens     else 0 end as tin,
       h.completion_tokens + case when h.confidence < t.t then o.completion_tokens else 0 end as tout,
       h.cost              + case when h.confidence < t.t then o.cost              else 0 end as cost
from (values (0.00), (0.60), (0.70), (0.75), (0.80), (0.85), (0.90), (0.92), (1.01)) as t(t)
cross join (select * from rec where model = 'claude-haiku-5-5') h
join       (select * from rec where model = 'claude-opus-5-5')  o using (company_id);

-- The three columns of the result table.
create temp view variants as
select 1 as ord, 'haiku' as variant, is_real_signal as verdict, label, has_line, has_evidence,
       is_grounded, prompt_tokens as tin, completion_tokens as tout, cost, false as to_opus
from rec where model = 'claude-haiku-5-5'
union all
select 2, 'opus', is_real_signal, label, has_line, has_evidence,
       is_grounded, prompt_tokens, completion_tokens, cost, false
from rec where model = 'claude-opus-5-5'
union all
select 3, 'routed (conf < 0.85)', verdict, label, has_line, has_evidence,
       is_grounded, tin, tout, cost, to_opus
from routed where t = 0.85;

\echo
\echo == Result table ==
select variant,
       count(*)                                                      as companies,
       count(*) filter (where verdict = label)                       as signal_correct,
       count(*) filter (where has_line)                              as lines,
       count(*) filter (where is_grounded)                           as grounded,
       count(*) filter (where has_line and not has_evidence)         as line_no_evidence,
       count(*) filter (where not has_line and not has_evidence)     as abstained,
       count(*) filter (where not has_line and has_evidence)         as evidence_no_line,
       round(avg(tin))                                               as avg_tokens_in,
       round(avg(tout))                                              as avg_tokens_out,
       round(avg(cost)::numeric, 4)                                  as usd_per_record,
       round(sum(cost)::numeric, 2)                                  as usd_total,
       count(*) filter (where to_opus)                               as sent_to_opus
from variants
group by ord, variant
order by ord;

\echo
\echo == Threshold sweep (route to Opus when Haiku confidence < t) ==
\echo == t = 0: Haiku only. t = 1.01: Opus answers all, Haiku still paid. ==
select t,
       count(*) filter (where to_opus)                               as sent_to_opus,
       count(*) filter (where verdict = label)                       as signal_correct,
       count(*) filter (where has_line)                              as lines,
       count(*) filter (where is_grounded)                           as grounded,
       count(*) filter (where has_line and not is_grounded)          as not_grounded,
       round(avg(cost)::numeric, 4)                                  as usd_per_record
from routed
group by t
order by t;

-- Signal accuracy against the blind C1 labels (headline) and after the
-- documented second look at labels both models disputed (not blind).
-- "title filter alone" says "real" for every company: all 30 passed it.
create temp view signal as
select 0 as ord, 'title filter alone' as variant, true as verdict, label, label_reviewed
from rec where model = 'claude-haiku-5-5'
union all
select 1, 'haiku', is_real_signal, label, label_reviewed from rec where model = 'claude-haiku-5-5'
union all
select 2, 'opus', is_real_signal, label, label_reviewed from rec where model = 'claude-opus-5-5'
union all
select 3, 'routed (conf < 0.85)', verdict, label, label_reviewed from routed where t = 0.85;

\echo
\echo == Signal accuracy: blind C1 labels vs. after documented second look ==
select variant,
       count(*) filter (where verdict = label)          as correct_blind_labels,
       count(*) filter (where verdict = label_reviewed) as correct_reviewed_labels,
       count(*)                                         as companies
from signal
group by ord, variant
order by ord;
