-- Hiring Signal Brief -- schema
-- Applies against an empty database. Safe to re-run (IF NOT EXISTS).
--   docker compose exec -T postgres psql -U hsb -d hiring_signal < sql/schema.sql
--
-- All timestamps are timestamptz. The feed reports UTC, the containers run
-- Europe/Berlin, and a naive timestamp loses that distinction silently.

-- ---------------------------------------------------------------------------
-- 1. snapshots -- provenance for the frozen input
-- ---------------------------------------------------------------------------
-- The evaluation must run against fixed input. Every job and company row
-- points at the snapshot it came from, so a later refetch cannot quietly
-- change what the models were scored on.

create table if not exists snapshots (
    id           bigserial primary key,
    fetched_at   timestamptz not null default now(),
    job_count    integer     not null,
    page_count   integer,
    note         text
);

-- ---------------------------------------------------------------------------
-- 2. jobs -- raw postings, one row per posting
-- ---------------------------------------------------------------------------
-- Needed beyond aggregation: hand-labelling criterion 1 means reading the
-- actual postings, and the evidence field quotes their text.

create table if not exists jobs (
    id            bigserial primary key,
    snapshot_id   bigint      not null references snapshots(id) on delete cascade,
    slug          text        not null,
    company_name  text        not null,
    company_key   text        not null,   -- normalised: legal suffixes stripped
    title         text        not null,
    location      text,
    remote        boolean,
    url           text,
    description   text,
    posted_at     timestamptz,
    is_target_role boolean    not null,   -- result of the title match
    unique (snapshot_id, slug)
);

create index if not exists jobs_company_idx on jobs (snapshot_id, company_key);

-- ---------------------------------------------------------------------------
-- 3. companies -- aggregated signal, one row per company per snapshot
-- ---------------------------------------------------------------------------
-- Every company with >= 1 target role is stored, not only qualifying ones.
-- The >= 2 threshold is a query, not a deletion: the README needs to report
-- how many companies the pre-filter removed.

create table if not exists companies (
    id               bigserial primary key,
    snapshot_id      bigint  not null references snapshots(id) on delete cascade,
    company_key      text    not null,
    company_name     text    not null,   -- display name, first seen spelling
    role_count       integer not null,
    first_posting_at timestamptz,
    latest_posting_at timestamptz,
    cities           text[],
    in_eval_set      boolean not null default false,  -- one of the 30
    unique (snapshot_id, company_key)
);

create index if not exists companies_eval_idx on companies (in_eval_set)
    where in_eval_set;

-- ---------------------------------------------------------------------------
-- 4. briefs -- LLM output, one row per company PER MODEL
-- ---------------------------------------------------------------------------
-- The grain is (company, model, run). Putting the LLM output on the company
-- row would make the two-model comparison impossible to store.
--
-- is_valid is generated, not written: an empty evidence field is a failed
-- record by definition, and the rule belongs in the database rather than in
-- whichever node happened to write the row.

create table if not exists briefs (
    id                  bigserial primary key,
    company_id          bigint not null references companies(id) on delete cascade,
    model               text   not null,
    run_label           text   not null default 'main',
    hiring_focus        text,
    team_context        text,
    personalization_line text,
    confidence          numeric(4,3) check (confidence between 0 and 1),
    evidence            text,
    raw_response        jsonb,
    created_at          timestamptz not null default now(),
    is_valid            boolean generated always as
                            (evidence is not null and length(btrim(evidence)) > 0) stored,
    unique (company_id, model, run_label)
);

-- Added in C2: the model's own verdict on criterion 1, scored against
-- labels_signal. Lets signal accuracy differ per model; without it, both
-- models would inherit the same company-level label.
-- run_label holds the prompt version (e.g. 'v1').
alter table briefs add column if not exists is_real_signal boolean;

-- ---------------------------------------------------------------------------
-- 5. llm_calls -- token usage, one row per API call
-- ---------------------------------------------------------------------------
-- Separate from briefs because a failed call produces no brief but still
-- costs tokens. Merging them would understate cost.
--
-- cost_usd is nullable: tokens are the ground truth and prices change, so
-- cost can always be recomputed from the token counts.

create table if not exists llm_calls (
    id                bigserial primary key,
    company_id        bigint references companies(id) on delete set null,
    brief_id          bigint references briefs(id) on delete set null,
    model             text    not null,
    prompt_tokens     integer not null,
    completion_tokens integer not null,
    total_tokens      integer generated always as
                          (prompt_tokens + completion_tokens) stored,
    cost_usd          numeric(10,6),
    latency_ms        integer,
    status            text    not null default 'ok',  -- ok | no_evidence | invalid_output | refusal | max_tokens | api_error
    called_at         timestamptz not null default now()
);

create index if not exists llm_calls_model_idx on llm_calls (model);

-- ---------------------------------------------------------------------------
-- 6. labels -- two tables, because the two criteria have different grains
-- ---------------------------------------------------------------------------
-- Criterion 1 ("is this company actually hiring for that function?") is a
-- property of the COMPANY. It is labelled once, before any model runs, and
-- is reused for both models.
--
-- Criterion 2 ("is the line supported by the quoted evidence?") is a property
-- of the BRIEF. The same company gets one grounding label per model.
--
-- Collapsing these into one table would invite labelling criterion 1 twice
-- and scoring it per model, which is exactly the confusion the split
-- evaluation exists to avoid.

create table if not exists labels_signal (
    company_id  bigint primary key references companies(id) on delete cascade,
    is_correct  boolean not null,
    reason      text,
    labelled_at timestamptz not null default now()
);

create table if not exists labels_grounded (
    brief_id    bigint primary key references briefs(id) on delete cascade,
    is_grounded boolean not null,
    reason      text,
    labelled_at timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- 7. eval_records -- the final table as one query
-- ---------------------------------------------------------------------------

create or replace view eval_records as
select
    c.id              as company_id,
    c.company_name,
    c.role_count,
    b.model,
    b.is_valid        as evidence_present,
    ls.is_correct     as signal_correct,
    lg.is_grounded    as line_grounded,
    lc.prompt_tokens,
    lc.completion_tokens,
    lc.total_tokens,
    lc.cost_usd,
    b.confidence,
    -- appended in C2 (a replaced view may only gain columns at the end)
    b.run_label,
    b.is_real_signal                  as model_says_signal,
    (b.is_real_signal = ls.is_correct) as model_signal_correct
from companies c
join briefs b              on b.company_id = c.id
left join labels_signal ls on ls.company_id = c.id
left join labels_grounded lg on lg.brief_id = b.id
left join llm_calls lc     on lc.brief_id = b.id
where c.in_eval_set;