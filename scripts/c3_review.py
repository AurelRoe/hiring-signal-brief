#!/usr/bin/env python3
"""
C3: prepare grounding labels for one model's briefs.

For every brief with a written line:
  - checks mechanically whether the evidence quote appears word for word in
    that company's postings (frozen snapshot, hash-checked)
  - writes a review file showing only line, evidence and the company's job
    titles/locations; the model's verdict and confidence are hidden
  - writes an empty label sheet (never overwritten once it exists)

Reads briefs from Postgres via `docker compose exec`, so run it from the
repo root with the containers up.

Usage:
    python scripts/c3_review.py claude-haiku-5-5
"""

import csv
import difflib
import hashlib
import html
import json
import re
import subprocess
import sys
from pathlib import Path

SNAPSHOT = Path("data/raw/eval_snapshot_3.json")
SNAPSHOT_SHA256 = "00bf78c8a4de3cfcee6aa16a94982a7aa6ffcb858193913398630099d1c21ee1"
RUN_LABEL = "v1"

QUERY = """
select coalesce(json_agg(x order by x.company_name), '[]')
from (
    select b.id as brief_id, b.company_id, c.company_name,
           b.personalization_line, b.evidence
    from briefs b join companies c on c.id = b.company_id
    where b.model = '{model}' and b.run_label = '{run_label}'
      and btrim(coalesce(b.personalization_line, '')) <> ''
) x;
"""

QUOTES = str.maketrans({"“": '"', "”": '"', "„": '"', "«": '"',
                        "»": '"', "‘": "'", "’": "'", "–": "-",
                        "—": "-", " ": " "})


def normalize(s: str) -> str:
    """Same text, different whitespace/quote styles/HTML entities -> equal."""
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = html.unescape(html.unescape(s)).translate(QUOTES)
    return re.sub(r"\s+", " ", s).strip()


def longest_overlap(needle: str, haystack: str) -> float:
    """Share of the quote covered by its longest exact run in the postings."""
    if not needle:
        return 0.0
    m = difflib.SequenceMatcher(None, needle, haystack, autojunk=False)
    return m.find_longest_match(0, len(needle), 0, len(haystack)).size / len(needle)


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    model = sys.argv[1]
    if not re.fullmatch(r"[a-z0-9.-]+", model):
        print("model id looks wrong", file=sys.stderr)
        return 2

    raw = SNAPSHOT.read_bytes()
    if hashlib.sha256(raw).hexdigest() != SNAPSHOT_SHA256:
        print("Snapshot hash mismatch. Refusing to run.", file=sys.stderr)
        return 1
    companies = {c["company_id"]: c for c in json.loads(raw)}

    out = subprocess.run(
        ["docker", "compose", "exec", "-T", "postgres", "psql", "-U", "hsb",
         "-d", "hiring_signal", "-At", "-c",
         QUERY.format(model=model, run_label=RUN_LABEL)],
        check=True, capture_output=True, text=True,
    ).stdout
    briefs = json.loads(out)
    if not briefs:
        print(f"No briefs with a line for {model}.", file=sys.stderr)
        return 1

    review = [f"# C3 review — {model} — {len(briefs)} written lines", "",
              "Label with `data/labels/c3_rubric.md` open. Verdict and confidence",
              "are hidden on purpose.", ""]
    rows = []
    for n, b in enumerate(briefs, 1):
        c = companies[b["company_id"]]
        # Whitespace is dropped before comparing: n8n turned HTML into text
        # differently (tags removed without a space), so the model may have
        # seen "word.Word" where this script would produce "word. Word".
        postings = re.sub(r"\s+", "", normalize(" ".join(
            j["title"] + " " + (j["description"] or "") for j in c["jobs"])))
        ev = re.sub(r"\s+", "", normalize(b["evidence"] or ""))
        verbatim = bool(ev) and ev in postings
        overlap = 1.0 if verbatim else longest_overlap(ev, postings)

        titles = sorted({f"{j['title']} — {j['location'] or '?'}" for j in c["jobs"]})
        review += [
            "---", "",
            f"## {n}. {b['company_name']}  (brief_id {b['brief_id']})", "",
            f"**Line:** {b['personalization_line']}", "",
            f"**Evidence:** {b['evidence'] or '(empty)'}", "",
            f"**Evidence verbatim in postings:** {'yes' if verbatim else 'NO'}"
            + ("" if verbatim else f" (longest exact run covers {overlap:.0%} of the quote)"),
            "", "**Job titles and locations:**",
        ] + [f"- {t}" for t in titles] + [""]
        rows.append([b["brief_id"], b["company_name"], str(verbatim).lower()])

    safe = model.replace(".", "-")
    review_path = Path(f"data/raw/c3_review_{safe}.md")
    review_path.write_text("\n".join(review), encoding="utf-8")
    print(f"review file : {review_path}")

    labels = Path(f"data/labels/c3_grounded_{safe}.csv")
    if labels.exists():
        print(f"label sheet : {labels} exists, left untouched")
    else:
        with labels.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["brief_id", "company_name", "evidence_verbatim",
                        "is_grounded", "reason"])
            for r in rows:
                w.writerow(r + ["", ""])
        print(f"label sheet : {labels} (fill in is_grounded + reason)")

    n_ok = sum(r[2] == "true" for r in rows)
    print(f"\nwritten lines: {len(rows)} | evidence verbatim: {n_ok} | not verbatim: {len(rows) - n_ok}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
