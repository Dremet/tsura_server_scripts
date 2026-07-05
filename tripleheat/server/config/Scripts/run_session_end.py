
commands = [
    "/broadcast <color=#dc3545>[TripleHeat]</color> Session over — see you next time! ELO ranking: tsura.org/elo-heats",
    "/timerOn = False",
]


with open("session_end_generated.src", "w", encoding="utf-8-sig") as file:
    file.write("\n".join(commands) + "\n")

