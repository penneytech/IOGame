# Lesson 1 — Make Your First Character

**Goal:** get yourself into the arena in five minutes.

## Step 1 — Open the editor

1. Open the game in your browser.
2. Click **Edit character**.
3. You'll see a big text box with some Python code already in it.

## Step 2 — Delete it all, then paste this

> **Important:** copy the **whole block below**, including the first
> line `def build_character():`. If you miss it, Python will say
> *"return outside function"*.

```python
def build_character():
    # Define each power as its own variable, then list them in "powers".
    punch = {
        "name": "Punch",
        "key": "space",
        "cooldownMs": 600,
        "cast": {
            "kind": "melee",
            "color": "blue",
            "range": 40,
            "arcDeg": 70,
            "onHit": [{"effect": "damage", "amount": 12}],
        },
    }

    return {
        "characterName": "Rookie",
        "color": "blue",
        "size": 24,
        "speed": 220,
        "maxHealth": 100,
        "powers": [punch],
    }
```

## Step 3 — Click "Run & Validate"

If everything's good you'll see a green **Total: XX.X — within budget**.

If it's red, read the error message — it usually tells you exactly
which line is wrong.

## Step 4 — Type your name and click "Join match"

You're in! Use:
- **WASD** or **arrow keys** to move
- **Mouse** to aim
- **Space** to punch

## Step 5 — Change one thing

Go back to the editor and try changing:

- `"characterName"` to your name
- `"color"` to `"red"`, `"green"`, `"orange"`, `"purple"`, or any of these:
  red, orange, yellow, green, blue, purple, pink, cyan, lime, gold,
  silver, white, black, gray, brown, navy, teal, magenta, crimson,
  indigo, skyblue, hotpink, olive...
  *(or use a hex code like `"#ff8800"`)*
- `"size"` (smaller is harder to hit — try 18)
- `"speed"` (try 300 for zippy)

Run & Validate, then **Join match** again.

## Done!

You made a character. Next: [Lesson 2 — Add a power →](02-add-a-power.md)
