commands = ["/broadcast <color=#dc3545><b>[TripleHeat]</b></color> <color=#aaaaaa>Event finished.</color>"]


with open("event_end_generated.src", "w", encoding="utf-8-sig") as file:
    file.write("\n".join(commands) + "\n")
