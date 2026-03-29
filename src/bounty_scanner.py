#!/usr/bin/env python3
"""
bounty_scanner.py — fetch bounty targets attivi con date reali da README
"""

import requests
import json
import subprocess
import base64
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

GITHUB_TOKEN = ""

@dataclass 
class BountyTarget:
    platform: str
    name: str
    repo_url: str
    reward_pool: str = "?"
    ends_at: str = ""
    is_active: bool = False

def github_headers():
    h = {"Accept": "application/vnd.github.v3+json"}
    if GITHUB_TOKEN:
        h["Authorization"] = f"token {GITHUB_TOKEN}"
    return h

def parse_readme_dates(repo_full_name: str) -> dict:
    """Estrae date e prize pool dal README del repo."""
    try:
        r = requests.get(
            f"https://api.github.com/repos/{repo_full_name}/contents/README.md",
            headers=github_headers(), timeout=10
        )
        if r.status_code != 200:
            return {}
        content = base64.b64decode(r.json()["content"]).decode()

        ends_match = re.search(
            r"Ends?\s+(\w+\s+\d+,?\s+\d{4})", content, re.IGNORECASE
        )
        prize_match = re.search(
            r"Total Prize Pool.*?\$([0-9,]+)", content, re.IGNORECASE
        )

        ends_str = ends_match.group(1) if ends_match else ""
        prize = prize_match.group(1).replace(",", "") if prize_match else "?"

        # Parse data
        is_active = False
        if ends_str:
            try:
                end_dt = datetime.strptime(ends_str.strip(), "%B %d, %Y")
                end_dt = end_dt.replace(tzinfo=timezone.utc)
                is_active = end_dt > datetime.now(timezone.utc)
            except:
                try:
                    end_dt = datetime.strptime(ends_str.strip(), "%B %d %Y")
                    end_dt = end_dt.replace(tzinfo=timezone.utc)
                    is_active = end_dt > datetime.now(timezone.utc)
                except:
                    pass

        return {"ends_at": ends_str, "prize": prize, "is_active": is_active}
    except Exception as e:
        return {}

def fetch_code4rena() -> list[BountyTarget]:
    targets = []
    try:
        now = datetime.now(timezone.utc)
        r = requests.get(
            "https://api.github.com/orgs/code-423n4/repos",
            params={"per_page": 50, "sort": "created", "direction": "desc"},
            headers=github_headers(), timeout=10
        )
        if r.status_code != 200:
            print(f"[code4rena] HTTP {r.status_code}")
            return targets

        repos = r.json()
        year = now.year

        for repo in repos:
            name = repo.get("name", "")
            # Solo repo contest (pattern YYYY-MM-*)
            if not re.match(r"^\d{4}-\d{2}-\w+$", name):
                continue
            if repo.get("archived"):
                continue

            full_name = repo.get("full_name", f"code-423n4/{name}")
            meta = parse_readme_dates(full_name)

            targets.append(BountyTarget(
                platform="code4rena",
                name=name,
                repo_url=repo.get("html_url", ""),
                reward_pool=meta.get("prize", "?"),
                ends_at=meta.get("ends_at", ""),
                is_active=meta.get("is_active", False)
            ))

    except Exception as e:
        print(f"[code4rena] error: {e}")
    return targets

def fetch_sherlock() -> list[BountyTarget]:
    targets = []
    try:
        r = requests.get(
            "https://mainnet-contest.sherlock.xyz/contests",
            timeout=10
        )
        if r.status_code != 200:
            return targets
        data = r.json()
        if not isinstance(data, list):
            return targets
        now = datetime.now(timezone.utc)
        for c in data:
            if not isinstance(c, dict):
                continue
            ends = c.get("ends_at", "")
            is_active = False
            try:
                end_dt = datetime.fromisoformat(ends.replace("Z", "+00:00"))
                is_active = end_dt > now
            except:
                pass
            repo = c.get("template_repo_name", "")
            if repo:
                repo = f"https://github.com/sherlock-audit/{repo}"
            targets.append(BountyTarget(
                platform="sherlock",
                name=c.get("title", ""),
                repo_url=repo,
                reward_pool=str(c.get("prize_pool", "?")),
                ends_at=ends,
                is_active=is_active
            ))
    except Exception as e:
        print(f"[sherlock] error: {e}")
    return targets

def analyze_with_recon0(repo_url: str) -> dict | None:
    if not repo_url or not repo_url.startswith("http"):
        return None
    try:
        result = subprocess.run(
            ["recon0", repo_url, "--json"],
            capture_output=True, text=True, timeout=300
        )
        output = result.stdout
        json_start = output.find('{')
        if json_start == -1:
            return None
        return json.loads(output[json_start:])
    except Exception as e:
        print(f"  [recon0] error: {e}")
        return None

def scan_all(active_only: bool = True):
    print("Fetching bounty targets...")
    all_targets = fetch_code4rena() + fetch_sherlock()

    active = [t for t in all_targets if t.is_active] if active_only else all_targets
    inactive = [t for t in all_targets if not t.is_active]

    print(f"\nACTIVE ({len(active)}):")
    for t in active:
        print(f"  [{t.platform}] {t.name} | ${t.reward_pool} | ends: {t.ends_at}")

    print(f"\nCLOSED ({len(inactive)}):")
    for t in inactive:
        print(f"  [{t.platform}] {t.name} | ends: {t.ends_at}")

    if not active:
        print("\nNo active contests right now. Run again later or check manually.")
        return []

    print(f"\nAnalyzing {len(active)} active targets...")
    results = []
    for t in active:
        if not t.repo_url:
            continue
        print(f"\n  Analyzing: {t.name} (${t.reward_pool})")
        analysis = analyze_with_recon0(t.repo_url)
        if not analysis:
            continue
        score = analysis.get("score", {}).get("score", 0)
        findings = analysis.get("findings", [])
        highs = [f for f in findings if f.get("severity") == "high"]
        print(f"  Score: {score}/100 | {len(highs)} HIGH | {len(findings)} total findings")
        results.append({
            "target": t.__dict__,
            "analysis": analysis,
            "priority": len(highs) * 10 + score
        })

    results.sort(key=lambda x: x["priority"], reverse=True)
    with open("bounty_scan_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved {len(results)} results.")
    return results

if __name__ == "__main__":
    scan_all()
