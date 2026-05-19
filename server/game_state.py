"""Authoritative game state for the classroom IO game.

The world is bigger than the viewport so the client can render an "IO-style"
camera that follows the local player.

Status effects supported (applied via Effect dicts from a power's manifest):

- ``damage``    – instant HP reduction (mitigated by an active shield)
- ``heal``      – instant HP increase (used by HealCast on the caster)
- ``slow``      – multiply the target's effective movement speed
- ``stun``      – target cannot move or fire
- ``knockback`` – instantly push the target away from the source
- ``dot``       – damage over time

Self-only buffs (shield, heal, dash) are applied directly by the cast handler.
"""

from __future__ import annotations

import math
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .models import CharacterManifest, Power

WORLD_WIDTH = 2400
WORLD_HEIGHT = 1600
RESPAWN_DELAY_S = 3.0

# Default round length, in seconds. Teacher can pass any value to start_round.
DEFAULT_ROUND_S = 120.0

# Movement feel. Higher = snappier acceleration. ~22 gives ~0.52 lerp at 30Hz,
# which feels punchy without being literal snap.
MOVE_ACCEL = 18.0
# Slower deceleration when no input is given — the player coasts/slides.
MOVE_DECEL = 4.5
# Global speed multiplier applied on top of the per-character speed.
# Bumped to give the game a snappier overall pace.
SPEED_MULT_GLOBAL = 1.20

# Universal skill moves (free for every character, not in their build budget).
STAMINA_MAX = 100.0
# Regen: full bar in ~7 seconds.
STAMINA_REGEN = STAMINA_MAX / 7.0
SPRINT_DRAIN = 30.0      # per second while sprinting
SPRINT_MIN_TO_START = 20 # can't start sprint below this
SPRINT_SPEED_MULT = 1.55
# Dodge-roll: consumes the entire stamina bar, and can only be triggered
# when stamina is full again (so ~7s between rolls).
ROLL_COST = STAMINA_MAX
ROLL_DISTANCE = 130.0     # px instant
ROLL_IFRAMES_MS = 280
ROLL_COOLDOWN_S = 0.55

# CTF tuning.
CTF_FLAG_RADIUS = 18
CTF_BASE_RADIUS = 80          # legacy (flag home visual)
CTF_CAPTURE_RADIUS = 90       # capture-zone circle radius
CTF_HOLD_SECONDS = 10.0       # carrier must stand inside own capture zone
CTF_CAPTURES_TO_WIN = 3


@dataclass
class Player:
    pid: str
    username: str
    manifest: CharacterManifest
    x: float
    y: float
    vx: float = 0.0
    vy: float = 0.0
    facing_x: float = 1.0
    facing_y: float = 0.0
    aim_x: float = 1.0
    aim_y: float = 0.0
    team: int = 0  # 0 = no team (FFA), 1 or 2 in team / ctf modes
    has_flag_team: int = 0  # which team's flag this player is carrying (0 = none)
    # Universal skill-move state (not in build budget).
    stamina: float = 100.0
    sprinting: bool = False
    roll_ready_at: float = 0.0
    health: float = 0.0
    alive: bool = True
    respawn_at: float = 0.0
    cooldowns: Dict[str, float] = field(default_factory=dict)  # power name -> ready time
    kills: int = 0
    deaths: int = 0
    # Lives system: decremented on each death; when it reaches 0 the player
    # becomes a spectator until the next round.
    lives_remaining: int = 3
    eliminated: bool = False

    # Status effects (epoch in monotonic seconds)
    slow_factor: float = 1.0
    slow_until: float = 0.0
    stun_until: float = 0.0
    invuln_until: float = 0.0
    shield_amount: float = 0.0
    shield_until: float = 0.0
    # Active DoTs as list of (dps, until, source_pid)
    dots: List[Tuple[float, float, str]] = field(default_factory=list)
    # Last damaging power name, for killcam attribution.
    last_hit_power: str = ""
    last_hit_by: str = ""

    def to_public(self, now: float) -> dict:
        return {
            "pid": self.pid,
            "username": self.username,
            "characterName": self.manifest.characterName,
            "color": self.manifest.color,
            "size": self.manifest.size,
            "x": round(self.x, 2),
            "y": round(self.y, 2),
            "facingX": round(self.facing_x, 3),
            "facingY": round(self.facing_y, 3),
            "team": self.team,
            "hasFlag": self.has_flag_team,
            "stamina": round(self.stamina, 1),
            "sprinting": self.sprinting,
            "health": round(self.health, 1),
            "maxHealth": self.manifest.maxHealth,
            "alive": self.alive,
            "kills": self.kills,
            "deaths": self.deaths,
            "livesRemaining": self.lives_remaining,
            "eliminated": self.eliminated,
            "powers": [p.model_dump() for p in self.manifest.powers],
            "sprites": self.manifest.sprites or None,
            "status": {
                "slowed": now < self.slow_until,
                "stunned": now < self.stun_until,
                "shielded": now < self.shield_until and self.shield_amount > 0,
                "shieldAmount": round(self.shield_amount, 1) if now < self.shield_until else 0,
                "invulnerable": now < self.invuln_until,
                "burning": any(now < until for _, until, _ in self.dots),
            },
        }


