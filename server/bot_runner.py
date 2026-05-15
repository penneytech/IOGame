"""Bot AI for soak tests and live classroom demos.

Two entry points:

* ``BOT_MANIFESTS`` and ``build_manifest(spec)`` — the 20 hand-designed
  characters (one per cast-kind variation, plus edge cases).
* ``LiveBotSwarm`` — spawns those bots into a running ``GameState`` and
  drives their AI from an asyncio task. Used by the teacher dashboard's
  "Spawn 20 bots" button.
"""
from __future__ import annotations

import asyncio
import logging
import math
import os
import random
from typing import Any

from .game_state import GameState
from .models import CharacterManifest


# ---------------------------------------------------------------------------
# Optional verbose AI logging. Off by default; teacher dashboard can flip it
# on at runtime via set_ai_logging(). Writes one file under the repo root.
# ---------------------------------------------------------------------------

_AI_LOG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "live_ai.log",
)
_ai_logger: logging.Logger | None = None
_ai_log_enabled: bool = False


def _get_ai_logger() -> logging.Logger:
    global _ai_logger
    if _ai_logger is None:
        lg = logging.getLogger("ai_live")
        lg.setLevel(logging.INFO)
        # Avoid duplicating into root handlers (e.g. uvicorn's stderr).
        lg.propagate = False
        if not lg.handlers:
            h = logging.FileHandler(_AI_LOG_PATH, mode="a", encoding="utf-8")
            h.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
            lg.addHandler(h)
        _ai_logger = lg
    return _ai_logger


def set_ai_logging(enabled: bool) -> dict:
    """Toggle the verbose live-AI log. Returns status info."""
    global _ai_log_enabled
    _ai_log_enabled = bool(enabled)
    lg = _get_ai_logger()
    lg.info("AI_LOG %s", "ON" if _ai_log_enabled else "OFF")
    return {"enabled": _ai_log_enabled, "path": _AI_LOG_PATH}


def get_ai_logging_status() -> dict:
    return {"enabled": _ai_log_enabled, "path": _AI_LOG_PATH}


def _ailog(msg: str) -> None:
    if _ai_log_enabled:
        _get_ai_logger().info(msg)


# ---------------------------------------------------------------------------
# Manifest helpers — keep these tiny so the catalogue stays readable.
# ---------------------------------------------------------------------------

def _proj(name, key, color, dmg, *, cd=600, speed=520, count=1, spread=0,
          pierce=False, extra=None, lifetime=1400, radius=6):
    onhit = [{"effect": "damage", "amount": dmg}]
    if extra:
        onhit.extend(extra)
    return {
        "name": name, "key": key, "cooldownMs": cd,
        "cast": {
            "kind": "projectile", "color": color, "speed": speed,
            "radius": radius, "lifetimeMs": lifetime,
            "count": count, "spreadDeg": spread, "pierce": pierce,
            "onHit": onhit,
        },
    }


def _area(name, key, color, *, cd=4000, radius=80, dur=2500, tick=300, ontick=None,
          follow=False):
    return {
        "name": name, "key": key, "cooldownMs": cd,
        "cast": {
            "kind": "area", "color": color, "radius": radius,
            "durationMs": dur, "tickIntervalMs": tick,
            "followOwner": follow,
            "onTick": ontick or [{"effect": "damage", "amount": 6}],
        },
    }


def _melee(name, key, color, *, cd=900, rng=70, arc=90, onhit=None):
    return {
        "name": name, "key": key, "cooldownMs": cd,
        "cast": {
            "kind": "melee", "color": color, "range": rng, "arcDeg": arc,
            "onHit": onhit or [{"effect": "damage", "amount": 18}],
        },
    }


def _dash(name, key, color, *, cd=3000, dist=200, dur=180, invuln=True):
    return {
        "name": name, "key": key, "cooldownMs": cd,
        "cast": {
            "kind": "dash", "color": color, "distance": dist,
            "durationMs": dur, "invulnerable": invuln,
        },
    }


def _shield(name, key, color, amount, *, cd=6000, dur=4000):
    return {
        "name": name, "key": key, "cooldownMs": cd,
        "cast": {
            "kind": "shield", "color": color,
            "amount": amount, "durationMs": dur,
        },
    }


def _heal(name, key, color, amount, *, cd=5000):
    return {
        "name": name, "key": key, "cooldownMs": cd,
        "cast": {"kind": "heal", "color": color, "amount": amount},
    }


# ---------------------------------------------------------------------------
# 20 bots covering every cast kind + every effect kind, plus edge cases.
# ---------------------------------------------------------------------------

