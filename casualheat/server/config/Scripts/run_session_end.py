
commands = [
    "/broadcast <color=#0d6efd>[Casual Heat]</color> Session over — see you next time! Results: tsura.org/races",
    "/timerOn = False",
]


with open("session_end_generated.src", "w", encoding="utf-8-sig") as file:
    file.write("\n".join(commands) + "\n")

