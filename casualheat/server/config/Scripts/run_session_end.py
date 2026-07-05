
commands = [
    "/broadcast <color=#0d6efd><b>[Casual Heat]</b></color> Session over — see you next time! Results: <b>tsura.org/races</b>",
    "/timerOn = False",
]


with open("session_end_generated.src", "w", encoding="utf-8-sig") as file:
    file.write("\n".join(commands) + "\n")

