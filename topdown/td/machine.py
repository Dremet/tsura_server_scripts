"""The heat state machine.

    IDLE --first human joins--> COUNTDOWN --90s--> HEAT --8 events--> COOLDOWN
      ^                              |               |                   |
      +---- lobby empties -----------+---------------+----60s, players---+

The machine owns no socket and reads no clock: it is fed events and the current
time, and returns the console commands it wants sent. That keeps a full heat --
including votes, late joiners and an emptying lobby -- replayable in tests
without a game server.

Rules implemented here come from McVizn (2026-07-31):
  B1  the 90s countdown is fixed; further joins do not extend it
  B2  a player joining mid-heat races from the next event onwards
  B3  no hard time limit per race
  B4  race restart needs 2/3 of those present; resetting the whole heat needs
      every driver who started it. Admins can force either.
  B5  when the last human leaves, the bots finish the current event and the heat
      then ends, flagged as having finished without players
  B6  if players stay, the next heat starts after 60s
  C3  a changed bot count only takes effect from the next event
"""

import math

IDLE = "idle"
COUNTDOWN = "countdown"
HEAT = "heat"
COOLDOWN = "cooldown"

BADGE = "<color=#fd7e14>[TopDown]</color>"
GREY = "<color=#aaaaaa>"

DEFAULTS = {
    "countdown_seconds": 90,
    "cooldown_seconds": 60,
    "vote_seconds": 60,
    "vote_fraction": 2.0 / 3.0,
    "bot_fill": 14,
    "max_drivers": 20,
    "bots_off_from_humans": 6,
    "tracks_per_heat": 4,
}
# Announce the countdown at these remaining-second marks.
COUNTDOWN_MARKS = (60, 30, 10)
# How long to wait for the requested session before nudging the server again.
SESSION_RETRY_SECONDS = 30
MAX_SESSION_RETRIES = 3


def _cfg(config, key):
    value = config.get(key, DEFAULTS.get(key))
    return DEFAULTS.get(key) if value is None else value


class Vote:
    """A running poll. Re-issuing the same command counts as a yes."""

    def __init__(self, topic, eligible, needed, deadline, arg=None):
        self.topic = topic
        self.eligible = set(eligible)
        self.needed = needed
        self.deadline = deadline
        self.arg = arg
        self.yes = set()

    def add(self, steam_id):
        if steam_id in self.eligible:
            self.yes.add(steam_id)
        return len(self.yes)

    def passed(self):
        return len(self.yes) >= self.needed


