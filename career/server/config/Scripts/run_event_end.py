import os
# mark that a real event finished, so the next event-init advances quali<->race
# (a restart does NOT fire this hook, so the mode is kept on restart)
open("career_event_done", "w").close()

commands = ["/broadcast <color=#ffc107>[Career]</color> <color=#aaaaaa>Event finished.</color>"]


with open("event_end_generated.src", "w", encoding="utf-8-sig") as file:
    file.write("\n".join(commands) + "\n")