BOT_MANIFESTS: list[dict[str, Any]] = [
    {"characterName": "Ranger", "color": "green", "size": 20, "speed": 260,
     "maxHealth": 100, "powers": [_proj("Arrow", "space", "green", 16, cd=500, speed=600)]},
    {"characterName": "Pyromancer", "color": "#ff6a3d", "size": 22, "speed": 230, "maxHealth": 90,
     "powers": [
         _proj("Fireball", "space", "orange", 11, cd=800, count=2, spread=14,
               extra=[{"effect": "dot", "dps": 8, "durationMs": 1200}]),
         _area("Firewall", "q", "red", radius=55, dur=2500,
               ontick=[{"effect": "damage", "amount": 5},
                       {"effect": "dot", "dps": 5, "durationMs": 800}]),
         _dash("Phase Step", "f", "white"),
     ]},
    {"characterName": "IceTank", "color": "#9ad3ff", "size": 32, "speed": 170, "maxHealth": 220,
     "powers": [
         _proj("Frost Bolt", "space", "#9ad3ff", 12, speed=420,
               extra=[{"effect": "slow", "factor": 0.4, "durationMs": 1500}]),
         _melee("Cleave", "q", "blue", cd=1100, rng=80, arc=120,
                onhit=[{"effect": "damage", "amount": 22},
                       {"effect": "knockback", "strength": 220}]),
         _shield("Bulwark", "e", "cyan", 80, dur=4000),
     ]},
    {"characterName": "Rogue", "color": "#a070ff", "size": 18, "speed": 320, "maxHealth": 80,
     "powers": [
         _proj("Knife", "space", "white", 10, cd=350, speed=700, pierce=True),
         _melee("Backstab", "q", "purple", cd=1500, rng=55, arc=60,
                onhit=[{"effect": "damage", "amount": 28},
                       {"effect": "stun", "durationMs": 250}]),
         _dash("Blink", "f", "#a070ff", dist=240),
     ]},
    {"characterName": "Medic", "color": "lime", "size": 24, "speed": 250, "maxHealth": 120,
     "powers": [
         _proj("Dart", "space", "white", 10, cd=600, speed=520),
         _heal("Mend", "e", "lime", 60),
         _area("Regen Pool", "q", "green", cd=7000, radius=80, dur=4000, tick=400, follow=True,
               ontick=[{"effect": "heal", "amount": 6}]),
     ]},
    {"characterName": "Paladin", "color": "#ffcb47", "size": 28, "speed": 200, "maxHealth": 180,
     "powers": [
         _melee("Smite", "space", "yellow", cd=900, rng=70,
                onhit=[{"effect": "damage", "amount": 20},
                       {"effect": "knockback", "strength": 150}]),
         _shield("Bastion", "e", "gold", 60, dur=5000),
         _heal("LayOnHands", "q", "white", 50, cd=8000),
     ]},
    {"characterName": "Bomber", "color": "#2a6b1a", "size": 26, "speed": 210, "maxHealth": 110,
     "powers": [
         _proj("Grenade", "space", "#2a6b1a", 22, cd=900, speed=380, radius=8,
               extra=[{"effect": "knockback", "strength": 280}]),
         _area("Poison Cloud", "q", "purple", cd=5000, radius=100, dur=3000, tick=300,
               ontick=[{"effect": "damage", "amount": 5},
                       {"effect": "slow", "factor": 0.6, "durationMs": 800}]),
         _dash("Roll Away", "f", "white", dist=180),
     ]},
    {"characterName": "Berserker", "color": "maroon", "size": 26, "speed": 240, "maxHealth": 140,
     "powers": [
         _melee("Slash", "space", "red", cd=550, rng=65, arc=80,
                onhit=[{"effect": "damage", "amount": 16}]),
         _melee("Reaver", "q", "orange", cd=1800, rng=80, arc=140,
                onhit=[{"effect": "damage", "amount": 18},
                       {"effect": "dot", "dps": 12, "durationMs": 2000},
                       {"effect": "knockback", "strength": 100}]),
     ]},
    {"characterName": "Sniper", "color": "navy", "size": 18, "speed": 200, "maxHealth": 70,
     "powers": [
         _proj("Snipe", "space", "yellow", 40, cd=2200, speed=900, pierce=True, radius=4),
         _dash("Reposition", "f", "white", dist=160),
     ]},
    {"characterName": "Shotgunner", "color": "brown", "size": 24, "speed": 230, "maxHealth": 110,
     "powers": [
         _proj("Buckshot", "space", "yellow", 7, cd=900, speed=520, count=6, spread=45,
               lifetime=600),
     ]},
    {"characterName": "Stunner", "color": "teal", "size": 22, "speed": 220, "maxHealth": 100,
     "powers": [
         _proj("Bolt", "space", "cyan", 8, cd=500),
         _area("Net", "q", "white", cd=6000, radius=90, dur=1200, tick=400,
               ontick=[{"effect": "stun", "durationMs": 250}]),
     ]},
    {"characterName": "Cleric", "color": "white", "size": 24, "speed": 240, "maxHealth": 120,
     "powers": [
         _proj("Light", "space", "white", 6, cd=400),
         _heal("Bless", "e", "white", 40, cd=4000),
     ]},
    {"characterName": "Bruiser", "color": "silver", "size": 28, "speed": 220, "maxHealth": 150,
     "powers": [
         _melee("Hammer", "space", "silver", cd=1100, rng=75,
                onhit=[{"effect": "damage", "amount": 18},
                       {"effect": "knockback", "strength": 350}]),
         _shield("Wall", "e", "gray", 50, dur=3000),
     ]},
    {"characterName": "Harasser", "color": "pink", "size": 16, "speed": 340, "maxHealth": 70,
     "powers": [
         _proj("Needle", "space", "pink", 5, cd=200, speed=700, radius=3, pierce=True),
     ]},
    {"characterName": "Stormcaller", "color": "blue", "size": 22, "speed": 220, "maxHealth": 90,
     "powers": [
         _area("Storm", "space", "cyan", cd=2200, radius=70, dur=1800, tick=300,
               ontick=[{"effect": "damage", "amount": 7}]),
         _area("Hail", "q", "white", cd=4000, radius=110, dur=2400, tick=400,
               ontick=[{"effect": "damage", "amount": 5},
                       {"effect": "slow", "factor": 0.7, "durationMs": 600}]),
     ]},
    {"characterName": "Hexer", "color": "magenta", "size": 22, "speed": 230, "maxHealth": 100,
     "powers": [
         _proj("Curse", "space", "magenta", 8, cd=600,
               extra=[{"effect": "slow", "factor": 0.6, "durationMs": 1200},
                      {"effect": "dot", "dps": 8, "durationMs": 1500}]),
         _melee("Rebuke", "q", "purple", cd=1500, rng=60, arc=100,
                onhit=[{"effect": "damage", "amount": 14},
                       {"effect": "stun", "durationMs": 300},
                       {"effect": "knockback", "strength": 180}]),
         _heal("Sip", "e", "lime", 30, cd=6000),
     ]},
    {"characterName": "Phantom", "color": "white", "size": 18, "speed": 300, "maxHealth": 80,
     "powers": [
         _melee("Strike", "space", "white", cd=600, rng=55,
                onhit=[{"effect": "damage", "amount": 14}]),
         _dash("Dash A", "f", "white", dist=240, cd=2200),
         _dash("Dash B", "q", "cyan", dist=140, cd=1400, invuln=False),
     ]},
    {"characterName": "Cannoneer", "color": "gold", "size": 26, "speed": 200, "maxHealth": 130,
     "powers": [
         _proj("Cannon", "space", "gold", 28, cd=1800, speed=400, radius=9,
               extra=[{"effect": "stun", "durationMs": 350},
                      {"effect": "knockback", "strength": 200}]),
     ]},
    {"characterName": "GlassCannon", "color": "red", "size": 14, "speed": 280, "maxHealth": 50,
     "powers": [
         _proj("Lance", "space", "red", 30, cd=1200, speed=750, pierce=True),
         _dash("Vanish", "f", "white", dist=220),
     ]},
    {"characterName": "Druid", "color": "lime", "size": 24, "speed": 230, "maxHealth": 130,
     "powers": [
         _proj("Thorn", "space", "green", 9, cd=450,
               extra=[{"effect": "slow", "factor": 0.7, "durationMs": 800}]),
         _area("Grove", "q", "lime", cd=8000, radius=90, dur=4000, tick=500, follow=True,
               ontick=[{"effect": "heal", "amount": 5}]),
         _shield("Bark", "e", "brown", 40, dur=3500),
     ]},
]