class HeatMachine:
    """Drives one topdown server through an endless series of heats."""

    def __init__(self, config, rng, plan_builder, clock=None, log=None):
        self.config = config or {}
        self.rng = rng
        self._build_plan = plan_builder      # () -> heat plan dict
        self.log = log or (lambda msg: None)

        self.state = IDLE
        self.humans = {}                     # steam_id -> name, humans only
        self.deadline = None                 # end of countdown / cooldown
        self.announced = set()               # countdown marks already broadcast

        self.heat_id = None
        self.plan = None
        self.events_done = 0
        self.events_total = 0
        self.starters = set()                # who was present when the heat began
        self.abandoned = False               # last human left mid-heat
        # Set while waiting for the server to cycle into the new session we
        # asked for, so our own session end is not mistaken for the heat's.
        self.awaiting_session = False
        self.vote = None
        self.bot_fill = int(_cfg(self.config, "bot_fill"))
        self.pending_bot_fill = None         # applied at the next event (C3)

    # --- helpers ----------------------------------------------------------

    @property
    def human_count(self):
        return len(self.humans)

    def votes_needed(self, eligible_count):
        """2/3 of those present, rounded up, and never fewer than one."""
        frac = float(_cfg(self.config, "vote_fraction"))
        return max(1, math.ceil(eligible_count * frac))

    def is_admin(self, steam_id):
        admins = {str(a[0]) for a in self.config.get("ingame_admins", []) if a}
        return str(steam_id) in admins

    def effective_bot_fill(self):
        """Target grid size for the next event, or 0 when bots are off.

        Bots stand down once enough humans are racing, and the grid never
        exceeds the configured maximum.
        """
        cutoff = int(_cfg(self.config, "bots_off_from_humans"))
        if self.human_count >= cutoff:
            return 0
        return min(int(self.bot_fill), int(_cfg(self.config, "max_drivers")))

    # --- inputs -----------------------------------------------------------

    def set_players(self, humans, now):
        """Replace the roster with the authoritative "/who /id" reply.

        Names from join lines are never trusted for identity, so this is the only
        way players enter the machine.
        """
        before = set(self.humans)
        self.humans = dict(humans)
        after = set(self.humans)
        cmds = []

        if not before and after and self.state == IDLE:
            cmds += self._start_countdown(now)
        elif not after and before:
            cmds += self._lobby_emptied(now)

        # A vote loses its quorum when the electorate shrinks.
        if self.vote and after != before:
            self.vote.eligible &= after
            self.vote.yes &= after
            if self.vote.eligible:
                self.vote.needed = self.votes_needed(len(self.vote.eligible))
                if self.vote.passed():
                    cmds += self._apply_vote(now)
            else:
                self.vote = None
        return cmds

    def tick(self, now):
        """Advance timers. Call regularly (about once a second)."""
        cmds = []
        if self.state == COUNTDOWN:
            remaining = int(math.ceil(self.deadline - now))
            total = float(_cfg(self.config, "countdown_seconds"))
            for mark in COUNTDOWN_MARKS:
                # Skip marks longer than the countdown itself, or a 20s countdown
                # would announce "60 seconds" and "30 seconds" in the same breath.
                if mark >= total:
                    self.announced.add(mark)
                    continue
                if remaining <= mark and mark not in self.announced:
                    self.announced.add(mark)
                    cmds.append(f"/broadcast {BADGE} Heat starts in {mark} seconds!")
            if now >= self.deadline:
                cmds += self._start_heat(now)
        elif self.state == COOLDOWN and now >= self.deadline:
            if self.human_count:
                cmds += self._start_heat(now)
            else:
                self.state = IDLE
                self.deadline = None
        # If the session we asked for never materialised, nudge the server again
        # rather than sitting in a half-started heat forever.
        if self.state == HEAT and self.awaiting_session and \
                now - self.session_requested_at > SESSION_RETRY_SECONDS:
            self.session_requested_at = now
            self.session_retries += 1
            if self.session_retries <= MAX_SESSION_RETRIES:
                self.log(f"session did not start; retrying (#{self.session_retries})")
                cmds.append("/continue")
            else:
                self.log("server never started the session -- giving up on this heat")
                self.state = IDLE
                self.awaiting_session = False
                cmds.append(f"/broadcast {BADGE} Could not start the heat -- "
                            f"{GREY}please tell an admin.</color>")

        if self.vote and now >= self.vote.deadline:
            cmds.append(
                f"/broadcast {BADGE} Vote on {self.vote.topic} failed "
                f"({len(self.vote.yes)}/{self.vote.needed} needed)."
            )
            self.vote = None
        return cmds

    def on_session_started(self, now):
        """The server entered the session that carries our heat."""
        if self.state == HEAT and self.awaiting_session:
            self.awaiting_session = False
            self.events_done = 0
            self.log(f"heat {self.heat_id} session is live")
        return []

    def on_session_ended(self, now):
        """A session ended. Once the heat's own session ends, the heat is over.

        The server plays the queued track list and then closes the session, so
        that is the authoritative end -- more reliable than counting events,
        which an aborted event or a restart can throw off.
        """
        if self.state != HEAT:
            return []
        if self.awaiting_session:
            # Our own /abortsession echoing back; the real session follows.
            return []
        return self._end_heat(now, abandoned=self.abandoned)

    def on_event_ended(self, now):
        """One game event (a qualifying or a race) finished."""
        if self.state != HEAT or self.awaiting_session:
            return []
        self.events_done += 1
        cmds = []
        if self.abandoned:
            # B5: the bots were allowed to finish; now close the heat.
            cmds += self._end_heat(now, abandoned=True)
        elif self.events_done >= self.events_total:
            cmds += self._end_heat(now, abandoned=False)
        else:
            fill = self.effective_bot_fill()
            if self.pending_bot_fill is not None:
                self.bot_fill = self.pending_bot_fill
                self.pending_bot_fill = None
                fill = self.effective_bot_fill()
                cmds.append(f"/broadcast {BADGE} Grid size is now {self.bot_fill}.")
            cmds.append(f"/set ai.aiFill {fill}")
        return cmds

    def on_chat(self, steam_id, name, text, now):
        """Handle a chat command. `steam_id` may be None if the name is unknown."""
        from .protocol import parse_command

        parsed = parse_command(text)
        if not parsed:
            return []
        cmd, args = parsed
        if cmd in ("bot", "bots"):
            return self._cmd_bots(steam_id, name, args, now)
        if cmd == "restart":
            return self._cmd_restart(steam_id, name, args, now)
        if cmd in ("heat", "tdheat", "status"):
            return self._cmd_status()
        return []

    # --- commands ---------------------------------------------------------

    def _cmd_status(self):
        if self.state == HEAT and self.plan:
            done = self.events_done
            rnd = min(done // 2 + 1, len(self.plan["rounds"]))
            phase = "race" if done % 2 else "qualifying"
            track = self.plan["rounds"][rnd - 1]["track"]
            return [f"/broadcast {BADGE} Heat #{self.heat_id}: round {rnd}/"
                    f"{len(self.plan['rounds'])} -- {phase} at {track}."]
        if self.state == COUNTDOWN:
            return [f"/broadcast {BADGE} Heat starting shortly -- hang tight!"]
        return [f"/broadcast {BADGE} No heat running. Join up and one starts automatically."]

    def _cmd_bots(self, steam_id, name, args, now):
        if not args or not args[0].lstrip("-").isdigit():
            return [f"/broadcast {BADGE} Usage: /bot <total drivers on the grid>"]
        want = int(args[0])
        limit = int(_cfg(self.config, "max_drivers"))
        if want < 0 or want > limit:
            return [f"/broadcast {BADGE} Grid size must be between 0 and {limit}."]

        if self.is_admin(steam_id):
            self.pending_bot_fill = want
            return [f"/broadcast {BADGE} {name} set the grid to {want} "
                    f"{GREY}(from the next race).</color>"]
        return self._open_vote("grid size", want, steam_id, name, now)

    def _cmd_restart(self, steam_id, name, args, now):
        what = (args[0].lower() if args else "race")
        if what in ("tdheat", "heat"):
            if self.state != HEAT:
                return [f"/broadcast {BADGE} No heat to restart."]
            if self.is_admin(steam_id):
                return self._restart_heat(now)
            # B4: resetting a whole heat needs everyone who started it.
            eligible = self.starters & set(self.humans)
            return self._open_vote("restarting the heat", None, steam_id, name, now,
                                   eligible=eligible, needed=len(eligible))
        if self.is_admin(steam_id):
            return [f"/broadcast {BADGE} {name} restarted the race.", "/restartevent"]
        return self._open_vote("restarting the race", None, steam_id, name, now)

    def _open_vote(self, topic, arg, steam_id, name, now, eligible=None, needed=None):
        if steam_id is None:
            return []
        if self.vote and self.vote.topic == topic and self.vote.arg == arg:
            count = self.vote.add(steam_id)
            if self.vote.passed():
                return self._apply_vote(now)
            return [f"/broadcast {BADGE} {name} agrees on {topic} "
                    f"({count}/{self.vote.needed})."]
        if self.vote:
            return [f"/broadcast {BADGE} Another vote is already running."]

        eligible = set(self.humans) if eligible is None else set(eligible)
        if not eligible:
            return []
        needed = self.votes_needed(len(eligible)) if needed is None else max(1, needed)
        window = float(_cfg(self.config, "vote_seconds"))
        self.vote = Vote(topic, eligible, needed, now + window, arg)
        self.vote.add(steam_id)
        if self.vote.passed():
            return self._apply_vote(now)
        label = "/bot" if topic == "grid size" else "/restart"
        return [f"/broadcast {BADGE} {name} wants {topic}"
                f"{f' = {arg}' if arg is not None else ''}. "
                f"Type {label} to agree ({len(self.vote.yes)}/{needed}, "
                f"{int(window)}s)."]

    def _apply_vote(self, now):
        vote, self.vote = self.vote, None
        if vote.topic == "grid size":
            self.pending_bot_fill = vote.arg
            return [f"/broadcast {BADGE} Vote passed -- grid size {vote.arg} "
                    f"{GREY}(from the next race).</color>"]
        if vote.topic == "restarting the race":
            return [f"/broadcast {BADGE} Vote passed -- restarting the race.",
                    "/restartevent"]
        if vote.topic == "restarting the heat":
            return self._restart_heat(now)
        return []

    # --- transitions ------------------------------------------------------

    def _start_countdown(self, now):
        self.state = COUNTDOWN
        self.announced = set()
        seconds = float(_cfg(self.config, "countdown_seconds"))
        self.deadline = now + seconds
        self.log(f"countdown started ({int(seconds)}s)")
        return [f"/broadcast {BADGE} Welcome! A new heat starts in "
                f"{int(seconds)} seconds."]

    def _lobby_emptied(self, now):
        """The last human left."""
        if self.state == HEAT:
            # B5: let the bots finish the current event, then wrap up.
            self.abandoned = True
            self.log("last human left -- heat will end after the current event")
            return []
        self.state = IDLE
        self.deadline = None
        self.vote = None
        return []

    def _start_heat(self, now):
        self.plan = self._build_plan()
        rounds = self.plan.get("rounds", [])
        if not rounds:
            self.log("no tracks configured -- cannot start a heat")
            self.state = IDLE
            return [f"/broadcast {BADGE} No tracks configured -- please tell an admin."]

        self.heat_id = self.plan.get("heat_id")
        self.state = HEAT
        self.events_done = 0
        self.events_total = len(rounds) * 2      # quali + race per track
        self.starters = set(self.humans)
        self.abandoned = False
        self.vote = None
        self.deadline = None
        self.awaiting_session = True
        self.session_requested_at = now
        self.session_retries = 0

        # The plan is already on disk (the builder wrote it). All that is left is
        # to ask the server for a new session: tracks, cars and AI can only be
        # set during session init, so run_session_init.py applies them there.
        # "/abortsession" ends a running session, "/continue" starts the next one
        # -- an idle server needs the second, a busy one needs both.
        names = ", ".join(r["track"] for r in rounds)
        self.log(f"heat {self.heat_id} requested: {names}")
        return [
            f"/broadcast {BADGE} Heat #{self.heat_id} coming up -- "
            f"{GREY}{names}</color>",
            "/abortsession Yes",
            "/continue",
        ]

    def _end_heat(self, now, abandoned):
        self.log(f"heat {self.heat_id} ended (abandoned={abandoned})")
        self.state = COOLDOWN
        self.deadline = now + float(_cfg(self.config, "cooldown_seconds"))
        self.announced = set()
        cmds = []
        if abandoned:
            cmds.append(f"/broadcast {BADGE} Heat #{self.heat_id} ended early -- "
                        f"{GREY}no players left.</color>")
        else:
            cmds.append(f"/broadcast {BADGE} Heat #{self.heat_id} complete! "
                        f"Results appear on tsura.org shortly.")
        if not self.human_count:
            self.state = IDLE
            self.deadline = None
        return cmds

    def _restart_heat(self, now):
        """Abandon the running heat and immediately compose a fresh one.

        The old heat keeps its ID and stays visible as restarted; the new one is
        a new heat entirely (F5).
        """
        self.log(f"heat {self.heat_id} restarted by vote/admin")
        old = self.heat_id
        cmds = [f"/broadcast {BADGE} Heat #{old} was restarted."]
        cmds += self._start_heat(now)
        return cmds
