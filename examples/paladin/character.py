def build_character():
    # Paladin — durable bruiser/support hybrid.
    # Demonstrates: SHIELD + HEAL + MELEE smite.

    bastion = {
        "name": "Bastion",
        "key": "q",
        "cooldownMs": 9000,
        "cast": {
            "kind": "shield",
            "color": "gold",
            "amount": 60,
            "durationMs": 5000,
        },
    }

    lay_on_hands = {
        "name": "Lay On Hands",
        "key": "e",
        "cooldownMs": 7000,
        "cast": {
            "kind": "heal",
            "color": "white",
            "amount": 50,
        },
    }

    smite = {
        "name": "Smite",
        "key": "space",
        "cooldownMs": 700,
        "cast": {
            "kind": "melee",
            "color": "yellow",
            "range": 60,
            "arcDeg": 90,
            "onHit": [
                {"effect": "damage", "amount": 16},
                {"effect": "knockback", "strength": 150},
            ],
        },
    }

    return {
        "characterName": "Paladin",
        "color": "#ffcb47",
        "size": 28,
        "speed": 200,
        "maxHealth": 180,
        "powers": [smite, bastion, lay_on_hands],
    }
