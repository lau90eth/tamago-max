# TAMAGO-MAX

Automated bug bounty hunter. Monitors bug bounty programs, analyzes contracts, generates reports.

## Stack
- recon0 — environment setup + attack surface mapping
- Slither — static analysis  
- Claude API — AI-powered vulnerability analysis
- UFR — trustless bounty splits if working in team

## Pipeline
```
Target URL → recon0 --json → AI analysis → Report draft → Manual review → Submit
```

## Status
🚧 In development
