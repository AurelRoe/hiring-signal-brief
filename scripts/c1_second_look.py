#!/usr/bin/env python3
"""
C4: documented second look at C1 labels that both models dispute.

Selects, by query, the companies where BOTH models' is_real_signal differs
from the hand label. Writes:
  data/raw/c1_second_look.md       postings only, no model output (gitignored)
  data/labels/c1_second_look.csv   original label + empty reviewed label
                                   (committed; never overwritten)

The original labels in data/labels/c1_signal.csv are not touched. This
review is not blind: the model verdicts were known when it was done.

Usage:
    python scripts/c1_second_look.py
"""

import csv
import hashlib
import html
import json
import subprocess
import sys
from pathlib import Path

from c1_sample import SNAPSHOT, SNAPSHOT_SHA256, html_to_text

QUERY = """
select coalesce(json_agg(x order by x.company_name), '[]') from (
    select c.id as company_id, c.company_name, s.is_correct as original
    from companies c
    join labels_signal s on s.company_id = c.id
    join briefs h on h.company_id = c.id and h.model = 'claude-haiku-5-5' and h.run_label = 'v1'
    join briefs o on o.company_id = c.id and o.model = 'claude-opus-5-5'  and o.run_label = 'v1'
    where h.is_real_signal <> s.is_correct and o.is_real_signal <> s.is_correct
) x;
"""

REVIEW = Path("data/raw/c1_second_look.md")
SHEET = Path("data/labels/c1_second_look.csv")


def main() -> int:
    raw = SNAPSHOT.read_bytes()
    if hashlib.sha256(raw).hexdigest() != SNAPSHOT_SHA256:
        print("Snapshot hash mismatch. Refusing to run.", file=sys.stderr)
        return 1
    companies = {c["company_id"]: c for c in json.loads(raw)}

    out = subprocess.run(
        ["docker", "compose", "exec", "-T", "postgres", "psql", "-U", "hsb",
         "-d", "hiring_signal", "-At", "-c", QUERY],
        check=True, capture_output=True, text=True,
    ).stdout
    disputed = json.loads(out)
    print(f"disputed by both models: {len(disputed)}")

    lines = ["# C1 second look — labels disputed by both models", "",
             "Re-read against `data/labels/c1_rubric.md`. Change a label only if a",
             "rule clearly applies. Model output is deliberately not shown.", ""]
    for n, d in enumerate(disputed, 1):
        c = companies[d["company_id"]]
        lines += ["---", "",
                  f"## {n}. {c['company_name']}  (company_id {c['company_id']}, "
                  f"original label: {'true' if d['original'] else 'false'})", ""]
        seen: dict[str, str] = {}
        for i, j in enumerate(c["jobs"], 1):
            lines += [f"### {n}.{i} {j['title']}",
                      f"{j['location'] or '?'} · {j['posted_at'][:10]} · {j['url']}", ""]
            # Decode once first: some postings are double-escaped
            # (`&lt;strong&gt;`), which html_to_text alone leaves as tags.
            text = html_to_text(html.unescape(j["description"] or ""))
            if text in seen:
                lines.append(f"*Description identical to {seen[text]}.*")
            else:
                seen[text] = f"{n}.{i}"
                lines.append(text)
            lines.append("")
    REVIEW.write_text("\n".join(lines), encoding="utf-8")
    print(f"review file : {REVIEW}")

    if SHEET.exists():
        print(f"sheet       : {SHEET} exists, left untouched")
    else:
        with SHEET.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["company_id", "company_name", "original_is_correct",
                        "reviewed_is_correct", "reason"])
            for d in disputed:
                w.writerow([d["company_id"], d["company_name"],
                            "true" if d["original"] else "false", "", ""])
        print(f"sheet       : {SHEET} (fill in reviewed_is_correct + reason)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
