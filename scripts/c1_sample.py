#!/usr/bin/env python3
"""
C1: draw the 30-company evaluation sample from the frozen snapshot and
prepare hand-labelling.

Writes:
  data/raw/c1_review.md      every posting of the 30, readable (gitignored:
                             contains job text)
  data/labels/c1_signal.csv  empty label sheet (committed; never overwritten)

Prints the SQL that marks the sample in Postgres.

The sample is deterministic: companies are ordered by sha256("c1|" + key)
and the first 30 are taken. Same snapshot in, same 30 out.

Usage:
    python scripts/c1_sample.py
"""

import csv
import hashlib
import html
import json
import re
import sys
from pathlib import Path

SNAPSHOT = Path("data/raw/eval_snapshot_3.json")
# Recorded in build-order.md (B4). Refuse to sample from anything else.
SNAPSHOT_SHA256 = "00bf78c8a4de3cfcee6aa16a94982a7aa6ffcb858193913398630099d1c21ee1"
SEED = "c1"
SAMPLE_SIZE = 30

REVIEW = Path("data/raw/c1_review.md")
LABELS = Path("data/labels/c1_signal.csv")


def html_to_text(s: str) -> str:
    """Postings are raw HTML. Keep paragraph breaks, drop tags."""
    s = re.sub(r"(?i)<br\s*/?>|</p>|</li>|</h\d>", "\n", s or "")
    s = re.sub(r"(?i)<li[^>]*>", "- ", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s)
    s = re.sub(r"[ \t]+", " ", s)
    return re.sub(r"\n\s*\n+", "\n\n", s).strip()


def main() -> int:
    raw = SNAPSHOT.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != SNAPSHOT_SHA256:
        print(f"Snapshot hash mismatch: {digest}\nRefusing to sample.", file=sys.stderr)
        return 1
    companies = json.loads(raw)

    sample = sorted(
        companies,
        key=lambda c: hashlib.sha256(f"{SEED}|{c['company_key']}".encode()).hexdigest(),
    )[:SAMPLE_SIZE]
    sample.sort(key=lambda c: c["company_name"].lower())

    # --- review file: one section per company ---------------------------
    out = [
        "# C1 review — 30 companies",
        "",
        "Label with `data/labels/c1_rubric.md` open. Job text is not committed.",
        "",
    ]
    for n, c in enumerate(sample, 1):
        out += [
            "---",
            "",
            f"## {n}. {c['company_name']}  (company_id {c['company_id']}, "
            f"{c['role_count']} matched postings)",
            "",
        ]
        seen: dict[str, str] = {}
        for i, j in enumerate(c["jobs"], 1):
            out.append(f"### {n}.{i} {j['title']}")
            out.append(f"{j['location'] or '?'} · {j['posted_at'][:10]} · {j['url']}")
            out.append("")
            text = html_to_text(j["description"])
            if text in seen:
                out.append(f"*Description identical to {seen[text]}.*")
            else:
                seen[text] = f"{n}.{i}"
                out.append(text)
            out.append("")
    REVIEW.write_text("\n".join(out), encoding="utf-8")
    print(f"review file : {REVIEW}")

    # --- label sheet: never overwrite labels already made ---------------
    if LABELS.exists():
        print(f"label sheet : {LABELS} exists, left untouched")
    else:
        LABELS.parent.mkdir(parents=True, exist_ok=True)
        with LABELS.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["company_id", "company_name", "is_correct", "reason"])
            for c in sample:
                w.writerow([c["company_id"], c["company_name"], "", ""])
        print(f"label sheet : {LABELS} (empty, fill in is_correct + reason)")

    ids = ", ".join(str(c["company_id"]) for c in sample)
    print("\nMark the sample in Postgres:")
    print(f"  update companies set in_eval_set = true where id in ({ids});")
    return 0


if __name__ == "__main__":
    sys.exit(main())
