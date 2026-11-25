-- D1: contact list for a salesperson, as CSV for German-locale Excel.
--
--   mkdir -p data/exports
--   { printf '\357\273\277'; docker compose exec -T postgres psql -U hsb \
--       -d hiring_signal -q < sql/export_briefs.sql; } > data/exports/briefs_opus.csv
--
-- The printf writes a UTF-8 byte-order mark, so Excel reads umlauts
-- correctly. Semicolon separator and comma decimals match German Excel.
-- The file holds text derived from Arbeitnow postings: it lands under
-- data/exports/, which *.csv in .gitignore keeps out of git.
--
-- Rows: Opus briefs (all 29 Opus lines were grounded in C3) for companies
-- the model itself calls a real signal and wrote a line for. Selection is
-- by the model's verdict, never by the hand labels: the file shows what
-- the pipeline produces.

copy (
    select c.company_name                                          as company,
           c.role_count                                            as open_sales_marketing_roles,
           array_to_string(c.cities, '; ')                         as locations,
           b.hiring_focus,
           b.team_context,
           b.personalization_line,
           b.evidence                                              as evidence_quote,
           replace(to_char(b.confidence, 'FM0.00'), '.', ',')      as confidence,
           to_char(c.first_posting_at, 'YYYY-MM-DD')               as first_posting,
           to_char(c.latest_posting_at, 'YYYY-MM-DD')              as latest_posting,
           (select string_agg(j.url, chr(10) order by j.posted_at desc, j.slug)
            from jobs j
            where j.snapshot_id = c.snapshot_id
              and j.company_key = c.company_key
              and j.is_target_role)                                as job_links,
           'Job data: Arbeitnow (arbeitnow.com)'                   as source,
           b.model,
           to_char(s.fetched_at, 'YYYY-MM-DD')                     as data_as_of
    from briefs b
    join companies c on c.id = b.company_id and c.in_eval_set
    join snapshots s on s.id = c.snapshot_id
    where b.model = 'claude-opus-5-5'
      and b.run_label = 'v1'
      and b.is_real_signal
      and btrim(coalesce(b.personalization_line, '')) <> ''
    order by b.confidence desc, c.company_name
) to stdout with (format csv, header, delimiter ';');
