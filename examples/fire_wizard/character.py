def build_character():
    # Fire Wizard — ranged caster.
    # Demonstrates: PROJECTILE (3-shot fan) + AREA (burning ground / DoT).

    fireball = {
        "name": "Fireball",
        "key": "space",
        "cooldownMs": 700,
        "cast": {
            "kind": "projectile",
            "color": "orange",
            "speed": 600,
            "radius": 8,
            "lifetimeMs": 1200,
            "count": 3,
            "spreadDeg": 22,
            "onHit": [
                {"effect": "damage", "amount": 14},
                {"effect": "dot", "dps": 12, "durationMs": 1500},
            ],
        },
    }

    firewall = {
        "name": "Firewall",
        "key": "q",
        "cooldownMs": 6000,
        "cast": {
            "kind": "area",
            "color": "red",
            "radius": 90,
            "durationMs": 4000,
            "tickIntervalMs": 300,
            "followOwner": False,
            "onTick": [{"effect": "damage", "amount": 6}],
        },
    }

    blink = {
        "name": "Phase Step",
        "key": "e",
        "cooldownMs": 4000,
        "cast": {
            "kind": "dash",
            "color": "magenta",
            "distance": 180,
            "durationMs": 200,
            "invulnerable": True,
        },
    }

    return {
        "characterName": "Fire Wizard",
        "color": "#ff6a3d",
        "size": 22,
        "speed": 230,
        "maxHealth": 90,
        "powers": [fireball, firewall, blink],
    }
