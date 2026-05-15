"""Tests for game state physics, combat, status effects, and respawn."""

import time

from server.game_state import GameState, RESPAWN_DELAY_S
from server.models import CharacterManifest


def make_manifest(*, name="A", color="red", size=20, speed=200, hp=100,
                  power_damage=50, power_cd=700, extra_effects=None):
    on_hit = [{"effect": "damage", "amount": power_damage}]
    if extra_effects:
        on_hit.extend(extra_effects)
    return CharacterManifest.model_validate({
        "characterName": name, "color": color, "size": size,
        "speed": speed, "maxHealth": hp,
        "powers": [{
            "name": "Bolt", "key": "space", "cooldownMs": power_cd,
            "cast": {
                "kind": "projectile", "color": color,
                "speed": 600, "radius": 10, "lifetimeMs": 1500,
                "count": 1, "spreadDeg": 0, "pierce": False,
                "onHit": on_hit,
            },
        }],
    })


def make_shield_manifest():
    return CharacterManifest.model_validate({
        "characterName": "Bunker", "color": "cyan", "size": 30,
        "speed": 200, "maxHealth": 100,
        "powers": [{
            "name": "Wall", "key": "space", "cooldownMs": 200,
            "cast": {"kind": "shield", "color": "cyan", "amount": 50, "durationMs": 4000},
        }],
    })


def make_melee_manifest():
    return CharacterManifest.model_validate({
        "characterName": "Bonker", "color": "orange", "size": 24,
        "speed": 200, "maxHealth": 100,
        "powers": [{
            "name": "Bonk", "key": "space", "cooldownMs": 800,
            "cast": {
                "kind": "melee", "color": "orange",
                "range": 60, "arcDeg": 120,
                "onHit": [
                    {"effect": "damage", "amount": 30},
                    {"effect": "stun", "durationMs": 500},
                ],
            },
        }],
    })


def make_heal_manifest():
    return CharacterManifest.model_validate({
        "characterName": "Doc", "color": "lime", "size": 20,
        "speed": 200, "maxHealth": 100,
        "powers": [{
            "name": "Mend", "key": "space", "cooldownMs": 200,
            "cast": {"kind": "heal", "color": "lime", "amount": 40},
        }],
    })


def test_add_remove_player():
    g = GameState()
    p = g.add_player("ada", make_manifest())
    assert p.pid in g.players
    g.remove_player(p.pid)
    assert p.pid not in g.players


def test_diagonal_speed_normalized():
    from server.game_state import SPEED_MULT_GLOBAL
    g = GameState()
    p = g.add_player("ada", make_manifest(speed=200))
    start_x, start_y = p.x, p.y
    g.set_input(p.pid, 1, 1)
    g.step(1.0)
    dx = p.x - start_x
    dy = p.y - start_y
    dist = (dx * dx + dy * dy) ** 0.5
    expected = 200 * SPEED_MULT_GLOBAL
    assert abs(dist - expected) < 5


def test_projectile_hits_and_kills():
    g = GameState(width=400, height=400)
    a = g.add_player("attacker", make_manifest(power_damage=60))
    t = g.add_player("target", make_manifest(hp=50))
    a.x, a.y = 100, 200
    a.facing_x, a.facing_y = 1, 0
    t.x, t.y = 200, 200
    assert g.fire(a.pid, "space")
    for _ in range(60):
        g.step(0.05)
        if not t.alive:
            break
    assert not t.alive
    assert t.deaths == 1
    assert a.kills == 1


def test_cooldown_blocks_repeat_fire():
    g = GameState()
    a = g.add_player("a", make_manifest(power_cd=1000))
    assert g.fire(a.pid, "space")
    assert not g.fire(a.pid, "space")


def test_respawn_after_delay():
    g = GameState()
    a = g.add_player("a", make_manifest(power_damage=60))
    t = g.add_player("t", make_manifest(hp=10))
    a.x, a.y = 100, 200; a.facing_x, a.facing_y = 1, 0
    t.x, t.y = 200, 200
    g.fire(a.pid, "space")
    for _ in range(40):
        g.step(0.05)
        if not t.alive:
            break
    assert not t.alive
    future = time.monotonic() + RESPAWN_DELAY_S + 0.1
    g.step(0.05, now=future)
    assert t.alive
    assert t.health == t.manifest.maxHealth


