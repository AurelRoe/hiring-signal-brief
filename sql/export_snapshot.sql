-- B4: freeze the evaluation input.
-- Exports every company with >= 2 target roles from one snapshot, with the
-- full text of its target-role postings. Everything downstream reads this
-- file, never a live fetch.
--
--   docker compose exec -T postgres psql -U hsb -d hiring_signal -At -v snap=3 \
--     < sql/export_snapshot.sql > data/raw/eval_snapshot_3.json
--
-- -At prints the bare value (no table borders, no row count), so stdout is
-- pure JSON. Job descriptions are left as raw HTML: this is the frozen
-- source, any cleaning happens downstream.

select json_agg(c order by c.role_count desc, c.company_key)
from (
    select co.id          as company_id,
           co.snapshot_id,
           co.company_name,
           co.company_key,
           co.role_count,
           co.first_posting_at,
           co.latest_posting_at,
           co.cities,
           (select json_agg(json_build_object(
                       'slug',        j.slug,
                       'title',       j.title,
                       'location',    j.location,
                       'remote',      j.remote,
                       'url',         j.url,
                       'posted_at',   j.posted_at,
                       'description', j.description)
                   order by j.posted_at, j.slug)
            from jobs j
            where j.snapshot_id = co.snapshot_id
              and j.company_key = co.company_key
              and j.is_target_role) as jobs
    from companies co
    where co.snapshot_id = :snap
      and co.role_count >= 2
) c;
