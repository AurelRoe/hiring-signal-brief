#!/usr/bin/env python3
"""
D3: gather one company's postings for the signal-brief skill.

Applies the pipeline's role definition, read at run time from the exported
n8n workflow (node "Tag jobs"), so the skill cannot drift from the
pipeline. Prints the company's target-role postings as plain text. Writing
the brief is left to Claude, following prompts/brief_v1.md.

Usage:
    python scripts/brief.py "Tebi"              # live Arbeitnow feed
    python scripts/brief.py "Tebi" --snapshot   # frozen evaluation snapshot
"""

import argparse
import html
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

API = "https://www.arbeitnow.com/api/job-board-api"
WORKFLOW = Path("n8n/fetch-arbeitnow.json")
SNAPSHOT = Path("data/raw/eval_snapshot_3.json")
MIN_ROLES = 2  # the pipeline's pre-filter threshold


def load_rules():
    """Pull the four regexes out of the n8n 'Tag jobs' node."""
    workflow = json.loads(WORKFLOW.read_text(encoding="utf-8"))
    code = next((n["parameters"].get("jsCode", "") for n in workflow["nodes"]
                 if n["name"] == "Tag jobs"), None)
    if not code:
        sys.exit(f"Node 'Tag jobs' not found in {WORKFLOW}; role definition unavailable.")

    def grab(name):
        m = re.search(rf"const {name} = /(.+?)/([a-z]*);", code)
        if not m:
            sys.exit(f"'{name}' not found in the 'Tag jobs' node of {WORKFLOW}.")
        # re.ASCII: JavaScript's \b and \w are ASCII-only; match them exactly.
        return re.compile(m.group(1), re.IGNORECASE | re.ASCII)

    return grab("ROLES"), grab("MARKETING"), grab("MARKETING_EXCLUDE"), grab("LEGAL")


ROLES, MARKETING, MARKETING_EXCLUDE, LEGAL = load_rules()


def is_target_role(title: str) -> bool:
    if ROLES.search(title):
        return True
    return bool(MARKETING.search(title)) and not MARKETING_EXCLUDE.search(title)


def company_key(name: str) -> str:
    s = LEGAL.sub(" ", name or "")
    s = re.sub(r"[^\w\s]|_", " ", s)
    return re.sub(r"\s+", " ", s).strip().lower()


def to_text(raw: str) -> str:
    """Decode first (some postings are double-escaped), then drop tags."""
    s = html.unescape(html.unescape(raw or ""))
    s = re.sub(r"(?i)<br\s*/?>|</p>|</li>|</h\d>", "\n", s)
    s = re.sub(r"(?i)<li[^>]*>", "- ", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = re.sub(r"[ \t ]+", " ", s)
    return re.sub(r"\n\s*\n+", "\n\n", s).strip()


def live_jobs() -> list[dict]:
    jobs, session = [], requests.Session()
    session.headers["User-Agent"] = "hiring-signal-brief (portfolio project)"
    for page in range(1, 301):
        # The API rate-limits (HTTP 429). Wait as told and retry; if it still
        # refuses, stop: a brief from half the feed would silently miss postings.
        for attempt in range(5):
            r = session.get(API, params={"page": page}, timeout=60)
            if r.status_code != 429:
                break
            wait = int(r.headers.get("Retry-After", "") or 10 * (attempt + 1))
            print(f"  page {page}: rate-limited, waiting {wait}s", file=sys.stderr)
            time.sleep(wait)
        r.raise_for_status()
        batch = r.json().get("data", [])
        if not batch:
            break
        jobs.extend(batch)
        print(f"  page {page}: {len(jobs)} jobs", file=sys.stderr)
        time.sleep(1)  # be polite to a free API
    return jobs


def snapshot_jobs() -> list[dict]:
    companies = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    return [dict(j, company_name=c["company_name"],
                 created_at=j["posted_at"], description=j["description"])
            for c in companies for j in c["jobs"]]


def posted(value) -> str:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, timezone.utc).strftime("%Y-%m-%d")
    return str(value or "")[:10]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("company")
    ap.add_argument("--snapshot", action="store_true",
                    help="use the frozen evaluation snapshot instead of the live feed")
    args = ap.parse_args()

    if args.snapshot:
        source = "Arbeitnow (arbeitnow.com), frozen evaluation snapshot of 2026-11-22"
        jobs = snapshot_jobs()
    else:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        source = f"Arbeitnow (arbeitnow.com), live feed fetched {today}"
        print("Fetching the live Arbeitnow feed...", file=sys.stderr)
        jobs = live_jobs()

    key = company_key(args.company)
    seen, mine = set(), []
    for j in jobs:
        if company_key(j.get("company_name", "")) == key and j["slug"] not in seen:
            seen.add(j["slug"])
            mine.append(j)

    if not mine:
        near = sorted({j.get("company_name", "") for j in jobs
                       if key and key in company_key(j.get("company_name", ""))})
        print(f"No postings for '{args.company}' in {source}.")
        if near:
            print("Similar company names: " + ", ".join(near[:5]))
        return 1

    targets = [j for j in mine if is_target_role(j.get("title", ""))]
    print(f"Company: {mine[0]['company_name']}")
    print(f"Source: {source}")
    print(f"Postings: {len(mine)} in total, {len(targets)} matching the role definition "
          f"(pipeline threshold: {MIN_ROLES})")
    if len(targets) < MIN_ROLES:
        print(f"Below the threshold: by the pipeline's rule this is no hiring signal.")
    if not targets:
        return 0

    shown: dict[str, int] = {}
    for i, j in enumerate(targets, 1):
        print(f"\n### Posting {i}: {j['title']}")
        print(f"Location: {j.get('location') or 'unknown'} | Posted: {posted(j.get('created_at'))}"
              f" | {j.get('url', '')}")
        text = to_text(j.get("description", ""))
        if text in shown:
            print(f"Description identical to posting {shown[text]}.")
        else:
            shown[text] = i
            print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
