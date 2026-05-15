def build_character():
    # Medic — light damage, strong self-sustain.
    # Demonstrates: heal cast, healing area, and a small projectile.

    heal = {
        "name": "Mend",
        "key": "e",
        "cooldownMs": 5000,
        "cast": {
            "kind": "heal",
            "color": "lime",
            "amount": 60,
        },
    }

    # A regen pool: stand in it to heal yourself OR teammates.
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
            # Set followOwner: true if you want the pool to move with you.
            # Default (false) drops it where you cast it.
            "followOwner": True,
            # Note: area effects affect everyone except the caster, so this heals
            # OTHER players in it. Pair with a teammate!
            "onTick": [
                {
                    "effect": "heal",
                    "amount": 6,
                }
            ],
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
            "onHit": [
                {
                    "effect": "damage",
                    "amount": 10,
                }
            ],
        },
    }

    return {
        "characterName": "Medic",
        "color": "lime",
        "size": 24,
        "speed": 250,
        "maxHealth": 120,
        "powers": [dart, heal, regen_pool],
    }
