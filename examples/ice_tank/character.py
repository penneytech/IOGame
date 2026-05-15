def build_character():
    # Ice Tank — front-line bruiser.
    # Demonstrates: SHIELD + MELEE + slowing PROJECTILE.

    bulwark = {
        "name": "Bulwark",
        "key": "q",
        "cooldownMs": 8000,
        "cast": {
            "kind": "shield",
            "color": "cyan",
            "amount": 80,
            "durationMs": 4000,
        },
    }

    cleave = {
        "name": "Cleave",
        "key": "space",
        "cooldownMs": 800,
        "cast": {
            "kind": "melee",
            "color": "white",
            "range": 70,
            "arcDeg": 110,
            "onHit": [
                {"effect": "damage", "amount": 18},
                {"effect": "knockback", "strength": 220},
            ],
        },
    }

    frost_bolt = {
        "name": "Frost Bolt",
        "key": "e",
        "cooldownMs": 1500,
        "cast": {
            "kind": "projectile",
            "color": "#9ad3ff",
            "speed": 420,
            "radius": 6,
            "lifetimeMs": 1500,
            "count": 1,
            "spreadDeg": 0,
            "onHit": [
                {"effect": "damage", "amount": 8},
                {"effect": "slow", "factor": 0.4, "durationMs": 1800},
            ],
        },
    }

    return {
        "characterName": "Ice Tank",
        "color": "#5db8ff",
        "size": 32,
        "speed": 170,
        "maxHealth": 220,
        "powers": [cleave, bulwark, frost_bolt],
    }
