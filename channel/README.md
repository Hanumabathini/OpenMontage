# Channel studio

This folder is the working state of the owner's technology documentary channel. It is governed by [MASTER-DIRECTIVE.md](MASTER-DIRECTIVE.md).

| File | Purpose | Status |
|---|---|---|
| [SYSTEM-AUDIT.md](SYSTEM-AUDIT.md) | What is verified, untested, missing or broken | Cycle 1 done (24 Nov 2026) |
| [WANGP-INTEGRATION.md](WANGP-INTEGRATION.md) | `wangp_video` provider, laptop test steps, benchmarks | Built; laptop test pending |
| [DAILY-INTELLIGENCE.md](DAILY-INTELLIGENCE.md) | Index of research cycles | 1 limited cycle |
| [MONETIZATION-ROADMAP.md](MONETIZATION-ROADMAP.md) | Eligibility milestones, including the **Feb 1, 2027 YPP change** | Done |
| [PLATFORM-COMPLIANCE.md](PLATFORM-COMPLIANCE.md) | AI, originality, disclosure and copyright rules with sources | Done |
| [COMPETITOR-ANALYSIS.md](COMPETITOR-ANALYSIS.md) | Competitor benchmark list | Waiting for a YouTube Data API key |
| `TOPIC-RANKING.json` | Ranked topic candidates (provisional) | Cycle 1 |
| `*-LIBRARY.json`, `*-QUEUE.json`, `*-REGISTRY.json`, `*.csv` | Persistent state: empty schemas, `null` until real data exists | Initialized |

The `research/`, `production/`, `publishing/` and `analytics/` folders hold per-cycle outputs. Rendered media and secrets are never committed.

**Rules:**
- Never invent data. Use `null` for anything unavailable.
- Publishing, spending, and anything involving credentials, banking or tax data need the owner's explicit approval.
