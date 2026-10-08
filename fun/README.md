# Fun Modes server (user `fun`, ports 7757/7758)

Manually hosted server for the non-racing modes (Sumo, Capture the Flag, ...).
Replaces Casual Heat (retired 2026-10-08) and took over its ports and in-game
server slot; everything else (tracks, cars, setup) is new.

- Admins: André (Dremet, owner) and McVizn. In-game admins come from the web
  admin lists (`webadmin.server_admins` -> `/srv/tsura/server_config/fun.json`);
  `apply_web_admins.py` (cron, every 10 min) keeps the running server in sync.
- Website: `/admin/fun` -- upload cars/tracks, send console commands, restart/update.
- No session automation: `-setup plain` (empty), admins start modes in-game.

## Result files are only archived

The format of the fun-mode result files is **not known yet**. Nothing reads
them -- the pipeline does not look at `/home/data/fun`. At event end and
session end the game calls `server/config/Scripts/archive_stats.sh`, which files
`eventstats.json`, `eventstats.details.log` and `sessionstats.json` under

    /home/data/fun/archive/<YYYYmmdd_HHMMSS>/raw/<ts>[_<level>]_{event.json,event_details.log,session.json}

(same naming as the other servers, so a loader can be added later). Event end
moves the event files and *copies* the session file, session end moves what is
left. Log: `server/config/Scripts/archive_stats.log`.

## Install notes

User `fun` (uid 1011, groups `users`, `tsu`), game via
`steamcmd +force_install_dir ~/server +login anonymous +app_update 1815810 validate`,
files from this directory into `/home/fun` (+ `server/config/Scripts`),
`crontab crontab`, sudoers line `tsura ALL=(fun) NOPASSWD: /home/fun/restart_server.sh, /home/fun/update_and_restart.sh`,
and `/home/data/fun/archive` (`data:tsu`, mode 2775). `server/config/game.json`
host settings (name `TSU Fun Modes`, admins, `commands.automaticScripts` and
`generateStatsFiles` true) are set on the machine, not here.
