
commands = [
    "/broadcast Session has ended for today, see you next time! Visit https://tsura.org/races for race results!",
    "/timerOn = False",
]


with open("session_end_generated.src", "w", encoding="utf-8-sig") as file:
    file.write("\n".join(commands) + "\n")

