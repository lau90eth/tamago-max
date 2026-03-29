#!/usr/bin/env python3
"""
bounty_scanner.py — fetch bounty targets attivi
Fonti: Code4rena (GitHub repos), Sherlock (API pubblica)
"""

import requests
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone

GITHUB_TOKEN = ""  # opzionale, aumenta rate limit

@dataclass
class BountyTarget:
    platform: str
    name: str
    repo_url: str
    reward_pool: str
    ends_at: str

def github_headers():
    h = {"Accept": "application/vnd.github.v3+json"}
    if GITHUB_TOKEN:
        h["Authorization"] = f"token {GITHUB_TOKEN}"
    return h

def fetch_code4rena() -> list[BountyTarget]:
    """Cerca repo Code4rena attivi con pattern YYYY-MM-*"""
    targets = []
    try:
        now = datetime.now(timezone.utc)
        year = now.year
        month = now.month

        # Cerca repo del mese corrente e precedente
        for y, m in [(year, month), (year, month-1 if month > 1 else 12)]:
            prefix = f"2026-{m:02d}" if y == 2026 else f"{y}-{m:02d}"
            r = requests.get(
                f"https://api.github.com/orgs/code-423n4/repos",
                params={"per_page": 100, "sort": "created", "direction": "desc"},
                headers=github_headers(),
                timeout=10
            )
            if r.status_code != 200:
                break
            repos = r.json()
            for repo in repos:
                name = repo.get("name", "")
                if not name.startswith(prefix):
                    continue
                # Repo attivo = creato di recente e non archiviato
                if repo.get("archived"):
                    continue
                targets.append(BountyTarget(
                    platform="code4rena",
                    name=name,
                    repo_url=repo.get("html_url", ""),
                    reward_pool="?",
                    ends_at=repo.get("created_at", "")
                ))
    except Exception as e:
        print(f"[code4rena] error: {e}")
    return targets

def fetch_sherlock() -> list[BountyTarget]:
    """Fetch contest attivi da Sherlock."""
    targets = []
    try:
        r = requests.get(
            "https://mainnet-contest.sherlock.xyz/contests",
            timeout=10
        )
        if r.status_code != 200:
            print(f"[sherlock] HTTP {r.status_code}")
            return targets
        contests = r.json()
        now = datetime.now(timezone.utc)
        for c in contests:
            # Filtra solo attivi
            ends = c.get("ends_at", "")
            try:
                end_dt = datetime.fromisoformat(ends.replace("Z", "+00:00"))
                if end_dt < now:
                    continue
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
                ends_at=ends
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

def scan_all():
    print("Fetching active bounties...")
    targets = fetch_code4rena() + fetch_sherlock()
    print(f"Found {len(targets)} active targets\n")

    for t in targets:
        print(f"  [{t.platform}] {t.name} | ${t.reward_pool} | {t.repo_url}")

    results = []
    for t in targets:
        if not t.repo_url:
            continue
        print(f"\nAnalyzing: {t.name}")
        analysis = analyze_with_recon0(t.repo_url)
        if not analysis:
            continue
        score = analysis.get("score", {}).get("score", 0)
        findings = analysis.get("findings", [])
        highs = [f for f in findings if f.get("severity") == "high"]
        print(f"  Score: {score}/100 | {len(highs)} HIGH findings")
        results.append({
            "target": t.__dict__,
            "analysis": analysis,
            "priority": len(highs) * 10 + score
        })

    results.sort(key=lambda x: x["priority"], reverse=True)
    with open("bounty_scan_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved {len(results)} analyzed targets")
    return results

if __name__ == "__main__":
    scan_all()
