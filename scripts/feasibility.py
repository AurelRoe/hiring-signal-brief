#!/usr/bin/env python3
"""
Feasibility check for the Hiring Signal Brief pipeline.

Answers one question before any infrastructure gets built:
how many companies in the Arbeitnow feed have >= N open target roles?

Also writes a frozen snapshot to data/raw/ so the later evaluation
runs against identical input for both models.

Usage:
    python scripts/feasibility.py --pages 5
    python scripts/feasibility.py --pages 5 --min-roles 2 --no-save
"""

import argparse
import json
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import requests

API = "https://www.arbeitnow.com/api/job-board-api"

# Target functions per the project plan. Lowercase; matched against job title.
# German terms included -- the feed is German-language heavy.
ROLE_PATTERNS = [
    r"\bsales\b", r"\bvertrieb", r"\baccount executive\b", r"\baccount manager",
    r"\bsdr\b", r"\bbdr\b", r"\bbusiness development", r"\bmarketing",
    r"\bgrowth\b", r"\brevenue\b", r"\bkundenberater", r"\baußendienst",
    r"\bpre-?sales\b", r"\binside sales\b", r"\bpartner manager",
]
ROLE_RE = re.compile("|".join(ROLE_PATTERNS), re.IGNORECASE)

# Dropped from company names before grouping, so "Acme GmbH" and "Acme" merge.
LEGAL_SUFFIXES = re.compile(
    r"\b(gmbh|mbh|ag|se|kg|ohg|ug|e\.?\s?v\.?|co\.?\s?kg|holding|group|"
    r"deutschland|germany|inc\.?|ltd\.?|llc|b\.?v\.?)\b",
    re.IGNORECASE,
)


def normalize_company(name: str) -> str:
    """Group 'Acme GmbH & Co. KG' and 'Acme Group' as one company."""
    n = LEGAL_SUFFIXES.sub(" ", name or "")
    n = re.sub(r"[^\w\s]", " ", n)
    return re.sub(r"\s+", " ", n).strip().lower()


def fetch_pages(max_pages: int, pause: float = 1.0) -> list[dict]:
    """Walk ?page=N until a page comes back empty. No pagination metadata exists."""
    jobs, session = [], requests.Session()
    session.headers["User-Agent"] = "hiring-signal-brief/0.1 (portfolio project)"
    for page in range(1, max_pages + 1):
        try:
            r = session.get(API, params={"page": page}, timeout=60)
            r.raise_for_status()
            batch = r.json().get("data", [])
        except (requests.RequestException, ValueError) as e:
            print(f"  page {page}: FAILED ({e.__class__.__name__}: {e})", file=sys.stderr)
            break
        if not batch:
            print(f"  page {page}: empty -- end of feed")
            break
        jobs.extend(batch)
        print(f"  page {page}: {len(batch)} jobs (total {len(jobs)})")
        time.sleep(pause)  # be polite to a free API
    return jobs


def save_snapshot(jobs: list[dict], out_dir: Path) -> Path:
    """Freeze the raw feed. The evaluation must not re-fetch."""
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = out_dir / f"arbeitnow_{stamp}.json"
    path.write_text(json.dumps(jobs, ensure_ascii=False), encoding="utf-8")
    return path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", type=int, default=5)
    ap.add_argument("--min-roles", type=int, default=2)
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--no-save", action="store_true")
    ap.add_argument("--out", type=Path, default=Path("data/raw"))
    args = ap.parse_args()

    print(f"Fetching up to {args.pages} page(s) from Arbeitnow...")
    jobs = fetch_pages(args.pages)
    if not jobs:
        print("No jobs fetched. Nothing to assess.", file=sys.stderr)
        return 1

    if not args.no_save:
        print(f"\nSnapshot: {save_snapshot(jobs, args.out)}")

    # --- match target roles by title -------------------------------------
    matched = [j for j in jobs if ROLE_RE.search(j.get("title", ""))]

    by_company: dict[str, list[dict]] = defaultdict(list)
    display_name: dict[str, str] = {}
    for j in matched:
        key = normalize_company(j.get("company_name", ""))
        if not key:
            continue
        by_company[key].append(j)
        display_name.setdefault(key, j.get("company_name", "").strip())

    counts = {k: len(v) for k, v in by_company.items()}
    qualified = {k: n for k, n in counts.items() if n >= args.min_roles}

    # --- report ----------------------------------------------------------
    print("\n" + "=" * 64)
    print("FEASIBILITY")
    print("=" * 64)
    print(f"jobs fetched                  : {len(jobs)}")
    print(f"jobs matching target roles    : {len(matched)} "
          f"({len(matched) / len(jobs):.1%})")
    print(f"distinct companies (>=1 role) : {len(counts)}")
    for n in (2, 3, 4, 5):
        k = sum(1 for c in counts.values() if c >= n)
        mark = "  <-- threshold" if n == args.min_roles else ""
        print(f"distinct companies (>={n} roles) : {k}{mark}")

    print(f"\nVERDICT: {len(qualified)} companies clear the >={args.min_roles} "
          f"threshold. Need 30 for the evaluation set.")
    if len(qualified) >= 50:
        print("  -> Comfortable. Plan holds; start Day 1 as written.")
    elif len(qualified) >= 30:
        print("  -> Workable, but thin: the label set is nearly the whole")
        print("     population. Consider more pages or wider role keywords.")
    else:
        print("  -> TOO THIN. Fetch more pages, widen keywords, or redefine")
        print("     the signal before building the pipeline.")

    print(f"\nTop {args.top} companies by open target roles:")
    for key, n in sorted(counts.items(), key=lambda kv: -kv[1])[: args.top]:
        titles = ", ".join(sorted({j["title"][:40] for j in by_company[key]})[:3])
        print(f"  {n:>3}  {display_name[key][:34]:<34} {titles}")

    # Location is free text with no country field -- inspect before filtering.
    print("\nTop 15 locations among matched jobs (DACH filter must be string-based):")
    for loc, n in Counter(
        (j.get("location") or "?").strip() for j in matched
    ).most_common(15):
        print(f"  {n:>4}  {loc[:50]}")

    print("\nSample matched titles (sanity-check for false positives):")
    for t in sorted({j["title"] for j in matched})[:12]:
        print(f"  - {t[:70]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())