
import os
# release the session lock so run_prepare.sh may regenerate .veh again
try:
    os.remove("session_active")
except FileNotFoundError:
    pass

commands = [
    "/broadcast <color=#ffc107>[Career]</color> Session over — points & credits update within a minute: tsura.org/career",
    "/timerOn = False",
]


with open("session_end_generated.src", "w", encoding="utf-8-sig") as file:
    file.write("\n".join(commands) + "\n")

