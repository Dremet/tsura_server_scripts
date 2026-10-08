# TSURA Server Scripts

Collection of scripts used on dedicated servers for Turbo Sliders Unlimited within the TSURA community, see https://tsura.org

## Servers

- **Career** (seasonal championship, per-driver tuned cars): see [career/OPERATIONS.md](career/OPERATIONS.md) for the operations runbook, [career/CAREER_ACTIVATION.md](career/CAREER_ACTIVATION.md) for the historical activation record, and [career/career_tools/README.md](career/career_tools/README.md) for the `.veh` generation tools.
- **Topdown** (automatic heats, top-down camera, port 7761): needs a long-running
  controller rather than cron -- see [topdown/README.md](topdown/README.md).
- **Fun Modes** (Sumo, Capture the Flag; manually hosted, port 7757): see [fun/README.md](fun/README.md). Result files are only archived, not evaluated yet.
- **events / tripleheat / hotlapping**: per-server `server/config/Scripts/` (autorun + event hooks).
- **casualheat**: retired 2026-10-08, kept for reference, see [casualheat/RETIRED.md](casualheat/RETIRED.md).
