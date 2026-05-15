"""Tests for the new manifest schema (cast kinds + effects)."""

from server.validation import validate_join, validate_manifest


def projectile_power():
    return {
        "name": "Bolt", "key": "space", "cooldownMs": 600,
        "cast": {
            "kind": "projectile", "color": "orange",
            "speed": 500, "radius": 8, "lifetimeMs": 1500,
            "count": 1, "spreadDeg": 0, "pierce": False,
            "onHit": [{"effect": "damage", "amount": 20}],
        },
    }


GOOD = {
    "characterName": "Fire Wizard",
    "color": "orange",
    "size": 28,
    "speed": 220,
    "maxHealth": 100,
    "powers": [projectile_power()],
}


def test_good_manifest():
    ok, result = validate_manifest(GOOD)
    assert ok, result
    m, report = result
    assert m.powers[0].cast.kind == "projectile"
    assert report["ok"] is True
    assert report["total"] <= 100


def test_bad_color_rejected():
    bad = dict(GOOD, color="url(http://evil)")
    ok, err = validate_manifest(bad)
    assert not ok and "color" in err


def test_health_out_of_range():
    ok, err = validate_manifest(dict(GOOD, maxHealth=10_000))
    assert not ok and "maxHealth" in err


def test_no_powers_rejected():
    ok, err = validate_manifest(dict(GOOD, powers=[]))
    assert not ok


def test_too_many_powers_rejected():
    ok, err = validate_manifest(dict(GOOD, powers=[projectile_power()] * 5))
    assert not ok


def test_duplicate_power_keys_rejected():
    p1 = projectile_power()
    p2 = projectile_power(); p2["name"] = "Bolt2"
    ok, err = validate_manifest(dict(GOOD, powers=[p1, p2]))
    assert not ok


def test_unknown_cast_kind_rejected():
    bad_power = projectile_power()
    bad_power["cast"]["kind"] = "nuke"
    ok, err = validate_manifest(dict(GOOD, powers=[bad_power]))
    assert not ok


def test_area_cast_validates():
    area_power = {
        "name": "Cloud", "key": "q", "cooldownMs": 4000,
        "cast": {
            "kind": "area", "color": "green",
            "radius": 80, "durationMs": 2000, "tickIntervalMs": 250,
            "onTick": [
                {"effect": "dot", "dps": 8, "durationMs": 1000},
                {"effect": "slow", "factor": 0.6, "durationMs": 800},
            ],
        },
    }
    ok, m = validate_manifest(dict(GOOD, powers=[area_power]))
    assert ok, m


def test_shield_and_heal_and_dash_validate():
    powers = [
        {"name": "S", "key": "space", "cooldownMs": 6000,
         "cast": {"kind": "shield", "color": "cyan", "amount": 50, "durationMs": 3000}},
        {"name": "H", "key": "e", "cooldownMs": 5000,
         "cast": {"kind": "heal", "color": "lime", "amount": 60}},
        {"name": "D", "key": "f", "cooldownMs": 3000,
         "cast": {"kind": "dash", "color": "white",
                  "distance": 200, "durationMs": 200, "invulnerable": True}},
    ]
    ok, m = validate_manifest(dict(GOOD, powers=powers))
    assert ok, m


def test_melee_validates():
    melee_power = {
        "name": "Hammer", "key": "space", "cooldownMs": 900,
        "cast": {
            "kind": "melee", "color": "orange",
            "range": 80, "arcDeg": 90,
            "onHit": [
                {"effect": "damage", "amount": 22},
                {"effect": "knockback", "strength": 240},
            ],
        },
    }
    ok, m = validate_manifest(dict(GOOD, powers=[melee_power]))
    assert ok, m


def test_effect_out_of_range_rejected():
    bad = projectile_power()
    bad["cast"]["onHit"] = [{"effect": "damage", "amount": 9999}]
    ok, err = validate_manifest(dict(GOOD, powers=[bad]))
    assert not ok


def test_empty_effects_rejected():
    bad = projectile_power()
    bad["cast"]["onHit"] = []
    ok, err = validate_manifest(dict(GOOD, powers=[bad]))
    assert not ok


def test_join_validates_username():
    ok, result = validate_join({"username": "ada", "manifest": GOOD})
    assert ok, result
    j, _report = result
    assert j.username == "ada"


def test_join_rejects_bad_username():
    ok, _ = validate_join({"username": "<script>", "manifest": GOOD})
    assert not ok


def test_hex_color_ok():
    ok, _ = validate_manifest(dict(GOOD, color="#ff8800"))
    assert ok


# --- Sprite payload tests ---------------------------------------------------

_TINY_PNG = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)


def test_sprites_accepted_when_valid():
    m = dict(GOOD)
    m["sprites"] = {"idle": [_TINY_PNG], "walk": [_TINY_PNG, _TINY_PNG]}
    ok, result = validate_manifest(m)
    assert ok, result


def test_sprites_unknown_slot_rejected():
    m = dict(GOOD)
    m["sprites"] = {"dance": [_TINY_PNG]}
    ok, result = validate_manifest(m)
    assert not ok


def test_sprites_too_many_frames_rejected():
    m = dict(GOOD)
    m["sprites"] = {"walk": [_TINY_PNG] * 5}
    ok, result = validate_manifest(m)
    assert not ok


def test_sprites_bad_prefix_rejected():
    m = dict(GOOD)
    m["sprites"] = {"idle": ["http://example.com/evil.png"]}
    ok, result = validate_manifest(m)
    assert not ok


def test_sprites_oversize_rejected():
    big = "data:image/png;base64," + ("A" * (16 * 1024 + 1))
    m = dict(GOOD)
    m["sprites"] = {"idle": [big]}
    ok, result = validate_manifest(m)
    assert not ok
