# Lesson 2 — Add a Power

**Goal:** give your character a second ability.

You already have **Punch** on the space bar. Now let's add more.

## The four keys

Your character can have up to **4 powers**, one for each key:

- `space`
- `e`
- `q`
- `f`
- `mouse1` (left click)
- `mouse2` (right click)

Pick whichever you like — each power needs its own key, no duplicates.

## How to add one

You already gave each power its own variable (like `punch`). Add a
**new variable** for the next power, then drop it into your `"powers"`
list:

```python
def build_character():
    punch = { ... }              # already there

    heal = {                     # ← new variable
        "name": "Heal",
        "key": "e",
        "cooldownMs": 8000,
        "cast": {"kind": "heal", "color": "lime", "amount": 35},
    }

    return {
        ...
        "powers": [punch, heal], # ← add the variable here
    }
```

Each power must use a **different key** (no two on `space`, etc.).

## Pick from the menu

Pick **one** of these. Copy the variable, then add it to your
`"powers"` list. (More power ideas are documented in the **Manual**
link in the game's top bar once you're ready for them.)

### Attack — Fireball (long-range hit)

```python
fireball = {
    "name": "Fireball",
    "key": "q",
    "cooldownMs": 1000,
    "cast": {
        "kind": "projectile", "color": "orange",
        "speed": 420, "radius": 6, "lifetimeMs": 1500,
        "count": 1, "spreadDeg": 0, "pierce": False,
        "onHit": [{"effect": "damage", "amount": 18}],
    },
}
```

Press **Q** to shoot a fireball.

---

### Defense — Shield (block damage)

```python
shield = {
    "name": "Shield",
    "key": "e",
    "cooldownMs": 7000,
    "cast": {"kind": "shield", "color": "cyan", "amount": 40, "durationMs": 3000},
}
```

Press **E** for 40 extra HP for 3 seconds.

## Try it!

1. Pick a power above.
2. Paste the variable **above** the `return` line in `build_character()`.
3. Add the variable name to your `"powers"` list — e.g. `[punch, heal]`.
4. **Run & Validate**.
5. **Join match** and try the new key.

## When it doesn't work

- **"Validation failed: ..."** → read the error. Usually a missing comma, a
  missing `True`/`False`, or two powers on the same key.
- **Over budget?** That's next: [Lesson 3 — Stay under 100 points →](03-budget.md)
