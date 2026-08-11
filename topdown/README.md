# Topdown Heat Server (port 7761)

Automatic matchmaking: players join an empty server, a countdown runs, and a
**heat** plays out on its own -- per track a one-lap qualifying, then a race
whose grid comes from that qualifying. Everything is driven in top-down view,
i.e. with a forced overhead camera.

Unlike the other servers this one needs a **long-running controller**, not just
cron: the heat reacts to joins, chat and event ends in real time over the TSU
script port (`-scriptPort 7766`).

## Processes

| What | Started by |
|---|---|
| `TSUs.x86_64 -public -port 7761 -setup plain -scriptPort 7766` | `restart_server.sh` (nohup) |
| `topdown_controller.py` | `start_controller.sh` (setsid nohup, cron watchdog every minute) |

## Layout

```
topdown_controller.py     the controller: lobby, countdown, heat lifecycle
td/                       its modules
  heat.py                 which tracks, which car, how many laps, scoring
  session.py              builds the session archive for one heat
  camfile.py              read/write TSU camera files (.cam)
  guid.py                 GUID strings <-> the numbers in the session files
  machine.py              lobby/heat state machine
  protocol.py             parses the script port's lines
  webconfig.py            reads /srv/tsura/server_config/topdown.json
tests/                    offline tests; `python3 -m unittest discover -s tests`
session_parts/            parts bin for the session archive (McVizn's export)
  event.json              race settings template
  ai.json  vehicles.json  bot + car templates
  tracks/<slug>/          level.json + camera5.cam, one dir per track
server/config/Scripts/    the server's own hooks (session init, event init/end)
crontab                   daily update/restart, controller watchdog, upload perms
```

## Config

`/srv/tsura/server_config/topdown.json` is the source of truth (tracks, cars,
AI, drafting, cameras, in-game admins) and is edited at
[tsura.org/admin/topdown](https://tsura.org/admin/topdown). It is re-read at the
start of every heat, so config-only changes need **no** restart. Changing
`td/*.py` or `topdown_controller.py` does -- the controller imports them once at
startup.

Two keys shape a heat:

- **`vehicles`** is a pool; one car is drawn **per race**, not per heat, and
  every event in the archive carries its own `vehicles.json`. `weight: 0`
  benches a car. `drafting_by_vehicle` bends the shared `drafting` block per
  car, because the tow belongs to the car.
- **`tracks[].lap_bonus_pct`** overrides the global `lap_bonus_max_pct` for one
  track: races run 0 to x percent *more* laps than configured, never fewer.

A track only needs `camera_settings` once someone edits its camera in the panel
-- otherwise the exported `camera5.cam` is used byte for byte, and a re-export
still reaches the server. A track that was never exported is built from its name
and GUID alone and borrows a camera via `camera_from`, or gets the built-in
top-down default.

Not in this repo (deliberately): everything the controller generates at runtime
-- `heat_plan.json`, `heat_progress.json`, `topdown_heat.json`,
`*_generated.src`, `eventsettings.json`, logs.

## Things that bite

- **The session archive wins.** TSU reads a session container once, at session
  start, and ignores every later change. That is the only way to give each track
  its own camera. Consequence: while `plan["session_name"]` is set,
  `run_event_init.py` sends *no* per-event settings at all -- mode, laps, points,
  camera and drafting must all go into the ZIP.
- **GUID strings are base32** over `m_guid.a` / `m_guid.b`, alphabet
  `0123456789abcdefghjklmnpqrstvwxz` (no i, o, u, y). That is how a track in
  `topdown.json` is matched against its AI line file
  `AI/ai-<level>-<vehicle>.aid`.
- **`ai.aiSkill` is an enum, not a scale**: 1 Low, 2 Medium Low, 3 Medium,
  4 Medium High, 5 High, 10/11/12 Custom1..3 (these need an `AI/customN.aic` on
  the server!), 20 Test, 100 Mixed (only then do `aiSkillLevel1`/`2` matter).
- **`.cam` files** are a version byte plus three bitmask-prefixed blocks; a clear
  bit means "field has its default". `camfile.encode` round-trips every exported
  file byte for byte. Quirk: `tracksideInterval` is always written, even at its
  default. The camera's "zoom" is the `distance` field.
- **Qualifying results are discarded** by `move_raw_files.sh` (hotlapping mode
  yields no usable race stats); the pole point comes from the following race's
  start position.