def build_manifests() -> list[CharacterManifest]:
    """Validate every bot manifest. Raises if any are malformed."""
    return [CharacterManifest.model_validate(spec) for spec in BOT_MANIFESTS]


# ---------------------------------------------------------------------------
# AI driver shared between offline soak test and live spawn.
# ---------------------------------------------------------------------------

# Per-bot scratch state keyed by pid. Reset implicitly when a pid disappears.
_AI_STATE: dict[str, dict[str, Any]] = {}


def _eff_kind(eff) -> str:
    """Extract the 'effect' discriminator from an Effect (pydantic) or dict."""
    if isinstance(eff, dict):
        return eff.get("effect", "")
    return getattr(eff, "effect", "")


def _classify(manifest) -> str:
    """Bucket a character into a coarse archetype from its powers + stats."""
    kinds = [p.cast.kind for p in manifest.powers]
    has_heal_cast = "heal" in kinds
    has_dash = "dash" in kinds
    has_shield = "shield" in kinds
    has_melee = "melee" in kinds
    has_proj = "projectile" in kinds
    primary = manifest.powers[0].cast.kind if manifest.powers else "projectile"
    # Healer ONLY if the primary attack is heal-or-projectile-but-weak AND
    # heal exists. Anyone whose primary is melee or whose damage projectile
    # exists is a fighter, not a healer.
    if has_heal_cast and primary in ("heal", "area") and not has_melee:
        return "healer"
    if has_heal_cast and primary == "projectile":
        # Cleric/Medic-style: weak ranged + heal. Treat as healer only if
        # the projectile damage is low (<= 10).
        proj0 = manifest.powers[0].cast
        first_dmg = 0
        for eff in (getattr(proj0, "onHit", None) or []):
            if _eff_kind(eff) == "damage":
                first_dmg = max(first_dmg, getattr(eff, "amount", 0)
                                if not isinstance(eff, dict) else eff.get("amount", 0))
        if first_dmg <= 10:
            return "healer"
    if has_dash and has_melee and manifest.maxHealth <= 100:
        return "assassin"
    if manifest.maxHealth >= 140 and (has_shield or has_melee):
        return "tank"
    if primary in ("projectile", "area"):
        return "ranged"
    if has_melee:
        return "tank"
    return "ranged"


