
commands = [
    "/broadcast <color=#dc3545><b>[TripleHeat]</b></color> Session over — see you next time! ELO ranking: <b>tsura.org/elo-heats</b>",
    "/timerOn = False",
]


with open("session_end_generated.src", "w", encoding="utf-8-sig") as file:
    file.write("\n".join(commands) + "\n")

