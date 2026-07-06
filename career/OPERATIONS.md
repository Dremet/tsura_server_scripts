# TSU Career — Operations Guide

Living runbook for the TSURA **Career** server (seasonal championship with
per-driver tuned cars, `tsura.org/career`). For the one-time activation record
see `CAREER_ACTIVATION.md` (historical); this file is the day-to-day reference.

- **Host:** carrot. **Server user:** `career`, port **7765** (`TSUs.x86_64 -public -port 7765 -setup plain`).
- **Website:** Flask app `tsura2` (repo `Dremet/tsura2`), served for `tsura.org`.
- **Pipeline:** ingestion under user `data` (`/home/data/tsu_pipeline`), cron every minute.
- **DB:** Postgres `tsu`, schema `career.*` + `mart.v_career_*` views (owned by `postgres`).

All career-user files need `sudo -u career …` (the `claude` user's EACCES otherwise).

---

## 1. Running a session

### Automatic — every Monday 21:00 (`crontab -u career`)
```
55 20 * * 1  /home/career/run_prepare.sh            # generate tuned cars
59 20 * * 1  … create_autorun.py announce_1_minute  # in-game "1 minute" warning
00 21 * * 1  … create_autorun.py start_session       # /refreshfiles, queue 2 tracks × (quali+race), force cars, broadcast builds
00 23 * * 1  … create_autorun.py skip_to_new_session # wind down
```

Independent of the Monday schedule, **every minute**:
```
* * * * *  /home/career/process_build_requests.sh   # admin "build & assign car" queue (§8)
```
Nothing to do — it runs itself. Drivers do NOT need to be in the lobby at start:
`/forcevehicle` is re-issued at every event, so a driver's tuned car applies from
the next quali/race after they join.

### Spontaneous — `host_session.sh`
```
sudo -u career /home/career/host_session.sh start [minutes]   # default 120 min
sudo -u career /home/career/host_session.sh stop              # wind down now
sudo -u career /home/career/host_session.sh status            # server + session state
```
Same flow as the Monday cron (prepare → announce → 60 s → start; auto wind-down
after `minutes`). Safe by design: refuses to start while a session is active
(`session_active` lock) or while the server is offline (it would otherwise hang
waiting for `autorun.src` to be consumed). Generating cars manually anytime:
`sudo -u career /home/career/run_prepare.sh` (refuses mid-session).

---

## 2. How it works (data flow)

```
run_prepare.sh ─► career_tools/career_prepare_session.py
    └─ reads mart.v_career_driver_cars (final tuning per driver)
    └─ writes per-driver .veh into server/config/Vehicles/  +  assignments.json (incl. focus text)

create_autorun.py start_session ─► writes autorun.src (server consumes it)
    └─ /refreshfiles, /admins, queue tracks, broadcast "Tonight's builds"

per event: TSU fires the hook chain ─► run_event_init.py ─► event_init_generated.src
    └─ /refreshfiles, quali (Hotlapping 3 laps) OR race settings, /vehicles + /forcevehicle per Steam-ID

race end ─► move_raw_files.sh ─► /home/data/career/<ts>/raw/*  +  new_career_files.trigger
    └─ pipeline (user data): loads base.* + tire telemetry, computes career.race_rewards (points + credits)

website tsura.org/career reads mart.v_career_* views
```

Only **race** events produce rewards + tire telemetry; **qualis** run in Hotlapping
mode (no tires, no rewards) and only set the grid for the following race
(`race.startingOrder = Last Event`).

---

## 3. Tuning — 9 upgrade axes

Configured per season in `career.upgrade_axes`; each driver buys tiers in the web
garage. `final value = base_value + tier × step_per_tier`. Axis → `.veh` field
mapping lives in `career_tools/career_vehicles.py::TUNING_FIELDS` (must stay in
sync with the website's `AXES` list and the DB axis CHECK constraint).

**Performance:** Top Speed (`speed.maxSpeed`), Acceleration (`speed.engineFriction`,
higher = faster), Braking (`braking.braking`), Grip (`steering.grip`), Downforce
(`downforce.downforce`).
**Driveability (cheap):** Sliding Gradual Range (`sliding.gradualRange`), Spring Max
Length (`spring.maxLength`), Locking Start Time (`braking.lockingStartTime`),
Oversteering Braking (`oversteering.braking`).

Season-1 cost rule: ≈1000 credits per second of measured lap-time gain per tier;
driveability flat 100/tier.

---

## 4. Credits / economy

Computed in the pipeline (`career.py`) + the view `mart.v_career_credit_balance`:
- `POINTS = [20,16,12,10,8,6,5,4,3,2,1]` by finishing position.
- Per-race credits: linear, slower = more (P1 → `credit_first`, last → `credit_last`).
- **Backfill:** every enrolled driver who did NOT participate in a scored race gets
  that race's **average participant credits** — covers both late joiners and skipped
  races (migration 011). `balance = start_credits + earned + backfill − spent`.
- **Undo:** the garage's "undo last upgrade" reverts exactly the most recent purchase
  (one step, `career.last_purchase`); refund is implicit.
- **Current Alpha Season:** `start_credits=1000`, `credit_first=200` (P1), `credit_last=600`
  (last). Payout is linear in between (P1 200 → P2 300 → … → last 600).
- **Changing a season's `credit_first`/`credit_last` is NOT retroactive** — stored
  `career.race_rewards.credits` keep their old values. To apply new payouts to past
  races, recompute: as user `data` with the pipeline env, run
  `tsu_pipeline.career.compute_career_rewards(session_ids, cur)` over the season's
  race sessions (`SELECT DISTINCT session_id FROM career.race_rewards WHERE season_id=…`);
  it upserts credits/points idempotently and balances/backfill follow via the views.

---

## 5. Broadcasts (Unity rich text)

Generated `/broadcast` lines use TMP rich text. Scheme: per-server colour badge
(`[Career]` `#ffc107`), `<color=#aaaaaa>` for secondary notes, `<mspace=0.6em>` +
`<noparse>` for aligned tables. **TSU chat does NOT support `<b>`** — it renders the
closing tag literally as "/b"; never use bold. At session start the server also
broadcasts each driver's tuning focus ("focused on X & Y" / "all-in" / "balanced" /
stock list), computed at prep time into `assignments.json`.

Ad-hoc messages: write lines to `server/config/Scripts/autorun.src` (the server
consumes and deletes it within seconds). Always wait for the file to be absent
before writing, so you don't clobber a pending session command.

**Reading player chat:** `server/config/Logs/log.<date>.txt`, lines formatted
`<[TAG] Name> message`.

---

## 6. Gotchas & lessons learned

| Symptom | Cause / rule |
|---|---|
| A driver's `.veh` won't load ("Invalid format, 312 vs …") | **Vehicle name limit is 20 chars** (metadata says 40 — stale). Names are capped in `career_vehicles` + `_unique_name`. |
| Weird filenames / broken `/forcevehicle` | Generated `.veh` filenames must have **no spaces** (→ `_`); vehicle display names have apostrophes stripped (they break quoted commands). |
| A fixed `.veh` doesn't appear until next event | `/refreshfiles` is **ignored mid-event**; it's emitted at every event init instead. |
| A restarted event flips quali↔race | **Fixed 2026-07-06:** the mode now only advances when an event actually finished (`run_event_end` drops `career_event_done`); a restart fires event-init without an event-end, so the mode is kept. |
| Career/casual-heat races show no tire stints | Telemetry loader was gated to events/tripleheat; now includes `career`+`casual_heat` (pipeline `loader.py`). |
| Literal `\uXXXX` shows up on a web page | In a **Python** string `\uXXXX` decodes to the char, but written into an **HTML/Jinja template** the text `\uXXXX` renders as-is. Always put **real** unicode chars (—, …, ’) in template HTML, never `\u` escapes. |
| `host_session.sh start` hangs | Server offline — nothing consumes `autorun.src`. The script now refuses when offline; start the server first (`restart_server.sh`, ~60 s). |

`restart_server.sh` clears stale `session_active` + `autorun.src` on boot.

---

## 7. Repos & deploy

- **Server scripts** (this repo, `Dremet/tsura_server_scripts`, branch **main**):
  `career/` mirrors `/home/career/…`. Edit under `/home/dremet/…`, commit, push;
  copy to the live `career` user paths.
- **Website** (`Dremet/tsura2`, branch master): edit `/home/dremet/tsura/tsura2`,
  push, `sudo -u tsura git -C /home/tsura/tsura2 pull --ff-only`, restart the
  gunicorn user service.
- **Pipeline / DB migrations** (`Dremet/tsu_pipeline`): SQL in `migrations/`, applied
  to the prod DB **as `postgres`** (not auto-run by a pull).

  Applied migrations incl.: `012_career_penalties` (standings penalties),
  `013_career_build_requests` (admin build-&-assign-car queue).

---

## 8. Admin actions on the website (`tsura.org/career/admin`, admins only)

- **Give / remove penalty points** — affects the **overall standings only**
  (`career.penalties`, season-scoped, netted into `mart.v_career_standings.points_total`).
  The standings page lists each penalty (when / who / points / why).
- **Rebuild & assign a car** — for a driver who upgraded late. The website (role
  `tsura`) can't write career files, so the button just enqueues into
  `career.car_build_requests` (migration 013). The career cron
  `process_build_requests.py` (every minute) then, per pending row:
  builds that one driver's `.veh` from current DB tuning, updates `assignments.json`,
  and — if the server is up — forces it live via `autorun.src`
  (`/refreshfiles` + `/vehicles /add` + `/forcevehicle` + a broadcast); otherwise it
  applies from the next event. Marks the row `done`/`error` with a note (shown on the
  admin page). Safe mid-session (single car, no `session_active` lock).
  Grants: `tsura` INSERT/SELECT, `career_ro` SELECT/UPDATE on the table.
- **Create / activate a season** — the new-season form is **prefilled from the active
  season's** config (start/credit_first/credit_last + per-axis base/step/max/cost), so
  it clones the current setup. Activating one sets the previous active season to
  `finished` (only one active at a time).

### Season-scoped vs global (what resets on a new season)
- **Global (persist):** `allowed_participants` (beta allowlist), `admins`.
- **Per season (reset):** enrollments, upgrades, credits/balance, `last_purchase`,
  `upgrade_axes`, `race_rewards`, `penalties`, `car_build_requests`. Drivers must
  **re-enroll** each season; old seasons stay viewable via the season dropdown.

## 9. Website UI notes

- **Upgrade overview** (`/career/upgrades`): per-axis **competitive grade** relative to
  the field — **S** (purple) maxed, **A** field-leading (nobody higher, not maxed),
  **B–E** ranked vs the strongest car, **F** stock. Exact tuned values are hidden.
  Route helper `_field_grade(tier, max_tier, field_max_tier)`. A **Spent** column shows
  total credits spent; drivers are sorted by it. Grade columns sort by rank via a
  numeric `data-sort` (S=6 … F=0), not alphabetically.
- **Sortable tables:** global click-to-sort JS in `base.html`; a `<th data-nosort>`
  opts a column out (action/button columns like *Details*). A `<td data-sort="N">`
  overrides a cell's sort key.
- **Upgrade-deadline countdown** (Mon 20:55 CEST): any element with class `js-deadline`
  is filled by the global handler in `base.html` — used big on the garage and on the
  career home box.
- **Naming:** display labels are **Triple Heat** / **Casual Heat** (internal server keys
  stay `tripleheat` / `casual_heat`). The front-page server cards colour the card
  **header** itself (no badge). The online-servers list still shows each game server's
  own self-reported name (e.g. "#3 TripleHeat/…") — that's live data, not a label.