def _ideal_range(arch: str) -> tuple[float, float]:
    """Preferred (min, max) distance to the focused enemy."""
    if arch == "ranged":
        return (260.0, 420.0)
    if arch == "assassin":
        return (40.0, 70.0)
    if arch == "healer":
        return (200.0, 360.0)
    return (40.0, 90.0)  # tank / brawler


def _separation(game: GameState, me, *, radius: float = 90.0) -> tuple[float, float]:
    """Sum of repulsion vectors from nearby players (allies + enemies).
    Falls off linearly inside `radius`. Output is unnormalised — caller
    blends it with their desired-movement vector.
    """
    rx = 0.0
    ry = 0.0
    rsq = radius * radius
    for o in game.players.values():
        if o.pid == me.pid or not o.alive:
            continue
        dx = me.x - o.x
        dy = me.y - o.y
        d2 = dx * dx + dy * dy
        if d2 <= 1.0 or d2 >= rsq:
            continue
        d = math.sqrt(d2)
        # Strength: 1 at touching, 0 at radius.
        w = (radius - d) / radius
        rx += (dx / d) * w
        ry += (dy / d) * w
    return rx, ry


def _nearest_ally(game: GameState, me) -> Any:
    best = None
    best_d = float("inf")
    for other in game.players.values():
        if other.pid == me.pid or not other.alive or other.eliminated:
            continue
        if me.team and other.team != me.team:
            continue
        if not me.team and not other.pid.startswith("BOT:"):
            continue  # in FFA, treat other bots as soft "allies" for healing
        if not me.team and other.pid == me.pid:
            continue
        d = math.hypot(other.x - me.x, other.y - me.y)
        if d < best_d:
            best_d = d
            best = other
    return best


def _pick_target(game: GameState, me, st: dict) -> Any:
    """Focus-fire: prefer current target if still valid + low HP, else lowest HP in range."""
    candidates = []
    for other in game.players.values():
        if other.pid == me.pid or not other.alive or other.eliminated:
            continue
        if me.team and other.team == me.team:
            continue
        d = math.hypot(other.x - me.x, other.y - me.y)
        # Score: lower HP and closer = better focus.
        score = other.health + d * 0.15
        candidates.append((score, d, other))
    if not candidates:
        return None
    candidates.sort(key=lambda c: c[0])
    # Sticky focus: keep current target if still in top 3 to avoid ping-ponging.
    cur = st.get("target_pid")
    if cur:
        for score, d, t in candidates[:3]:
            if t.pid == cur:
                return t
    chosen = candidates[0][2]
    st["target_pid"] = chosen.pid
    return chosen


def _power_by_kind(me, kind: str):
    for p in me.manifest.powers:
        if p.cast.kind == kind:
            return p
    return None


def _power_with_effect(me, effect: str):
    for p in me.manifest.powers:
        # For heal cast or onHit/onTick effects.
        if p.cast.kind == effect:
            return p
        for eff in (getattr(p.cast, "onHit", None) or []):
            if _eff_kind(eff) == effect:
                return p
        for eff in (getattr(p.cast, "onTick", None) or []):
            if _eff_kind(eff) == effect:
                return p
    return None


