# Lesson 3 — Stay Under 100 Points

**Goal:** understand why your fireball got expensive, and how to fix it.

## The rule

> Every character has **100 points** to spend. If you go over, the game
> won't let you in.

When you click **Run & Validate**, the right side shows your **cost report**.
Green = you're good. Red = too expensive, fix it.

## Where do points go?

Two places:

1. **Your stats** (size, speed, health).
2. **Your powers.**

### Stats

| Stat        | Free baseline | Costs more if...      |
| ----------- | ------------- | --------------------- |
| `maxHealth` | 100 HP        | you raise it          |
| `speed`     | 200           | you raise it          |
| `size`      | (no cost at 60) | you shrink it       |

Tiny + fast + tons of HP = expensive. Pick one or two, not all three.

### Powers

The strong an effect, the higher the cost. The bigger an area, the higher
the cost. The **shorter the cooldown**, the higher the cost — a lot
higher.

## The cooldown trick

The biggest cost lever is **cooldown**.

- `cooldownMs: 200` → spam mode → **6× cost!**
- `cooldownMs: 1000` → normal → about 1.5×
- `cooldownMs: 5000` → slow → 0.6×

If your power is too expensive, **make the cooldown longer** before
weakening anything else.

## Example: my fireball is 60 points!

```python
{
    "name": "Mega Bolt", "key": "space", "cooldownMs": 250,
    "cast": {
        "kind": "projectile", "color": "red",
        "speed": 700, "radius": 8, "lifetimeMs": 1500,
        "count": 3, "spreadDeg": 30, "pierce": True,
        "onHit": [{"effect": "damage", "amount": 30}],
    },
},
```

This is:
- 3 fireballs (`"count": 3`) ← ×3 cost
- They pierce ← +6 cost
- Spam cooldown (250 ms) ← ×~5 cost
- Big damage (30) ← high base
- Top speed (700) ← extra

Pick ONE of these to keep. Cut the others.

**Fix it 4 ways:**

```python
# Fix 1: Less spam (longer cooldown)
"cooldownMs": 1500,   # cost drops by about 3×

# Fix 2: Fewer shots
"count": 1, "spreadDeg": 0,

# Fix 3: Less damage
"amount": 18,

# Fix 4: No pierce
"pierce": False,
```

Combine 2 or 3 of these and you're back under 100.

## The 3 questions

When a power is too expensive, ask:

1. **Can I make the cooldown longer?** (Usually the cheapest fix.)
2. **Can I drop a side-effect?** (Like a stun on top of damage.)
3. **Can I make it smaller?** (Less damage, fewer projectiles, smaller area.)

## Try it!

Take the Mega Bolt above and bring it under 30 points using only the
4 fixes shown. Run & Validate after each change to see the number drop.

Next: [Lesson 4 — Build your own from scratch →](04-your-own.md)
