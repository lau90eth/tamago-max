#!/usr/bin/env python3
"""
bounty_scanner.py — scrapa bounty attivi da Code4rena e Cantina
Output: lista di target con URL repo, reward pool, scadenza
"""

import requests
import json
import subprocess
import os
from dataclasses import dataclass
from datetime import datetime

@dataclass
class BountyTarget:
    platform: str
    name: str
    repo_url: str
    reward_pool: str
    ends_at: str
    scope_urls: list[str]

def fetch_code4rena() -> list[BountyTarget]:
    """Scrapa contest attivi da Code4rena API."""
    targets = []
    try:
        r = requests.get("https://code4rena.com/api/contests", timeout=10)
        data = r.json()
        for c in data:
            if c.get("status") != "active":
                continue
            targets.append(BountyTarget(
                platform="code4rena",
                name=c.get("title", ""),
                repo_url=c.get("repo", ""),
                reward_pool=str(c.get("amount", "?")),
                ends_at=c.get("end_time", ""),
                scope_urls=[c.get("repo", "")] if c.get("repo") else []
            ))
    except Exception as e:
        print(f"[code4rena] error: {e}")
    return targets

def fetch_cantina() -> list[BountyTarget]:
    """Scrapa bounty attivi da Cantina."""
    targets = []
    try:
        r = requests.get("https://cantina.xyz/api/competitions?status=open", timeout=10)
        data = r.json()
        for c in data.get("competitions", []):
            repo = c.get("repoUrl", "") or c.get("repo_url", "")
            targets.append(BountyTarget(
                platform="cantina",
                name=c.get("name", c.get("title", "")),
                repo_url=repo,
                reward_pool=str(c.get("prizePool", c.get("prize_pool", "?"))),
                ends_at=c.get("endDate", c.get("end_date", "")),
                scope_urls=[repo] if repo else []
            ))
    except Exception as e:
        print(f"[cantina] error: {e}")
    return targets

def analyze_with_recon0(target: BountyTarget) -> dict | None:
    """Lancia recon0 --json sul repo del target."""
    if not target.repo_url:
        return None
    try:
        result = subprocess.run(
            ["recon0", target.repo_url, "--json"],
            capture_output=True, text=True, timeout=300
        )
        output = result.stdout
        json_start = output.find('{')
        if json_start == -1:
            return None
        return json.loads(output[json_start:])
    except Exception as e:
        print(f"[recon0] error on {target.repo_url}: {e}")
        return None

def scan_all():
    """Scan completo di tutti i bounty attivi."""
    print("Fetching active bounties...")
    targets = fetch_code4rena() + fetch_cantina()
    print(f"Found {len(targets)} active targets")

    results = []
    for t in targets:
        if not t.repo_url:
            print(f"  SKIP {t.name} — no repo URL")
            continue

        print(f"\n  Analyzing: {t.name} ({t.platform})")
        print(f"  Repo: {t.repo_url}")
        print(f"  Pool: ${t.reward_pool}")

        analysis = analyze_with_recon0(t)
        if analysis:
            score = analysis.get("score", {}).get("score", 0)
            findings = analysis.get("findings", [])
            highs = [f for f in findings if f.get("severity") == "high"]

            print(f"  Score: {score}/100")
            print(f"  Findings: {len(findings)} ({len(highs)} HIGH)")

            results.append({
                "target": t.__dict__,
                "analysis": analysis,
                "priority": len(highs) * 10 + score
            })

    # Ordina per priorità
    results.sort(key=lambda x: x["priority"], reverse=True)

    # Salva report
    with open("bounty_scan_results.json", "w") as f:
        json.dump(results, f, indent=2)

    print(f"\nTop targets:")
    for r in results[:5]:
        t = r["target"]
        print(f"  {t['name']} ({t['platform']}) — score {r['analysis']['score']['score']}/100 — ${t['reward_pool']}")

    return results

if __name__ == "__main__":
    scan_all()