def _try_fire(game: GameState, me, power, now: float, *, skill: float = 1.0,
              rng: random.Random | None = None) -> bool:
    if power is None:
        return False
    ready_at = me.cooldowns.get(power.name, 0.0)
    if now < ready_at:
        return False
    # Low-skill bots occasionally "fumble" a ready ability (miss the keypress).
    if rng is not None and skill < 1.0:
        fumble_chance = (1.0 - skill) * 0.20  # up to 20% per call at min skill
        if rng.random() < fumble_chance:
            _ailog(f"FUMBLE pid={me.pid[:8]} power={power.name} skill={skill:.2f}")
            return False
    fired = game.fire(me.pid, power.key, now=now)
    if fired:
        _ailog(f"FIRE pid={me.pid[:8]} who={me.username} power={power.name} "
               f"kind={power.cast.kind} hp={me.health:.0f}/{me.manifest.maxHealth}")
    return fired


def _ctf_objective(game: GameState, me, st: dict, now: float,
                   skill: float, rng: random.Random):
    """CTF behaviour. Returns:
      - None  → handled this tick fully (movement+powers issued, caller should return)
      - target Player → caller should engage this enemy in combat (we already moved)
    """
    enemy_team = 2 if me.team == 1 else 1
    own_flag = game.flags.get(me.team)
    enemy_flag = game.flags.get(enemy_team)
    own_zone = game.capture_zones.get(me.team)
    if own_flag is None or enemy_flag is None or own_zone is None:
        return _pick_target(game, me, st)  # fall back to brawl

    # 1) If I'm carrying enemy flag → run to my own capture zone.
    if me.has_flag_team == enemy_team:
        zx, zy = own_zone["x"], own_zone["y"]
        dx, dy = zx - me.x, zy - me.y
        d = math.hypot(dx, dy) or 1.0
        nx, ny = dx / d, dy / d
        in_zone = d < own_zone["radius"]
        # If a chaser is very close, fire at them while running.
        threat = None
        for o in game.players.values():
            if o.pid == me.pid or not o.alive or o.team == me.team:
                continue
            od = math.hypot(o.x - me.x, o.y - me.y)
            if od < 200:
                if threat is None or od < math.hypot(threat.x - me.x, threat.y - me.y):
                    threat = o
        if in_zone:
            # Stand near zone center; only nudge if near edge. Keep facing
            # nearest threat so defensive abilities + counter-attacks work.
            nudge_x = nx * 0.3 if d > own_zone["radius"] * 0.5 else 0.0
            nudge_y = ny * 0.3 if d > own_zone["radius"] * 0.5 else 0.0
            if threat is not None:
                tx, ty = threat.x - me.x, threat.y - me.y
                tlen = math.hypot(tx, ty) or 1.0
                game.set_input(me.pid, nudge_x, nudge_y, ax=tx / tlen, ay=ty / tlen)
            else:
                game.set_input(me.pid, nudge_x, nudge_y, ax=nx, ay=ny)
        else:
            if threat is not None:
                tx, ty = threat.x - me.x, threat.y - me.y
                tlen = math.hypot(tx, ty) or 1.0
                # Separation while running.
                sep_x, sep_y = _separation(game, me, radius=80.0)
                mx, my = nx + sep_x * 0.8, ny + sep_y * 0.8
                ml = math.hypot(mx, my) or 1.0
                game.set_input(me.pid, mx / ml, my / ml, ax=tx / tlen, ay=ty / tlen)
            else:
                sep_x, sep_y = _separation(game, me, radius=80.0)
                mx, my = nx + sep_x * 0.8, ny + sep_y * 0.8
                ml = math.hypot(mx, my) or 1.0
                game.set_input(me.pid, mx / ml, my / ml, ax=nx, ay=ny)
        # Mash defensive abilities every tick (shield/heal).
        for kind in ("shield", "heal"):
            p = _power_by_kind(me, kind)
            if p:
                _try_fire(game, me, p, now, skill=skill, rng=rng)
        # If a threat is in melee range while in zone, swing.
        if threat is not None and in_zone:
            tdist = math.hypot(threat.x - me.x, threat.y - me.y)
            if tdist <= 110:
                p = _power_by_kind(me, "melee")
                if p:
                    _try_fire(game, me, p, now, skill=skill, rng=rng)
            else:
                # Lob a projectile at the chaser.
                pp = _power_by_kind(me, "projectile")
                if pp:
                    _try_fire(game, me, pp, now, skill=skill, rng=rng)
        return None  # fully handled

    # 1b) Defender duty: if our carrier exists, allies near the zone should
    # protect them. Pick nearest enemy to the carrier as combat target.
    for team, f in game.flags.items():
        if team == me.team:
            continue
        cid = f.get("carrier")
        if cid is None:
            continue
        carrier = game.players.get(cid)
        if carrier is None or not carrier.alive or carrier.team != me.team:
            continue
        # Find an enemy threatening the carrier.
        best = None
        best_d = float("inf")
        for o in game.players.values():
            if o.pid == me.pid or not o.alive or o.team == me.team:
                continue
            od = math.hypot(o.x - carrier.x, o.y - carrier.y)
            if od < 280 and od < best_d:
                best_d = od
                best = o
        if best is not None:
            return best  # combat-engage the threat

    # 2) If an enemy is carrying our flag → chase the carrier (combat target).
    own_carrier_pid = own_flag.get("carrier")
    if own_carrier_pid:
        carrier = game.players.get(own_carrier_pid)
        if carrier is not None and carrier.alive:
            return carrier  # combat-engage

    # 3) Else go grab enemy flag (its current x/y — could be home or dropped).
    if enemy_flag.get("carrier") is None:
        fx, fy = enemy_flag["x"], enemy_flag["y"]
        dx, dy = fx - me.x, fy - me.y
        d = math.hypot(dx, dy) or 1.0
        # If close to flag, just dash straight in (ignore combat aim).
        nx, ny = dx / d, dy / d
        # If an enemy is right next to us, return them as combat target.
        nearest_enemy = None
        nearest_d = float("inf")
        for o in game.players.values():
            if o.pid == me.pid or not o.alive or o.team == me.team:
                continue
            od = math.hypot(o.x - me.x, o.y - me.y)
            if od < nearest_d:
                nearest_d = od
                nearest_enemy = o
        if nearest_enemy is not None and nearest_d < 100 and d > 80:
            return nearest_enemy  # fight first
        sep_x, sep_y = _separation(game, me, radius=80.0)
        mx, my = nx + sep_x * 0.8, ny + sep_y * 0.8
        ml = math.hypot(mx, my) or 1.0
        game.set_input(me.pid, mx / ml, my / ml, ax=nx, ay=ny)
        return None

    # 4) Enemy carrier exists and isn't ours → fight normally.
    return _pick_target(game, me, st)


