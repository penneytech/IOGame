def build_character():
    # Medic — sustain support.
    # Demonstrates: HEAL + AREA heal (followOwner) + light PROJECTILE.

    mend = {
        "name": "Mend",
        "key": "e",
        "cooldownMs": 5000,
        "cast": {
            "kind": "heal",
            "color": "lime",
            "amount": 60,
        },
    }

    regen_pool = {
        "name": "Regen Pool",
        "key": "q",
        "cooldownMs": 7000,
        "cast": {
            "kind": "area",
            "color": "green",
            "radius": 80,
            "durationMs": 4000,
            "tickIntervalMs": 400,
            "followOwner": True,
            "onTick": [{"effect": "heal", "amount": 6}],
        },
    }

    dart = {
        "name": "Healing Dart",
        "key": "space",
        "cooldownMs": 600,
        "cast": {
            "kind": "projectile",
            "color": "white",
            "speed": 520,
            "radius": 4,
            "lifetimeMs": 1200,
            "count": 1,
            "spreadDeg": 0,
            "onHit": [{"effect": "damage", "amount": 10}],
        },
    }

    return {
        "characterName": "Medic",
        "color": "lime",
        "size": 24,
        "speed": 250,
        "maxHealth": 120,
        "powers": [dart, mend, regen_pool],
    }