@dataclass
class Projectile:
    pid: str
    power_name: str
    x: float
    y: float
    vx: float
    vy: float
    radius: float
    color: str
    expires_at: float
    on_hit: List[dict]
    pierce: bool = False
    hit_pids: set = field(default_factory=set)
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])

    def to_public(self) -> dict:
        return {
            "id": self.id,
            "ownerPid": self.pid,
            "x": round(self.x, 2),
            "y": round(self.y, 2),
            "radius": self.radius,
            "color": self.color,
        }


@dataclass
class Area:
    pid: str
    power_name: str
    x: float
    y: float
    radius: float
    color: str
    expires_at: float
    next_tick_at: float
    tick_interval: float
    on_tick: List[dict]
    follow_owner: bool = False
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])

    def to_public(self) -> dict:
        return {
            "id": self.id,
            "ownerPid": self.pid,
            "x": round(self.x, 2),
            "y": round(self.y, 2),
            "radius": self.radius,
            "color": self.color,
        }


@dataclass
class MeleeFx:
    """Short-lived visual marker for a melee swing (rendered client-side)."""
    pid: str
    x: float
    y: float
    facing_x: float
    facing_y: float
    range: float
    arc_deg: float
    color: str
    expires_at: float
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])

    def to_public(self) -> dict:
        return {
            "id": self.id,
            "ownerPid": self.pid,
            "x": round(self.x, 2),
            "y": round(self.y, 2),
            "facingX": round(self.facing_x, 3),
            "facingY": round(self.facing_y, 3),
            "range": self.range,
            "arcDeg": self.arc_deg,
            "color": self.color,
        }