def step_bot_ai(game: GameState, pid: str, now: float, rng: random.Random) -> None:
    """Drive one bot for one tick using archetype-aware tactics."""
    me = game.players.get(pid)
    if me is None or not me.alive or me.eliminated:
        return
    st = _AI_STATE.setdefault(pid, {
        "last_dmg_dealt_at": now,
        "last_hp": me.health,
        "force_aggro_until": 0.0,
        "noise_phase": rng.random() * math.tau,
        # Skill in [0.4, 1.0]. Higher = sharper aim, faster reactions, fewer fumbles.
        "skill": 0.4 + rng.random() * 0.6,
        "next_decision_at": now,
        "aim_jitter": (rng.random() - 0.5) * 0.6,
    })
    # Always recompute arch so a fix to the classifier picks up immediately
    # for live demos (cheap; <1us).
    arch = _classify(me.manifest)
    st["arch"] = arch
    skill = st["skill"]
    hp_frac = me.health / max(1.0, me.manifest.maxHealth)

    # Reaction lag: low-skill bots only refresh decisions every ~150-300ms.
    # High-skill (1.0) refresh every tick. We always update movement, but
    # gate target reselection + ability use through this gate.
    react_interval = 0.05 + (1.0 - skill) * 0.30  # 50ms .. 350ms
    can_act = now >= st["next_decision_at"]
    if can_act:
        st["next_decision_at"] = now + react_interval
        # Re-roll aim jitter occasionally so it isn't a fixed bias.
        st["aim_jitter"] = (rng.random() - 0.5) * (1.0 - skill) * 1.2

    # --- Healer: support nearest ally first, only fight if safe ----------
    # Skip the healer support branch if force-aggression is active (we want
    # to close + fight, not back off to heal).
    if arch == "healer" and now >= st["force_aggro_until"]:
        ally = _nearest_ally(game, me)
        if ally is not None and ally.health < ally.manifest.maxHealth * 0.7:
            heal_power = _power_by_kind(me, "heal")
            if heal_power and _try_fire(game, me, heal_power, now, skill=skill, rng=rng):
                pass  # fired self-heal; AOE/follow goes via Grove path below
            grove = next((p for p in me.manifest.powers
                          if p.cast.kind == "area" and any(
                              _eff_kind(eff) == "heal"
                              for eff in (getattr(p.cast, "onTick", None) or []))), None)
            if grove:
                _try_fire(game, me, grove, now, skill=skill, rng=rng)
            # Move toward ally
            adx, ady = ally.x - me.x, ally.y - me.y
            ad = math.hypot(adx, ady) or 1.0
            mx, my = adx / ad, ady / ad
            sep_x, sep_y = _separation(game, me, radius=90.0)
            mx += sep_x * 1.0
            my += sep_y * 1.0
            ml = math.hypot(mx, my) or 1.0
            game.set_input(pid, mx / ml, my / ml, ax=adx / ad, ay=ady / ad)
            return

    # --- CTF objective overrides normal target-seeking ------------------
    if game.mode == "ctf" and me.team in (1, 2):
        ctf_action = _ctf_objective(game, me, st, now, skill, rng)
        if ctf_action is not None:
            # Returned a target to combat-engage (e.g. enemy carrier),
            # otherwise the helper already issued movement and fired powers.
            target = ctf_action
            dx, dy = target.x - me.x, target.y - me.y
            dist = math.hypot(dx, dy) or 1.0
            ax, ay = dx / dist, dy / dist
            perp_x, perp_y = -ay, ax
            # fall through to combat block (skip target re-pick)
            _ctf_did_move = True
        else:
            return  # _ctf_objective handled this tick fully
    else:
        _ctf_did_move = False

    # --- Pick target & basic geometry -----------------------------------
    if not _ctf_did_move:
        target = _pick_target(game, me, st)
        if target is None:
            game.set_input(pid, 0.0, 0.0)
            return
        dx, dy = target.x - me.x, target.y - me.y
        dist = math.hypot(dx, dy) or 1.0
        ax, ay = dx / dist, dy / dist
        perp_x, perp_y = -ay, ax

    # --- Track damage dealt for anti-stalemate --------------------------
    if me.kills > st.get("last_kills", me.kills):
        st["last_dmg_dealt_at"] = now
    st["last_kills"] = me.kills
    # Crude proxy: target's HP went down recently → assume we contributed.
    last_target_hp = st.get("last_target_hp", target.health)
    if target.health < last_target_hp - 0.5:
        st["last_dmg_dealt_at"] = now
    st["last_target_hp"] = target.health

    stalemate = (now - st["last_dmg_dealt_at"]) > 3.5
    if stalemate and now > st["force_aggro_until"]:
        st["force_aggro_until"] = now + 4.0
        _ailog(f"STALEMATE pid={me.pid[:8]} who={me.username} forcing aggression")

    forcing = now < st["force_aggro_until"]

    # Log target switches once per change.
    prev_target = st.get("logged_target_pid")
    if target.pid != prev_target:
        _ailog(f"TARGET pid={me.pid[:8]} who={me.username} arch={arch} "
               f"-> {target.username} dist={dist:.0f} skill={skill:.2f}")
        st["logged_target_pid"] = target.pid

    # --- Self-preservation: low HP retreat / heal / shield --------------
    low_hp = hp_frac < 0.30
    if low_hp and not st.get("logged_low_hp"):
        _ailog(f"LOW_HP pid={me.pid[:8]} who={me.username} hp={hp_frac:.0%}")
        st["logged_low_hp"] = True
    if not low_hp and st.get("logged_low_hp"):
        st["logged_low_hp"] = False
    if low_hp:
        heal = _power_by_kind(me, "heal")
        _try_fire(game, me, heal, now, skill=skill, rng=rng)
        shield = _power_by_kind(me, "shield")
        _try_fire(game, me, shield, now, skill=skill, rng=rng)

    # --- Movement: pick desired distance band ---------------------------
    rmin, rmax = _ideal_range(arch)
    if forcing:
        rmin, rmax = (0.0, 60.0)  # close in to break the stalemate
    if low_hp and not forcing:
        rmin, rmax = (rmin + 120, rmax + 200)  # back off

    # Strafe noise so bots don't stack
    strafe = math.sin(now * 1.7 + st["noise_phase"]) * 0.45

    if dist > rmax:
        mx, my = ax, ay  # close in
    elif dist < rmin:
        mx, my = -ax, -ay  # back off
    else:
        mx, my = perp_x, perp_y  # circle
    mx += perp_x * strafe
    my += perp_y * strafe
    # Personal space: push away from anyone within ~90px so bots don't pile up.
    sep_x, sep_y = _separation(game, me, radius=90.0)
    mx += sep_x * 1.3
    my += sep_y * 1.3
    mlen = math.hypot(mx, my) or 1.0
    # Aim jitter: low-skill bots aim less precisely.
    j = st["aim_jitter"]
    aim_x = ax + perp_x * j
    aim_y = ay + perp_y * j
    alen = math.hypot(aim_x, aim_y) or 1.0
    game.set_input(pid, mx / mlen, my / mlen, ax=aim_x / alen, ay=aim_y / alen)

    # Combat decisions are gated by reaction time.
    if not can_act:
        return

    # --- Combat: pick a power based on situation ------------------------
    # Assassin: dash in if far & melee ready
    if arch == "assassin" and dist > 120:
        dash = _power_by_kind(me, "dash")
        if dash and _try_fire(game, me, dash, now, skill=skill, rng=rng):
            return

    # Disabling powers when target is mobile / forcing close-up
    if dist <= 110:
        for kind in ("melee",):
            p = _power_by_kind(me, kind)
            if p and _try_fire(game, me, p, now, skill=skill, rng=rng):
                return

    # Area drops at bands they cover well
    if dist <= 140:
        for p in me.manifest.powers:
            if p.cast.kind == "area" and not any(
                _eff_kind(eff) == "heal"
                for eff in (getattr(p.cast, "onTick", None) or [])):
                if _try_fire(game, me, p, now, skill=skill, rng=rng):
                    return

    # Default: try projectile, then anything remaining (so soak coverage holds)
    proj = _power_by_kind(me, "projectile")
    if proj and _try_fire(game, me, proj, now, skill=skill, rng=rng):
        return

    powers = list(me.manifest.powers)
    rng.shuffle(powers)
    for power in powers:
        if _try_fire(game, me, power, now, skill=skill, rng=rng):
            return


