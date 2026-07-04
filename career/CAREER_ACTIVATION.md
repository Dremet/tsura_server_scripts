# Career server — race-night activation

The automation scripts + vehicle tools are deployed but **dormant**: the running
test server still behaves normally until you enable them. Do these steps when
you want to switch the Career server into automated race-night mode.

## One-time setup
1. **Place the season base car**: put the chosen Workshop `.veh` on the server and
   set its path in the admin UI (career.seasons.base_vehicle_veh), e.g.
   `/home/career/career_base/season1.veh`.
2. **DB access for the prepare step**: `cp career_tools/.env.example career_tools/.env`
   and set `CAREER_DB_URL` (read-only role, or reuse `tsura`).
3. **Enable automatic scripts in `server/config/game.json`** (then restart):
   - `commands.automaticScripts = true`
   - `commands.generateStatsFiles = true`, `commands.generateDetailsLog = true`
   - set the starting order to **Last Event** so the race grid comes from the quali
     (the pole/quali-win point is derived from race `start_position = 1`).
4. **Switch the launcher to the plain setup** so the autorun drives levels/vehicles:
   in `restart_server.sh` use `-setup plain` (an empty `setup.plain.src` is deployed).

## Weekly crons (add to `crontab -u career`) — enable once a season is live
```
# ~15 min before the session: generate the tuned cars for enrolled drivers
45 20 * * 1  /home/career/run_prepare.sh >> /home/career/prepare.log 2>&1
# session flow (Mondays 21:00), mirrors the tripleheat/heat pattern
59 20 * * 1  cd /home/career/server/config/Scripts && python3 create_autorun.py announce_1_minute
00 21 * * 1  cd /home/career/server/config/Scripts && python3 create_autorun.py start_session
00 23 * * 1  cd /home/career/server/config/Scripts && python3 create_autorun.py skip_to_new_session
```
(The daily `steamcmd` + `restart_server.sh` crons at 04:45/05:45 are already installed.)

## Flow each Monday
20:45 `run_prepare.sh` → per-driver `.veh` into `config/Vehicles/` + `assignments.json`.
21:00 `start_session` → `/refreshfiles`, admins, 2 tracks queued twice (quali+race).
Per event `run_event_init.py` sets quali (Hotlapping, 3 laps) or race, and forces
each Steam-ID onto their car. Race end → `move_raw_files.sh` → `/home/data/career/…`
→ pipeline loads it (server='career', no ELO) and computes credits + points.

## ⚠️ Validate once live (could not be tested without real players)
- **`/forcevehicle <steamid> '<name>'`** by Steam-ID: the README says the `<player>`
  token accepts a Steam ID, but the shipped examples only show names / `/pos`.
  Do one test session with a real driver and confirm the forced car applies. If the
  Steam-ID form doesn't work, fall back to `/fv /pos <gridpos> '<name>'` driven off
  the quali order (edit `run_event_init.py::vehicle_commands`).
- **Starting order = Last Event**: confirm the race grid follows the quali result
  (so `start_position = 1` really is the pole/quali winner).
