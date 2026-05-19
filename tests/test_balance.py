"""Tests for the build-budget balance system."""

from server.balance import (
    BUDGET, build_report, cooldown_factor, cost_cast, cost_effect, cost_power,
    cost_stats,
)
from server.models import CharacterManifest
from server.validation import validate_manifest


def base_manifest(**overrides):
    m = {
        "characterName": "Test", "color": "red",
        "size": 32, "speed": 180, "maxHealth": 80,
        "powers": [{
            "name": "Bolt", "key": "space", "cooldownMs": 1500,
            "cast": {
                "kind": "projectile", "color": "red",
                "speed": 400, "radius": 6, "lifetimeMs": 1000,
                "count": 1, "spreadDeg": 0, "pierce": False,
                "onHit": [{"effect": "damage", "amount": 20}],
            },
        }],
    }
    m.update(overrides)
    return CharacterManifest.model_validate(m)


def test_baseline_character_is_almost_free():
    m = base_manifest()
    r = build_report(m)
    assert r["statsTotal"] == 0
    # 1 power, 1 effect, ref cooldown -> a few points only.
    assert 0 < r["powersTotal"] < 25
    assert r["ok"] is True


def test_more_hp_costs_more_points():
    cheap = build_report(base_manifest(maxHealth=80))["statsTotal"]
    pricey = build_report(base_manifest(maxHealth=200))["statsTotal"]
    assert pricey > cheap + 25  # ~30 pts for +120 hp


def test_smaller_size_costs_points():
    big = build_report(base_manifest(size=40))["statsTotal"]
    small = build_report(base_manifest(size=16))["statsTotal"]
    assert small > big + 8


def test_short_cooldown_makes_a_power_more_expensive():
    long = cost_power(base_manifest(powers=[{
        "name": "X", "key": "space", "cooldownMs": 3000,
        "cast": {
            "kind": "projectile", "color": "red",
            "speed": 400, "radius": 6, "lifetimeMs": 1000,
            "count": 1, "spreadDeg": 0, "pierce": False,
            "onHit": [{"effect": "damage", "amount": 20}],
        },
    }]).powers[0])
    short = cost_power(base_manifest(powers=[{
        "name": "X", "key": "space", "cooldownMs": 300,
        "cast": {
            "kind": "projectile", "color": "red",
            "speed": 400, "radius": 6, "lifetimeMs": 1000,
            "count": 1, "spreadDeg": 0, "pierce": False,
            "onHit": [{"effect": "damage", "amount": 20}],
        },
    }]).powers[0])
    assert short > long * 3.5


def test_cooldown_factor_is_clamped():
    assert cooldown_factor(50) == 6.0    # ridiculously short
    assert cooldown_factor(50_000) == 0.4  # ridiculously long


def test_overpowered_character_is_rejected():
    """Max stats + 4 spammy 60-damage powers should fail validation."""
    overpowered = {
        "characterName": "GodMode", "color": "red",
        "size": 12, "speed": 400, "maxHealth": 300,
        "powers": [
            {"name": f"P{i}", "key": k, "cooldownMs": 200,
             "cast": {
                 "kind": "projectile", "color": "red",
                 "speed": 700, "radius": 30, "lifetimeMs": 5000,
                 "count": 6, "spreadDeg": 60, "pierce": True,
                 "onHit": [{"effect": "damage", "amount": 60}],
             }}
            for i, k in enumerate(["space", "e", "q", "f"])
        ],
    }
    ok, err = validate_manifest(overpowered)
    assert not ok
    assert "budget" in err.lower()


def test_warning_on_spammy_dps_power():
    m = base_manifest(powers=[{
        "name": "Spam", "key": "space", "cooldownMs": 200,
        "cast": {
            "kind": "projectile", "color": "red",
            "speed": 400, "radius": 6, "lifetimeMs": 1000,
            "count": 1, "spreadDeg": 0, "pierce": False,
            "onHit": [{"effect": "damage", "amount": 30}],
        },
    }])
    r = build_report(m)
    assert any("DPS" in w or "spammy" in w for w in r["warnings"])


def test_warning_on_perma_stun():
    m = base_manifest(powers=[{
        "name": "Lock", "key": "space", "cooldownMs": 600,
        "cast": {
            "kind": "melee", "color": "red", "range": 60, "arcDeg": 90,
            "onHit": [
                {"effect": "damage", "amount": 5},
                {"effect": "stun", "durationMs": 1000},
            ],
        },
    }])
    r = build_report(m)
    assert any("perma-stun" in w for w in r["warnings"])


def test_metrics_present():
    m = base_manifest()
    r = build_report(m)
    for k in ("burst", "dps", "effectiveHealth", "mobility", "healing", "crowdControl"):
        assert k in r["metrics"]