# ---------------------------------------------------------------------------
# Live driver — used by the teacher dashboard.
# ---------------------------------------------------------------------------

class LiveBotSwarm:
    """Spawns BOT_MANIFESTS into a running GameState and drives them.

    Bots are visible in /spectator just like real players. They have unlimited
    lives in this mode (the server's normal respawn flow handles deaths) so the
    teacher can show a continuous demo brawl.
    """

    BOT_PREFIX = "BOT:"  # username prefix so we can find/clean them up

    def __init__(self, game: GameState, *, tick_hz: float = 30.0) -> None:
        self.game = game
        self.tick_hz = tick_hz
        self._task: asyncio.Task | None = None
        self._pids: list[str] = []
        self._rng = random.Random(0)

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    @property
    def count(self) -> int:
        return sum(1 for pid in self._pids if pid in self.game.players)

    def spawn(self) -> int:
        """Add all bots to the game. Returns the number spawned."""
        for spec in BOT_MANIFESTS:
            manifest = CharacterManifest.model_validate(spec)
            p = self.game.add_player(self.BOT_PREFIX + spec["characterName"], manifest)
            self._pids.append(p.pid)
            _ailog(f"BOT_SPAWN pid={p.pid[:8]} name={spec['characterName']}")
        return len(self._pids)

    def remove(self) -> int:
        """Remove every bot we spawned. Returns the number removed."""
        n = 0
        for pid in self._pids:
            if pid in self.game.players:
                self.game.remove_player(pid)
                n += 1
        self._pids.clear()
        return n

    async def _loop(self) -> None:
        import time as _t
        dt = 1.0 / self.tick_hz
        # Per-bot prior-state cache so we can emit DEATH/RESPAWN/KILL when
        # values change. Keyed by pid.
        prior: dict[str, dict] = {}
        try:
            while True:
                now = _t.monotonic()
                for pid in list(self._pids):
                    p = self.game.players.get(pid)
                    if p is None:
                        continue
                    try:
                        step_bot_ai(self.game, pid, now, self._rng)
                    except Exception:
                        import logging
                        logging.getLogger("bot_runner").exception(
                            "bot AI failed pid=%s", pid)
                        _ailog(f"AI_ERROR pid={pid[:8]}")

                    pr = prior.get(pid)
                    if pr is None:
                        prior[pid] = {
                            "alive": p.alive,
                            "lives": p.lives_remaining,
                            "kills": p.kills,
                            "eliminated": p.eliminated,
                        }
                        continue
                    if pr["alive"] and not p.alive:
                        _ailog(f"DEATH pid={pid[:8]} who={p.username} "
                               f"lives_left={p.lives_remaining}")
                    if not pr["alive"] and p.alive:
                        _ailog(f"RESPAWN pid={pid[:8]} who={p.username} "
                               f"lives_left={p.lives_remaining}")
                    if p.kills > pr["kills"]:
                        _ailog(f"KILL pid={pid[:8]} who={p.username} "
                               f"total_kills={p.kills}")
                    if p.eliminated and not pr["eliminated"]:
                        _ailog(f"ELIMINATED pid={pid[:8]} who={p.username}")
                    pr["alive"] = p.alive
                    pr["lives"] = p.lives_remaining
                    pr["kills"] = p.kills
                    pr["eliminated"] = p.eliminated
                await asyncio.sleep(dt)
        except asyncio.CancelledError:
            return

    def start(self) -> None:
        if self.running:
            return
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> int:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None
        return self.remove()
