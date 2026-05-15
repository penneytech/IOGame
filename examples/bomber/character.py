def build_character():
    # Bomber — area-of-effect specialist.
    # Demonstrates: heavy PROJECTILE + big AREA (poison cloud) + escape DASH.

    grenade = {
        "name": "Grenade",
        "key": "space",
        "cooldownMs": 900,
        "cast": {
            "kind": "projectile",
            "color": "#2a6b1a",
            "speed": 380,
            "radius": 12,
            "lifetimeMs": 900,
            "count": 1,
            "spreadDeg": 0,
            "onHit": [
                {"effect": "damage", "amount": 22},
                {"effect": "knockback", "strength": 280},
            ],
        },
    }

    poison_cloud = {
        "name": "Poison Cloud",
        "key": "q",
        "cooldownMs": 5500,
        "cast": {
            "kind": "area",
            "color": "purple",
            "radius": 110,
            "durationMs": 5000,
            "tickIntervalMs": 350,
            "followOwner": False,
            "onTick": [
                {"effect": "damage", "amount": 4},
                {"effect": "slow", "factor": 0.6, "durationMs": 600},
            ],
        },
    }

    roll_away = {
        "name": "Roll Away",
        "key": "shift",
        "cooldownMs": 3000,
        "cast": {
            "kind": "dash",
            "color": "white",
            "distance": 200,
            "durationMs": 220,
            "invulnerable": False,
        },
    }

    return {
        "characterName": "Bomber",
        "color": "#7ad36b",
        "size": 26,
        "speed": 210,
        "maxHealth": 110,
        "powers": [grenade, poison_cloud, roll_away],
    }
