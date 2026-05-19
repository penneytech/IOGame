# Lesson 4 — Build Your Own From Scratch

**Goal:** make a character that's YOURS, not a copy.

## Step 1 — Pick a vibe

Choose one. Don't overthink it.

- **Tank** — slow, hard to kill, hits hard up close.
- **Sniper** — long-range fireballs, dies fast.
- **Ninja** — fast, dashes a lot, sneak attacks.
- **Wizard** — fireballs + a fire-cloud area.
- **Medic** — heals self/teammates, weak attacks.
- **Brawler** — big punches and a stun.
- **Trap setter** — drop areas, run away.

## Step 2 — Fill in this template

Copy this and replace the **CAPS** with your choices:

```python
def build_character():
    # Define each power as its own variable first.
    punch = {
        "name": "Punch",
        "key": "space",
        "cooldownMs": 600,
        "cast": {
            "kind": "melee", "color": "blue",
            "range": 40, "arcDeg": 70,
            "onHit": [{"effect": "damage", "amount": 12}],
        },
    }
    # power2 = { ... }   # copy one from Lesson 2
    # power3 = { ... }   # optional

    return {
        "characterName": "YOUR NAME HERE",
        "color": "YOUR COLOR HERE",
        "size": 24,            # smaller = harder to hit, costs more
        "speed": 220,          # 80 to 400
        "maxHealth": 100,      # 40 to 300
        "powers": [punch],     # add your other variables here: [punch, power2]
    }
```

## Step 3 — Add 2 or 3 powers

Go back to [Lesson 2](02-add-a-power.md) and pick 2 or 3 powers that
fit your vibe.

**Match the vibe!**

- Tank? → big melee, shield, maybe heal. No fireballs.
- Sniper? → fireball, dash, maybe a second fireball on a different key.
- Ninja? → fast melee, dash, no shield.
- Wizard? → fireball + poison cloud.
- Medic? → heal + heal-cloud + tiny weak fireball.

## Step 4 — Tune

1. **Run & Validate.**
2. If over 100, do [Lesson 3](03-budget.md).
3. **Join match.**
4. Play 2 or 3 fights. What feels good? What feels bad?
5. Change ONE number. Test again.
6. Repeat.

## Step 5 — Ask yourself

After playing for a while:

- **How do I kill people?** (If you can't answer, your damage is too low.)
- **What kills me?** (If "everything," you need more HP or shield or speed.)
- **Is there a moment when my character feels cool?** (If yes, protect that moment from future changes!)

## Bonus dares

When you're bored of your character, try one of these:

- **The 50-point character.** Spend only half your budget. Still fun?
- **Space only.** Just ONE power. Make it interesting.
- **No damage allowed.** Win with stun, slow, knockback (push enemies around).
- **Identity swap.** Switch files with a friend. Can you play their build?

## You're done!

Open the **Manual** link in the game's top bar for the full list of
fields and legal values.

Have fun!
