
import sys
import yaml
from pathlib import Path
from random import randint

MOVE = sys.argv[1].strip().lower()
STATE_FILE = Path("game-state.yml")
README_FILE = Path("README.md")

# Load state
state = yaml.safe_load(STATE_FILE.read_text())

player = state["player"]
enemy = state["enemy"]
history = state["history"]

log = []

# --- Player move ---
if MOVE == "attack":
    dmg = randint(5, 15)
    enemy["hp"] = max(0, enemy["hp"] - dmg)
    player["last_move"] = "attack"
    log.append(f"You attack the enemy for {dmg} damage.")
elif MOVE == "heal":
    if "potion" in player["inventory"]:
        heal = randint(10, 20)
        player["hp"] = min(player["max_hp"], player["hp"] + heal)
        player["inventory"].remove("potion")
        player["last_move"] = "heal"
        log.append(f"You used a potion and healed {heal} HP.")
    else:
        log.append("No potions left!")
        player["last_move"] = "nothing"
else:
    log.append(f"Unknown move: {MOVE}")
    player["last_move"] = MOVE

# --- Enemy move (simple adaptive AI) ---
recent = [h["player"] for h in history[-3:]]

if player["last_move"] == "heal":
    enemy_move = "charge"
elif recent.count("attack") >= 2:
    enemy_move = "defend"
elif enemy["hp"] < 20:
    enemy_move = "evade"
else:
    enemy_move = "slash"

enemy["last_move"] = enemy_move

if enemy_move == "slash":
    dmg = randint(5, 12)
    player["hp"] = max(0, player["hp"] - dmg)
    log.append(f"{enemy['name']} slashes you for {dmg} damage.")
elif enemy_move == "charge":
    dmg = randint(10, 18)
    player["hp"] = max(0, player["hp"] - dmg)
    log.append(f"{enemy['name']} charges and deals {dmg} damage!")
elif enemy_move == "defend":
    log.append(f"{enemy['name']} takes a defensive stance.")
elif enemy_move == "evade":
    log.append(f"{enemy['name']} tries to flee... but stays to fight.")

# Append turn to history
history.append({"player": player["last_move"], "enemy": enemy_move})
state["turn"] += 1

# Save updated state
STATE_FILE.write_text(yaml.dump(state))

# Update README
README_FILE.write_text(f"""# 🧙 GitHub RPG

**Turn:** {state["turn"]}

**Player HP:** {player["hp"]}/{player["max_hp"]}  
**Enemy HP:** {enemy["hp"]}/{enemy["max_hp"]}  
**Inventory:** {", ".join(player["inventory"]) or "empty"}  

---

### 🔁 Last Turn

{chr(10).join(f"- {l}" for l in log)}

---

Submit your next move as a GitHub Issue with title:

> /attack  
> /heal
""")