class GameState:
    def __init__(self, width: int = WORLD_WIDTH, height: int = WORLD_HEIGHT) -> None:
        self.width = width
        self.height = height
        self.players: Dict[str, Player] = {}
        self.projectiles: List[Projectile] = []
        self.areas: List[Area] = []
        self.melee_fx: List[MeleeFx] = []
        self.tick: int = 0
        self.events: List[dict] = []
        self._inputs: Dict[str, Tuple[float, float]] = {}
        # Per-player flag: is the sprint key currently held?
        self._sprint_held: Dict[str, bool] = {}
        # Match / round state. status is one of: 'lobby', 'running', 'ended'.
        self.match_status: str = "lobby"
        self.match_started_at: float = 0.0
        self.match_ends_at: float = 0.0
        self.match_id: int = 0
        # Last finished round's scoreboard, kept until next round starts.
        self.last_scoreboard: List[dict] = []
        # Teacher-controlled flags.
        self.safe_mode: bool = False
        # Pending joins (used when safe_mode is on). Keyed by pending id.
        self.pending_joins: Dict[str, dict] = {}
        # Game mode: 'ffa' | 'team' | 'ctf'
        self.mode: str = "ffa"
        # Team scores (used by team & ctf modes). team_caps used by ctf.
        self.team_caps: Dict[int, int] = {1: 0, 2: 0}
        # CTF flag state. Each entry: {'home_x','home_y','x','y','carrier'}.
        self.flags: Dict[int, dict] = {}
        # CTF capture zones — where a carrier must stand to score.
        # team -> {'x','y','radius'}
        self.capture_zones: Dict[int, dict] = {}
        # Per-carrier capture progress (seconds accumulated inside own zone).
        # pid -> seconds in [0, CTF_HOLD_SECONDS)
        self._capture_progress: Dict[str, float] = {}
        self._next_team: int = 1  # round-robin assignment for late joiners
        # Lives per player per round. Teacher can override in start_round.
        self.lives_per_round: int = 3

    # --- player lifecycle -------------------------------------------------

    def add_player(self, username: str, manifest: CharacterManifest) -> Player:
        pid = uuid.uuid4().hex[:10]
        team = 0
        if self.mode in ("team", "ctf"):
            # Late joiners alternate teams to keep numbers balanced.
            team = self._next_team
            self._next_team = 2 if team == 1 else 1
        spawn = self._spawn_point(team)
        p = Player(
            pid=pid,
            username=username,
            manifest=manifest,
            x=spawn[0],
            y=spawn[1],
            team=team,
            health=manifest.maxHealth,
            lives_remaining=self.lives_per_round,
        )
        self.players[pid] = p
        self.events.append({"kind": "join", "pid": pid, "username": username})
        return p

    def remove_player(self, pid: str) -> None:
        if pid in self.players:
            username = self.players[pid].username
            del self.players[pid]
            self._inputs.pop(pid, None)
            self._sprint_held.pop(pid, None)
            self.projectiles = [pr for pr in self.projectiles if pr.pid != pid]
            self.areas = [a for a in self.areas if a.pid != pid]
            self.events.append({"kind": "leave", "pid": pid, "username": username})

    def _spawn_point(self, team: int = 0) -> Tuple[float, float]:
        import random as _r
        if team in (1, 2):
            cx = self.width * (0.22 if team == 1 else 0.78)
            cy = self.height / 2
            r = min(self.width, self.height) * 0.14
            angle = _r.uniform(0.0, 2 * math.pi)
            dist = r * _r.uniform(0.2, 1.0)
            return cx + math.cos(angle) * dist, cy + math.sin(angle) * dist
        # FFA: anywhere on the map, keeping a small margin from the edges.
        margin = min(self.width, self.height) * 0.05
        return (_r.uniform(margin, self.width - margin),
                _r.uniform(margin, self.height - margin))

    # --- inputs -----------------------------------------------------------

    def set_input(self, pid: str, mx: float, my: float,
                  ax: Optional[float] = None, ay: Optional[float] = None,
                  sprint: Optional[bool] = None) -> None:
        mx = max(-1.0, min(1.0, float(mx)))
        my = max(-1.0, min(1.0, float(my)))
        length = math.hypot(mx, my)
        if length > 1.0:
            mx /= length
            my /= length
        self._inputs[pid] = (mx, my)
        if sprint is not None:
            self._sprint_held[pid] = bool(sprint)
        # Optional independent aim direction from the client (mouse cursor).
        # If not supplied, aim falls back to movement direction in _step_players.
        if ax is not None and ay is not None:
            p = self.players.get(pid)
            if p is not None:
                alen = math.hypot(float(ax), float(ay))
                if alen > 0:
                    p.aim_x = float(ax) / alen
                    p.aim_y = float(ay) / alen

    def roll(self, pid: str, now: Optional[float] = None) -> bool:
        """Universal short dodge-roll. Costs stamina, brief invulnerability."""
        if now is None:
            now = time.monotonic()
        p = self.players.get(pid)
        if p is None or not p.alive:
            return False
        if now < p.stun_until:
            return False
        if now < p.roll_ready_at:
            return False
        # Roll requires a FULL stamina bar.
        if p.stamina < STAMINA_MAX - 0.01:
            return False
        p.stamina = 0.0
        p.roll_ready_at = now + ROLL_COOLDOWN_S
        # Roll in movement direction if any, else aim direction.
        mx, my = self._inputs.get(pid, (0.0, 0.0))
        if mx == 0 and my == 0:
            mx, my = p.aim_x, p.aim_y
        length = math.hypot(mx, my) or 1.0
        mx /= length
        my /= length
        p.x += mx * ROLL_DISTANCE
        p.y += my * ROLL_DISTANCE
        self._clamp_player(p)
        p.invuln_until = max(p.invuln_until, now + ROLL_IFRAMES_MS / 1000.0)
        self.events.append({"kind": "roll", "pid": pid})
        return True

    def fire(self, pid: str, power_key: str, now: Optional[float] = None) -> bool:
        if now is None:
            now = time.monotonic()
        p = self.players.get(pid)
        if p is None or not p.alive or p.eliminated:
            return False
        if now < p.stun_until:
            return False
        power = _find_power(p.manifest, power_key)
        if power is None:
            return False
        ready_at = p.cooldowns.get(power.name, 0.0)
        if now < ready_at:
            return False
        p.cooldowns[power.name] = now + power.cooldownMs / 1000.0
        cast = power.cast
        kind = cast.kind
        if kind == "projectile":
            self._cast_projectile(p, power, cast, now)
        elif kind == "area":
            self._cast_area(p, power, cast, now)
        elif kind == "melee":
            self._cast_melee(p, power, cast, now)
        elif kind == "dash":
            self._cast_dash(p, power, cast, now)
        elif kind == "shield":
            self._cast_shield(p, power, cast, now)
        elif kind == "heal":
            self._cast_heal(p, power, cast, now)
        self.events.append({"kind": "fire", "pid": pid, "power": power.name, "castKind": kind})
        return True

    # --- cast handlers ----------------------------------------------------

    def _cast_projectile(self, p: Player, power: Power, cast, now: float) -> None:
        fx, fy = _facing(p)
        base_angle = math.atan2(fy, fx)
        n = max(1, int(cast.count))
        if n == 1:
            angles = [base_angle]
        else:
            spread = math.radians(cast.spreadDeg)
            # Spread evenly from -spread/2 to +spread/2.
            step = spread / (n - 1) if n > 1 else 0
            angles = [base_angle - spread / 2 + step * i for i in range(n)]
        on_hit = [e.model_dump() for e in cast.onHit]
        expires = now + cast.lifetimeMs / 1000.0
        for a in angles:
            vx = math.cos(a) * cast.speed
            vy = math.sin(a) * cast.speed
            self.projectiles.append(Projectile(
                pid=p.pid, power_name=power.name,
                x=p.x + math.cos(a) * (p.manifest.size / 2 + cast.radius + 1),
                y=p.y + math.sin(a) * (p.manifest.size / 2 + cast.radius + 1),
                vx=vx, vy=vy,
                radius=cast.radius, color=cast.color,
                expires_at=expires, on_hit=on_hit, pierce=bool(cast.pierce),
            ))

    def _cast_area(self, p: Player, power: Power, cast, now: float) -> None:
        self.areas.append(Area(
            pid=p.pid, power_name=power.name,
            x=p.x, y=p.y,
            radius=cast.radius, color=cast.color,
            expires_at=now + cast.durationMs / 1000.0,
            next_tick_at=now,  # tick immediately
            tick_interval=cast.tickIntervalMs / 1000.0,
            on_tick=[e.model_dump() for e in cast.onTick],
            follow_owner=bool(getattr(cast, "followOwner", False)),
        ))

    def _cast_melee(self, p: Player, power: Power, cast, now: float) -> None:
        fx, fy = _facing(p)
        on_hit = [e.model_dump() for e in cast.onHit]
        cone_cos = math.cos(math.radians(cast.arcDeg) / 2)
        for target in self.players.values():
            if target.pid == p.pid or not target.alive:
                continue
            dx = target.x - p.x
            dy = target.y - p.y
            dist = math.hypot(dx, dy)
            reach = cast.range + target.manifest.size / 2
            if dist == 0 or dist > reach:
                continue
            # Inside the cone?
            if (dx * fx + dy * fy) / dist >= cone_cos:
                self._apply_effects(target, on_hit, source=p, now=now,
                                    impact_dx=dx, impact_dy=dy,
                                    power_name=power.name)
        self.melee_fx.append(MeleeFx(
            pid=p.pid, x=p.x, y=p.y, facing_x=fx, facing_y=fy,
            range=cast.range, arc_deg=cast.arcDeg, color=cast.color,
            expires_at=now + 0.18,
        ))

    def _cast_dash(self, p: Player, power: Power, cast, now: float) -> None:
        fx, fy = _facing(p)
        p.x += fx * cast.distance
        p.y += fy * cast.distance
        self._clamp_player(p)
        if cast.invulnerable:
            p.invuln_until = max(p.invuln_until, now + cast.durationMs / 1000.0)

    def _cast_shield(self, p: Player, power: Power, cast, now: float) -> None:
        # Refresh / replace shield (don't stack indefinitely).
        p.shield_amount = float(cast.amount)
        p.shield_until = now + cast.durationMs / 1000.0

    def _cast_heal(self, p: Player, power: Power, cast, now: float) -> None:
        p.health = min(p.manifest.maxHealth, p.health + cast.amount)

    # --- effect application ----------------------------------------------

    def _apply_effects(
        self,
        target: Player,
        effects: List[dict],
        *,
        source: Player,
        now: float,
        impact_dx: float = 0.0,
        impact_dy: float = 0.0,
        power_name: str = "",
    ) -> None:
        if not target.alive:
            return
        if now < target.invuln_until:
            return
        # Friendly-fire rules in team / CTF modes: harmful effects skip teammates.
        same_team = (
            self.mode in ("team", "ctf")
            and source.pid != target.pid
            and source.team > 0
            and source.team == target.team
        )
        for e in effects:
            kind = e.get("effect")
            if same_team and kind in ("damage", "slow", "stun", "knockback", "dot"):
                continue
            if kind == "damage":
                self._damage(target, source, float(e["amount"]), now, power_name=power_name)
            elif kind == "heal":
                target.health = min(target.manifest.maxHealth,
                                    target.health + float(e["amount"]))
            elif kind == "slow":
                until = now + float(e["durationMs"]) / 1000.0
                new_factor = float(e["factor"])
                # Take the strongest (lowest factor) currently active; always refresh.
                if now < target.slow_until:
                    target.slow_factor = min(target.slow_factor, new_factor)
                    target.slow_until = max(target.slow_until, until)
                else:
                    target.slow_factor = new_factor
                    target.slow_until = until
            elif kind == "stun":
                until = now + float(e["durationMs"]) / 1000.0
                if until > target.stun_until:
                    target.stun_until = until
            elif kind == "knockback":
                strength = float(e["strength"])
                dist = math.hypot(impact_dx, impact_dy) or 1.0
                nx = impact_dx / dist
                ny = impact_dy / dist
                # Velocity impulse — MOVE_DECEL carries the push for ~0.5s of motion.
                target.vx += nx * strength * 1.6
                target.vy += ny * strength * 1.6
            elif kind == "dot":
                dps = float(e["dps"])
                until = now + float(e["durationMs"]) / 1000.0
                # Refresh-not-stack: same source overwrites its previous DoT timer.
                replaced = False
                for i, (d, u, src) in enumerate(target.dots):
                    if src == source.pid:
                        # Keep the stronger DPS; always refresh until forward.
                        target.dots[i] = (max(d, dps), max(u, until), src)
                        replaced = True
                        break
                if not replaced:
                    target.dots.append((dps, until, source.pid))
            if not target.alive:
                break

    def _damage(self, target: Player, source: Player, amount: float, now: float,
                *, power_name: str = "") -> None:
        if now < target.shield_until and target.shield_amount > 0:
            absorbed = min(target.shield_amount, amount)
            target.shield_amount -= absorbed
            amount -= absorbed
            if target.shield_amount <= 0:
                target.shield_amount = 0
                target.shield_until = 0
        if amount <= 0:
            return
        target.health -= amount
        if source.pid != target.pid:
            target.last_hit_by = source.pid
            if power_name:
                target.last_hit_power = power_name
        self.events.append({
            "kind": "hit", "from": source.pid, "to": target.pid, "damage": amount,
        })
        if target.health <= 0:
            target.health = 0
            target.alive = False
            target.deaths += 1
            target.lives_remaining = max(0, target.lives_remaining - 1)
            if target.lives_remaining <= 0:
                target.eliminated = True
                # Spectators don't respawn until next round.
                target.respawn_at = float("inf")
            else:
                target.respawn_at = now + RESPAWN_DELAY_S
            # Clear status when dying.
            target.dots.clear()
            target.shield_amount = 0
            if source.pid != target.pid and source.pid in self.players:
                source.kills += 1
            # CTF: dropped flag returns home.
            if self.mode == "ctf" and target.has_flag_team:
                self._return_flag(target.has_flag_team)
                target.has_flag_team = 0
            self.events.append({
                "kind": "death", "pid": target.pid, "by": source.pid,
                "byName": source.username,
                "byPower": target.last_hit_power or power_name or "",
                "livesRemaining": target.lives_remaining,
                "eliminated": target.eliminated,
            })

    # --- simulation -------------------------------------------------------

    def step(self, dt: float, now: Optional[float] = None) -> None:
        if now is None:
            now = time.monotonic()
        self.tick += 1
        self._last_dt = dt
        self._step_dots(dt, now)
        self._step_players(dt, now)
        self._step_projectiles(dt, now)
        self._step_areas(dt, now)
        self._step_melee_fx(now)
        self._step_respawns(now)

    def _effective_speed(self, p: Player, now: float) -> float:
        if now < p.stun_until:
            return 0.0
        base = p.manifest.speed * SPEED_MULT_GLOBAL
        if now < p.slow_until:
            base = p.manifest.speed * p.slow_factor * SPEED_MULT_GLOBAL
        # CTF: flag carriers get a small speed bonus so making it home is
        # actually achievable through enemy fire.
        if self.mode == "ctf" and p.has_flag_team:
            base *= 1.20
        return base

    def _step_players(self, dt: float, now: float) -> None:
        # Frame-rate-independent lerp coefficients. We use a faster ramp when
        # the player is actively pushing a direction (ease-in) and a slower
        # one when no input is held (coast / slide — ease-out).
        accel_in = 1.0 - math.exp(-dt * MOVE_ACCEL)
        accel_out = 1.0 - math.exp(-dt * MOVE_DECEL)
        for pid, p in self.players.items():
            if not p.alive:
                p.vx = p.vy = 0
                p.sprinting = False
                # Dead players still regen stamina slowly.
                p.stamina = min(STAMINA_MAX, p.stamina + STAMINA_REGEN * 0.5 * dt)
                continue
            mx, my = self._inputs.get(pid, (0.0, 0.0))
            sprint_held = self._sprint_held.get(pid, False)
            # Sprint state machine: must be moving + above min-stamina to start.
            moving = (mx != 0 or my != 0)
            if sprint_held and moving and (p.sprinting or p.stamina >= SPRINT_MIN_TO_START):
                p.sprinting = True
            else:
                p.sprinting = False
            if p.sprinting:
                p.stamina = max(0.0, p.stamina - SPRINT_DRAIN * dt)
                if p.stamina <= 0.0:
                    p.sprinting = False
            else:
                p.stamina = min(STAMINA_MAX, p.stamina + STAMINA_REGEN * dt)
            speed = self._effective_speed(p, now)
            if p.sprinting:
                speed *= SPRINT_SPEED_MULT
            target_vx = mx * speed
            target_vy = my * speed
            k = accel_in if (mx != 0 or my != 0) else accel_out
            p.vx += (target_vx - p.vx) * k
            p.vy += (target_vy - p.vy) * k
            p.x += p.vx * dt
            p.y += p.vy * dt
            # Facing follows mouse aim when available, else movement direction.
            if p.aim_x != 0 or p.aim_y != 0:
                p.facing_x = p.aim_x
                p.facing_y = p.aim_y
            elif mx != 0 or my != 0:
                p.facing_x = mx
                p.facing_y = my
            self._clamp_player(p)
        # CTF: keep flag attached to its carrier, handle base captures.
        if self.mode == "ctf":
            self._step_ctf(now)

    def _clamp_player(self, p: Player) -> None:
        r = p.manifest.size / 2
        p.x = max(r, min(self.width - r, p.x))
        p.y = max(r, min(self.height - r, p.y))

    def _step_projectiles(self, dt: float, now: float) -> None:
        survivors: List[Projectile] = []
        for pr in self.projectiles:
            pr.x += pr.vx * dt
            pr.y += pr.vy * dt
            if (
                now >= pr.expires_at
                or pr.x < 0 or pr.x > self.width
                or pr.y < 0 or pr.y > self.height
            ):
                continue
            consumed = False
            for target in self.players.values():
                if target.pid == pr.pid or not target.alive:
                    continue
                if target.pid in pr.hit_pids:
                    continue
                dx = target.x - pr.x
                dy = target.y - pr.y
                rr = (target.manifest.size / 2 + pr.radius)
                if dx * dx + dy * dy <= rr * rr:
                    source = self.players.get(pr.pid)
                    if source is not None:
                        self._apply_effects(target, pr.on_hit, source=source, now=now,
                                            impact_dx=pr.vx, impact_dy=pr.vy,
                                            power_name=pr.power_name)
                    pr.hit_pids.add(target.pid)
                    if not pr.pierce:
                        consumed = True
                        break
            if not consumed:
                survivors.append(pr)
        self.projectiles = survivors

    def _step_areas(self, dt: float, now: float) -> None:
        survivors: List[Area] = []
        for a in self.areas:
            if now >= a.expires_at:
                continue
            survivors.append(a)
            # Areas that follow their caster track the player position each tick.
            if a.follow_owner:
                owner = self.players.get(a.pid)
                if owner is not None and owner.alive:
                    a.x, a.y = owner.x, owner.y
            if now >= a.next_tick_at:
                a.next_tick_at = now + a.tick_interval
                source = self.players.get(a.pid)
                if source is None:
                    continue
                for target in self.players.values():
                    if target.pid == a.pid or not target.alive:
                        continue
                    dx = target.x - a.x
                    dy = target.y - a.y
                    rr = (target.manifest.size / 2 + a.radius)
                    if dx * dx + dy * dy <= rr * rr:
                        self._apply_effects(target, a.on_tick, source=source, now=now,
                                            impact_dx=dx, impact_dy=dy,
                                            power_name=a.power_name)
        self.areas = survivors

    def _step_melee_fx(self, now: float) -> None:
        self.melee_fx = [m for m in self.melee_fx if now < m.expires_at]

    def _step_dots(self, dt: float, now: float) -> None:
        for p in self.players.values():
            if not p.alive or not p.dots:
                continue
            keep: List[Tuple[float, float, str]] = []
            for dps, until, src in p.dots:
                if now >= until:
                    continue
                # Apply this tick's burn.
                src_player = self.players.get(src) or p  # if attacker left, self-credit
                self._damage(p, src_player, dps * dt, now)
                if p.alive:
                    keep.append((dps, until, src))
            p.dots = keep

    def _step_respawns(self, now: float) -> None:
        for p in self.players.values():
            if p.eliminated:
                continue
            if not p.alive and now >= p.respawn_at:
                p.alive = True
                p.health = p.manifest.maxHealth
                p.slow_until = p.stun_until = p.shield_until = p.invuln_until = 0
                p.shield_amount = 0
                p.dots.clear()
                # CTF: drop a carried flag on death (returns home immediately).
                if self.mode == "ctf" and p.has_flag_team:
                    self._return_flag(p.has_flag_team)
                    p.has_flag_team = 0
                p.stamina = STAMINA_MAX
                p.sprinting = False
                p.roll_ready_at = 0.0
                spawn = self._spawn_point(p.team)
                p.x, p.y = spawn
                self.events.append({"kind": "respawn", "pid": p.pid})

    # --- snapshots --------------------------------------------------------

    def snapshot(self, now: Optional[float] = None) -> dict:
        if now is None:
            now = time.monotonic()
        return {
            "tick": self.tick,
            "width": self.width,
            "height": self.height,
            "players": [pl.to_public(now) for pl in self.players.values()],
            "projectiles": [pr.to_public() for pr in self.projectiles],
            "areas": [a.to_public() for a in self.areas],
            "meleeFx": [m.to_public() for m in self.melee_fx],
            "match": self._match_public(now),
            "mode": self.mode,
            "flags": self._flags_public() if self.mode == "ctf" else [],
            "captureZones": self._capture_zones_public() if self.mode == "ctf" else [],
            "teamScores": self.team_caps if self.mode in ("team", "ctf") else {},
        }

    def _match_public(self, now: float) -> dict:
        remaining = max(0.0, self.match_ends_at - now) if self.match_status == "running" else 0.0
        # Auto-end when time runs out.
        if self.match_status == "running" and remaining <= 0.0:
            self.end_round()
            remaining = 0.0
        return {
            "status": self.match_status,
            "id": self.match_id,
            "mode": self.mode,
            "remaining": round(remaining, 1),
            "safeMode": self.safe_mode,
            "scoreboard": self.scoreboard(),
            "lastScoreboard": self.last_scoreboard,
            "pendingCount": len(self.pending_joins),
            "teamScores": self.team_caps if self.mode in ("team", "ctf") else {},
        }

    # --- match / round controls ------------------------------------------

    def start_round(self, duration_s: float = DEFAULT_ROUND_S,
                    mode: Optional[str] = None,
                    lives: Optional[int] = None,
                    now: Optional[float] = None) -> None:
        if now is None:
            now = time.monotonic()
        if mode is not None:
            mode = mode.lower()
            if mode not in ("ffa", "team", "ctf"):
                raise ValueError(f"unknown mode: {mode}")
            self.mode = mode
        if lives is not None:
            self.lives_per_round = max(1, int(lives))
        self.match_id += 1
        self.match_status = "running"
        self.match_started_at = now
        self.match_ends_at = now + max(10.0, float(duration_s))
        self.last_scoreboard = []
        self.team_caps = {1: 0, 2: 0}
        # Assign / reset teams up front for team and ctf modes.
        if self.mode in ("team", "ctf"):
            pids = list(self.players.keys())
            # Stable shuffle by hashing pid + match_id so it's reproducible per round.
            pids.sort(key=lambda x: (hash((x, self.match_id))))
            for i, pid in enumerate(pids):
                self.players[pid].team = 1 if i % 2 == 0 else 2
            self._next_team = 1
        else:
            for p in self.players.values():
                p.team = 0
        # CTF: place flags at each team's base.
        if self.mode == "ctf":
            self.flags = {
                1: {"home_x": self.width * 0.08, "home_y": self.height / 2,
                    "x": self.width * 0.08, "y": self.height / 2, "carrier": None},
                2: {"home_x": self.width * 0.92, "home_y": self.height / 2,
                    "x": self.width * 0.92, "y": self.height / 2, "carrier": None},
            }
            # Capture zones: same point as own flag base. To score, carrier
            # of enemy flag must stand inside their own team's zone for
            # CTF_HOLD_SECONDS cumulative seconds.
            self.capture_zones = {
                1: {"x": self.width * 0.08, "y": self.height / 2, "radius": CTF_CAPTURE_RADIUS},
                2: {"x": self.width * 0.92, "y": self.height / 2, "radius": CTF_CAPTURE_RADIUS},
            }
            self._capture_progress = {}
        else:
            self.flags = {}
            self.capture_zones = {}
            self._capture_progress = {}
        for p in self.players.values():
            p.kills = 0
            p.deaths = 0
            p.lives_remaining = self.lives_per_round
            p.eliminated = False
            p.health = p.manifest.maxHealth
            p.alive = True
            p.respawn_at = 0
            p.dots.clear()
            p.shield_amount = 0
            p.cooldowns.clear()
            p.has_flag_team = 0
            p.stamina = STAMINA_MAX
            p.sprinting = False
            p.roll_ready_at = 0.0
            spawn = self._spawn_point(p.team)
            p.x, p.y = spawn
        self.projectiles.clear()
        self.areas.clear()
        self.melee_fx.clear()
        self.events.append({"kind": "round_start", "id": self.match_id})

    def end_round(self) -> None:
        if self.match_status != "running":
            return
        self.last_scoreboard = self.scoreboard()
        self.match_status = "ended"
        self.events.append({
            "kind": "round_end", "id": self.match_id,
            "scoreboard": self.last_scoreboard,
        })

    def reset_arena(self) -> None:
        """Wipe live entities and zero scores. Players keep their characters."""
        self.projectiles.clear()
        self.areas.clear()
        self.melee_fx.clear()
        for p in self.players.values():
            p.kills = 0
            p.deaths = 0
            p.lives_remaining = self.lives_per_round
            p.eliminated = False
            p.health = p.manifest.maxHealth
            p.alive = True
            p.respawn_at = 0
            p.cooldowns.clear()
            p.dots.clear()
            p.shield_amount = 0
        self.match_status = "lobby"
        self.events.append({"kind": "reset"})

    def clear_projectiles(self) -> None:
        self.projectiles.clear()
        self.areas.clear()
        self.melee_fx.clear()

    def kick(self, pid: str) -> bool:
        if pid not in self.players:
            return False
        self.events.append({"kind": "kicked", "pid": pid})
        self.remove_player(pid)
        return True

    def scoreboard(self) -> List[dict]:
        rows = [
            {
                "pid": p.pid,
                "username": p.username,
                "characterName": p.manifest.characterName,
                "color": p.manifest.color,
                "team": p.team,
                "kills": p.kills,
                "deaths": p.deaths,
                "score": p.kills - p.deaths,
            }
            for p in self.players.values()
        ]
        rows.sort(key=lambda r: (-r["score"], -r["kills"], r["username"]))
        return rows

    def drain_events(self) -> List[dict]:
        out = self.events
        self.events = []
        return out

    # --- CTF helpers ------------------------------------------------------

    def _flags_public(self) -> List[dict]:
        out = []
        for team, f in self.flags.items():
            out.append({
                "team": team,
                "x": round(f["x"], 2),
                "y": round(f["y"], 2),
                "homeX": round(f["home_x"], 2),
                "homeY": round(f["home_y"], 2),
                "carrier": f["carrier"],
            })
        return out

    def _capture_zones_public(self) -> List[dict]:
        out = []
        for team, z in self.capture_zones.items():
            # Find carrier of the *enemy* flag for this team — they're the one
            # who can score by standing here. Report their progress.
            holding_pid = None
            progress = 0.0
            other_team = 2 if team == 1 else 1
            other_flag = self.flags.get(other_team)
            if other_flag and other_flag.get("carrier"):
                cid = other_flag["carrier"]
                p = self.players.get(cid)
                if p and p.alive and p.team == team:
                    holding_pid = cid
                    progress = self._capture_progress.get(cid, 0.0)
            out.append({
                "team": team,
                "x": round(z["x"], 2),
                "y": round(z["y"], 2),
                "radius": z["radius"],
                "holdSeconds": CTF_HOLD_SECONDS,
                "carrierPid": holding_pid,
                "progress": round(progress, 2),
            })
        return out

    def _return_flag(self, team: int) -> None:
        f = self.flags.get(team)
        if f is None:
            return
        # Clear any in-progress hold for the previous carrier.
        prev = f.get("carrier")
        if prev is not None:
            self._capture_progress.pop(prev, None)
        f["x"] = f["home_x"]
        f["y"] = f["home_y"]
        f["carrier"] = None

    def _step_ctf(self, now: float) -> None:
        if not self.flags:
            return
        # 1) Move carried flags to follow their carrier.
        for team, f in self.flags.items():
            cid = f["carrier"]
            if cid is not None:
                p = self.players.get(cid)
                if p is None or not p.alive:
                    self._return_flag(team)
                    if p is not None:
                        p.has_flag_team = 0
                else:
                    f["x"] = p.x
                    f["y"] = p.y
        # 2) Pickups.
        for p in self.players.values():
            if not p.alive or p.team not in (1, 2):
                continue
            for team, f in self.flags.items():
                if team == p.team or f["carrier"] is not None:
                    continue
                dx = p.x - f["x"]
                dy = p.y - f["y"]
                rr = p.manifest.size / 2 + CTF_FLAG_RADIUS
                if dx * dx + dy * dy <= rr * rr:
                    f["carrier"] = p.pid
                    p.has_flag_team = team
                    self._capture_progress[p.pid] = 0.0
                    self.events.append({
                        "kind": "flag_pickup", "pid": p.pid, "team": team,
                    })
        # 3) Capture progress: carrier must stand inside their OWN team's zone.
        # Tick rate is fixed (game uses _tick_dt for sim). We can compute dt
        # from the previous snapshot time; simpler: assume 1/tick_hz. The
        # game step calls this once per tick from _step_movement.
        dt = getattr(self, "_last_dt", 1.0 / 30.0)
        scored: List[Tuple[str, int, int]] = []  # (pid, by_team, captured_team)
        for team, zone in self.capture_zones.items():
            other_team = 2 if team == 1 else 1
            f = self.flags.get(other_team)
            if not f or f.get("carrier") is None:
                continue
            cid = f["carrier"]
            p = self.players.get(cid)
            if p is None or not p.alive or p.team != team:
                continue
            dx = p.x - zone["x"]
            dy = p.y - zone["y"]
            in_zone = (dx * dx + dy * dy) <= (zone["radius"] * zone["radius"])
            if in_zone:
                cur = self._capture_progress.get(cid, 0.0) + dt
                if cur >= CTF_HOLD_SECONDS:
                    scored.append((cid, team, other_team))
                    self._capture_progress[cid] = 0.0
                else:
                    self._capture_progress[cid] = cur
            else:
                # Reset on leaving the zone — keeps the rule simple.
                if self._capture_progress.get(cid, 0.0) > 0.0:
                    self._capture_progress[cid] = 0.0
        for cid, by_team, captured_team in scored:
            self.team_caps[by_team] = self.team_caps.get(by_team, 0) + 1
            self._return_flag(captured_team)
            p = self.players.get(cid)
            if p is not None:
                p.has_flag_team = 0
            self.events.append({
                "kind": "flag_capture", "pid": cid,
                "team": by_team, "captured": captured_team,
                "score": self.team_caps[by_team],
            })
            if self.team_caps[by_team] >= CTF_CAPTURES_TO_WIN:
                self.end_round()
                return


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_power(manifest: CharacterManifest, key: str) -> Optional[Power]:
    key = (key or "").strip().lower()
    for p in manifest.powers:
        if p.key == key:
            return p
    return None


def _facing(p: Player) -> Tuple[float, float]:
    fx, fy = p.facing_x, p.facing_y
    if fx == 0 and fy == 0:
        return 1.0, 0.0
    length = math.hypot(fx, fy) or 1.0
    return fx / length, fy / length