def test_shield_absorbs_damage():
    g = GameState()
    bunker = g.add_player("bunker", make_shield_manifest())
    attacker = g.add_player("att", make_manifest(power_damage=30))
    bunker.x, bunker.y = 200, 200
    attacker.x, attacker.y = 100, 200
    attacker.facing_x, attacker.facing_y = 1, 0
    # Bunker raises shield (50 HP), then attacker fires (30 dmg).
    assert g.fire(bunker.pid, "space")
    hp_before = bunker.health
    g.fire(attacker.pid, "space")
    for _ in range(30):
        g.step(0.05)
    # All 30 damage absorbed; HP unchanged; shield should be at 20.
    assert bunker.health == hp_before
    assert 15 <= bunker.shield_amount <= 25


def test_slow_effect_reduces_speed():
    g = GameState()
    runner = g.add_player("r", make_manifest(speed=200))
    slower = g.add_player("s", make_manifest(
        power_damage=1, extra_effects=[{"effect": "slow", "factor": 0.25, "durationMs": 5000}],
    ))
    runner.x, runner.y = 200, 200
    slower.x, slower.y = 100, 200
    slower.facing_x, slower.facing_y = 1, 0
    g.fire(slower.pid, "space")
    # Step until projectile hits.
    for _ in range(40):
        g.step(0.05)
        if runner.health < runner.manifest.maxHealth:
            break
    assert runner.slow_until > 0
    assert runner.slow_factor == 0.25
    # Movement should now be slow.
    g.set_input(runner.pid, 1, 0)
    start = runner.x
    for _ in range(20):
        g.step(0.05)
    moved = runner.x - start
    # 200 * 0.25 = 50 px/s, over 1.0s = ~50 px (way less than 200).
    assert moved < 80


def test_stun_blocks_movement_and_fire():
    g = GameState()
    a = g.add_player("a", make_melee_manifest())
    b = g.add_player("b", make_manifest())
    a.x, a.y = 200, 200; a.facing_x, a.facing_y = 1, 0
    b.x, b.y = 230, 200
    assert g.fire(a.pid, "space")  # melee
    g.step(0.02)  # apply
    assert b.stun_until > 0
    # b tries to move and fire; nothing happens.
    g.set_input(b.pid, 1, 0)
    start_x = b.x
    g.step(0.1)
    assert b.x == start_x
    assert not g.fire(b.pid, "space")


def test_heal_cast_restores_health():
    g = GameState()
    doc = g.add_player("doc", make_heal_manifest())
    doc.health = 50
    g.fire(doc.pid, "space")
    assert doc.health == 90


def test_melee_only_hits_in_cone():
    g = GameState()
    a = g.add_player("a", make_melee_manifest())
    front = g.add_player("front", make_manifest())
    behind = g.add_player("behind", make_manifest())
    a.x, a.y = 200, 200; a.facing_x, a.facing_y = 1, 0
    front.x, front.y = 240, 200
    behind.x, behind.y = 160, 200
    g.fire(a.pid, "space")
    g.step(0.02)
    assert front.health < front.manifest.maxHealth
    assert behind.health == behind.manifest.maxHealth


def test_dot_damages_over_time():
    g = GameState()
    a = g.add_player("a", make_manifest(
        power_damage=1, extra_effects=[{"effect": "dot", "dps": 20, "durationMs": 1000}],
    ))
    t = g.add_player("t", make_manifest(hp=100))
    a.x, a.y = 100, 200; a.facing_x, a.facing_y = 1, 0
    t.x, t.y = 130, 200
    g.fire(a.pid, "space")
    # Step ~1 second.
    for _ in range(50):
        g.step(0.02)
    assert t.health < 90  # took at least ~10 damage from DoT


def test_pierce_passes_through():
    g = GameState()
    pm = CharacterManifest.model_validate({
        "characterName": "P", "color": "purple", "size": 20,
        "speed": 200, "maxHealth": 100,
        "powers": [{
            "name": "P", "key": "space", "cooldownMs": 200,
            "cast": {
                "kind": "projectile", "color": "purple",
                "speed": 600, "radius": 6, "lifetimeMs": 1500,
                "count": 1, "spreadDeg": 0, "pierce": True,
                "onHit": [{"effect": "damage", "amount": 10}],
            },
        }],
    })
    a = g.add_player("a", pm)
    t1 = g.add_player("t1", make_manifest())
    t2 = g.add_player("t2", make_manifest())
    a.x, a.y = 100, 200; a.facing_x, a.facing_y = 1, 0
    t1.x, t1.y = 200, 200
    t2.x, t2.y = 300, 200
    g.fire(a.pid, "space")
    for _ in range(40):
        g.step(0.02)
    assert t1.health < t1.manifest.maxHealth
    assert t2.health < t2.manifest.maxHealth


def test_snapshot_shape():
    g = GameState()
    g.add_player("ada", make_manifest())
    snap = g.snapshot()
    for k in ("players", "projectiles", "areas", "meleeFx", "tick", "width", "height"):
        assert k in snap
