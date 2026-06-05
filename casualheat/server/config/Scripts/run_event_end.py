commands = ["/broadcast Event End"]


with open("event_end_generated.src", "w", encoding="utf-8-sig") as file:
    file.write("\n".join(commands) + "\n")
