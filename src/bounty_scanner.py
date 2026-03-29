#!/usr/bin/env python3
"""
bounty_scanner.py — fetch bounty targets da Code4rena (GitHub) e Cantina
"""

import requests
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone

@dataclass
class BountyTarget:
    platform: str
    name: str
    repo_url: str
    reward_pool: str
    ends_at: str

def fetch_code4rena() -> list[BountyTarget]:
    """Legge i contest attivi dal repo GitHub ufficiale di Code4rena."""
    targets = []
    try:
        r = requests.get(
            "https://api.github.com/repos/code-423n4/code423n4.com-_data/contents/contests",
            headers={"Accept": "application/vnd.github.v3+json"},
            timeout=10
        )
        files = r.json()
        now = datetime.now(timezone.utc)

        for f in files:
            if not f["name"].endswith(".json"):
                continue
            cr = requests.get(f["download_url"], timeout=10)
            c = cr.json()

            # Controlla se è attivo
            end_str = c.get("end_time", "")
            try:
                end_dt = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
                if end_dt < now:
                    continue
            except:
                continue

            repo = c.get("repo", "")
            targets.append(BountyTarget(
                platform="code4rena",
                name=c.get("title", f["name"]),
                repo_url=repo,
                reward_pool=str(c.get("amount", "?")),
                ends_at=end_str
            ))
    except Exception as e:
        print(f"[code4rena] error: {e}")
    return targets

def fetch_cantina() -> list[BountyTarget]:
    """Scrapa bounty attivi da Cantina."""
    targets = []
    try:
        r = requests.get(
            "https://cantina.xyz/api/competitions",
            params={"status": "open"},
            timeout=10
        )
        if r.status_code != 200:
            print(f"[cantina] HTTP {r.status_code}")
            return targets
        data = r.json()
        for c in data.get("competitions", data if isinstance(data, list) else []):
            repo = c.get("repoUrl") or c.get("repo_url") or c.get("repo") or ""
            targets.append(BountyTarget(
                platform="cantina",
                name=c.get("name") or c.get("title") or "",
                repo_url=repo,
                reward_pool=str(c.get("prizePool") or c.get("prize_pool") or "?"),
                ends_at=c.get("endDate") or c.get("end_date") or ""
            ))
    except Exception as e:
        print(f"[cantina] error: {e}")
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
    targets = fetch_code4rena() + fetch_cantina()
    print(f"Found {len(targets)} active targets\n")

    results = []
    for t in targets:
        print(f"  [{t.platform}] {t.name} | ${t.reward_pool} | ends: {t.ends_at}")
        if not t.repo_url:
            print(f"    SKIP — no repo URL")
            continue

        print(f"    Analyzing: {t.repo_url}")
        analysis = analyze_with_recon0(t.repo_url)
        if not analysis:
            continue

        score = analysis.get("score", {}).get("score", 0)
        findings = analysis.get("findings", [])
        highs = [f for f in findings if f.get("severity") == "high"]
        print(f"    Score: {score}/100 | Findings: {len(findings)} ({len(highs)} HIGH)")

        results.append({
            "target": t.__dict__,
            "analysis": analysis,
            "priority": len(highs) * 10 + score
        })

    results.sort(key=lambda x: x["priority"], reverse=True)

    with open("bounty_scan_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved {len(results)} results to bounty_scan_results.json")

    if results:
        print("\nTop targets:")
        for r in results[:3]:
            t = r["target"]
            s = r["analysis"]["score"]["score"]
            print(f"  {t['name']} — score {s}/100 — ${t['reward_pool']}")

    return results

if __name__ == "__main__":
    scan_all()
