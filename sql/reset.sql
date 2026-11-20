-- Drops everything. Rebuild with schema.sql.
--   docker compose exec -T postgres psql -U hsb -d hiring_signal < sql/reset.sql
drop view  if exists eval_records;
drop table if exists labels_grounded, labels_signal, llm_calls, briefs,
                     companies, jobs, snapshots cascade;