"""Tests for game modes: FFA (default), team (friendly-fire off), CTF."""
from __future__ import annotations

import math
import pytest

from server.game_state import GameState, CTF_CAPTURES_TO_WIN, CTF_HOLD_SECONDS
from server.models import CharacterManifest


def make_manifest(name="P", color="red", *, melee_damage=50, melee_cd_ms=800,
                  hp=100, speed=200, size=32):
    return CharacterManifest.model_validate({
        "characterName": name,
        "color": color,
        "size": size,
        "speed": speed,
        "maxHealth": hp,
        "powers": [{
            "name": "Hit", "key": "space", "cooldownMs": melee_cd_ms,
            "cast": {
                "kind": "melee", "color": color, "range": 60, "arcDeg": 90,
                "onHit": [{"effect": "damage", "amount": melee_damage}],
            },
        }],
    })


def test_team_mode_friendly_fire_is_disabled():
    g = GameState()
    a = g.add_player("alice", make_manifest("A"))
    b = g.add_player("bob", make_manifest("B"))
    g.start_round(60, mode="team")
    # After start_round both should have a team assigned.
    assert a.team in (1, 2) and b.team in (1, 2)
    # Force them onto the same team and stand next to each other.
    a.team = b.team = 1
    a.x, a.y = 1000, 800
    b.x, b.y = 1040, 800
    a.facing_x, a.facing_y = 1, 0
    hp_before = b.health
    g.fire(a.pid, "space")
    assert b.health == hp_before, "teammate should not take damage in team mode"


def test_ffa_mode_keeps_friendly_fire_on():
    g = GameState()
    a = g.add_player("alice", make_manifest("A"))
    b = g.add_player("bob", make_manifest("B"))
    # FFA: default mode, no team assignment.
    a.x, a.y = 1000, 800
    b.x, b.y = 1040, 800
    a.facing_x, a.facing_y = 1, 0
    hp_before = b.health
    g.fire(a.pid, "space")
    assert b.health < hp_before


def test_team_mode_assigns_balanced_teams():
    g = GameState()
    for i in range(6):
        g.add_player(f"p{i}", make_manifest(f"P{i}"))
    g.start_round(60, mode="team")
    teams = sorted(p.team for p in g.players.values())
    assert teams.count(1) == 3
    assert teams.count(2) == 3


def test_ctf_pickup_and_capture_increments_score_and_can_win():
    g = GameState()
    p = g.add_player("alice", make_manifest("A"))
    g.start_round(60, mode="ctf")
    # Force into team 1 and place at enemy flag.
    p.team = 1
    enemy_flag = g.flags[2]
    p.x, p.y = enemy_flag["x"], enemy_flag["y"]
    g._last_dt = 1.0 / 30.0
    g._step_ctf(now=0.0)
    assert p.has_flag_team == 2
    assert g.flags[2]["carrier"] == p.pid

    # Walk back to own capture zone and tick long enough to score.
    own_zone = g.capture_zones[1]
    p.x, p.y = own_zone["x"], own_zone["y"]
    # Need CTF_HOLD_SECONDS * tick_hz ticks per capture.
    ticks_per_cap = int(CTF_HOLD_SECONDS * 30) + 2
    for _ in range(CTF_CAPTURES_TO_WIN):
        if not p.has_flag_team:
            p.x, p.y = enemy_flag["home_x"], enemy_flag["home_y"]
            g._step_ctf(now=0.0)
            p.x, p.y = own_zone["x"], own_zone["y"]
        for _ in range(ticks_per_cap):
            g._step_ctf(now=0.0)
            if not p.has_flag_team:
                break
    assert g.team_caps[1] == CTF_CAPTURES_TO_WIN
    # Round should auto-end after reaching the cap.
    assert g.match_status == "ended"


def test_ctf_progress_resets_on_leaving_zone():
    g = GameState()
    p = g.add_player("alice", make_manifest("A"))
    g.start_round(60, mode="ctf")
    p.team = 1
    g._last_dt = 1.0 / 30.0
    p.x, p.y = g.flags[2]["x"], g.flags[2]["y"]
    g._step_ctf(now=0.0)
    assert p.has_flag_team == 2
    own_zone = g.capture_zones[1]
    # Stand in zone for half the required time.
    p.x, p.y = own_zone["x"], own_zone["y"]
    for _ in range(int(CTF_HOLD_SECONDS * 30 / 2)):
        g._step_ctf(now=0.0)
    assert g._capture_progress[p.pid] > 0.0
    # Walk far away — progress resets.
    p.x, p.y = own_zone["x"] + 10_000, own_zone["y"]
    g._step_ctf(now=0.0)
    assert g._capture_progress[p.pid] == 0.0
    assert g.team_caps[1] == 0


def test_ctf_carrier_drops_flag_on_death():
    g = GameState()
    a = g.add_player("alice", make_manifest("A", hp=40))
    b = g.add_player("bob", make_manifest("B", melee_damage=60))
    g.start_round(60, mode="ctf")
    a.team, b.team = 1, 2
    a.health = a.manifest.maxHealth
    # Pick up enemy flag.
    a.x, a.y = g.flags[2]["x"], g.flags[2]["y"]
    g._step_ctf(now=0.0)
    assert a.has_flag_team == 2
    # Bob kills alice — flag should return home, alice no longer carrying.
    b.x, b.y = 1000, 800
    a.x, a.y = 1040, 800
    b.facing_x, b.facing_y = 1, 0
    g.fire(b.pid, "space")
    assert not a.alive
    assert a.has_flag_team == 0
    assert g.flags[2]["carrier"] is None
    assert (g.flags[2]["x"], g.flags[2]["y"]) == (g.flags[2]["home_x"], g.flags[2]["home_y"])


def test_aim_input_overrides_movement_facing():
    g = GameState()
    p = g.add_player("alice", make_manifest("A"))
    # Move right but aim down — facing should follow aim.
    g.set_input(p.pid, 1.0, 0.0, ax=0.0, ay=1.0)
    g.step(1.0 / 30, now=0.1)
    assert p.facing_y > 0.9
    assert abs(p.facing_x) < 0.1


def test_movement_smoothing_does_not_snap():
    g = GameState()
    p = g.add_player("alice", make_manifest("A", speed=300))
    g.set_input(p.pid, 1.0, 0.0)
    g.step(1.0 / 30, now=0.1)
    # After one tick we should NOT yet be at full speed (smoothed accel).
    assert 0 < p.vx < 300
    # After several ticks we should be near full speed.
    for i in range(20):
        g.step(1.0 / 30, now=0.1 + (i + 1) / 30)
    assert p.vx > 280
