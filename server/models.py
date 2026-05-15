"""Pydantic models for character manifests and network messages.

Powers in this framework are *composed* from two layers:

1. A **cast shape** that says how the power is delivered:
   ``projectile``, ``area``, ``melee``, ``dash``, ``shield``, or ``heal``.
2. A list of **effects** (where the cast supports them) that say what happens
   to whoever is hit: ``damage``, ``slow``, ``stun``, ``knockback``, ``dot``,
   or ``heal``.

Every numeric field has a strict, inclusive range so a student can't make a
god-tier character.

The server NEVER executes student JavaScript. It only validates the data the
student's JS produced in their own browser.
"""

from __future__ import annotations

from typing import Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Limits
# ---------------------------------------------------------------------------

NAME_MAX_LEN = 24

MAX_HEALTH_RANGE = (10, 300)
SIZE_RANGE = (8, 60)
SPEED_RANGE = (40, 500)

DAMAGE_RANGE = (1, 60)
HEAL_RANGE = (1, 80)
SLOW_FACTOR_RANGE = (0.1, 0.95)        # multiplier on movement speed
STATUS_DURATION_RANGE_MS = (100, 6000)
STUN_DURATION_RANGE_MS = (100, 2000)
KNOCKBACK_RANGE = (50, 600)
DOT_DPS_RANGE = (1, 30)

COOLDOWN_RANGE_MS = (150, 15_000)
PROJECTILE_SPEED_RANGE = (50, 900)
PROJECTILE_RADIUS_RANGE = (2, 30)
PROJECTILE_LIFETIME_RANGE_MS = (200, 5000)
PROJECTILE_COUNT_RANGE = (1, 6)
PROJECTILE_SPREAD_RANGE_DEG = (0.0, 180.0)

AREA_RADIUS_RANGE = (20, 150)
AREA_DURATION_RANGE_MS = (100, 6000)
AREA_TICK_INTERVAL_RANGE_MS = (100, 1000)

DASH_DISTANCE_RANGE = (40, 400)
DASH_DURATION_RANGE_MS = (80, 600)

SHIELD_AMOUNT_RANGE = (5, 200)
SHIELD_DURATION_RANGE_MS = (200, 8000)

MELEE_RANGE_RANGE = (20, 140)
MELEE_ARC_RANGE_DEG = (30.0, 180.0)

MAX_POWERS = 4
MAX_EFFECTS_PER_CAST = 3


def _ranged(name: str, lo, hi):
    def _v(cls, v):
        if not lo <= v <= hi:
            raise ValueError(f"{name} must be between {lo} and {hi}")
        return float(v)
    return _v


# ---------------------------------------------------------------------------
# Effects
# ---------------------------------------------------------------------------

class DamageEffect(BaseModel):
    effect: Literal["damage"]
    amount: float

    _v = field_validator("amount")(_ranged("damage amount", *DAMAGE_RANGE))


class HealEffect(BaseModel):
    effect: Literal["heal"]
    amount: float

    _v = field_validator("amount")(_ranged("heal amount", *HEAL_RANGE))


class SlowEffect(BaseModel):
    effect: Literal["slow"]
    factor: float
    durationMs: float

    _vf = field_validator("factor")(_ranged("slow factor", *SLOW_FACTOR_RANGE))
    _vd = field_validator("durationMs")(
        _ranged("slow durationMs", *STATUS_DURATION_RANGE_MS)
    )


class StunEffect(BaseModel):
    effect: Literal["stun"]
    durationMs: float

    _v = field_validator("durationMs")(
        _ranged("stun durationMs", *STUN_DURATION_RANGE_MS)
    )


class KnockbackEffect(BaseModel):
    effect: Literal["knockback"]
    strength: float

    _v = field_validator("strength")(
        _ranged("knockback strength", *KNOCKBACK_RANGE)
    )


class DotEffect(BaseModel):
    effect: Literal["dot"]
    dps: float
    durationMs: float

    _vd = field_validator("dps")(_ranged("dot dps", *DOT_DPS_RANGE))
    _vt = field_validator("durationMs")(
        _ranged("dot durationMs", *STATUS_DURATION_RANGE_MS)
    )


Effect = Union[
    DamageEffect, HealEffect, SlowEffect, StunEffect, KnockbackEffect, DotEffect,
]


def _validate_effects(v: List[Effect]) -> List[Effect]:
    if not v:
        raise ValueError("at least one effect is required")
    if len(v) > MAX_EFFECTS_PER_CAST:
        raise ValueError(f"too many effects (max {MAX_EFFECTS_PER_CAST})")
    return v


# ---------------------------------------------------------------------------
# Casts
# ---------------------------------------------------------------------------

class _CastBase(BaseModel):
    color: str = Field(..., min_length=1, max_length=24)

    @field_validator("color")
    @classmethod
    def _c(cls, v: str) -> str:
        return _safe_color(v)


class ProjectileCast(_CastBase):
    kind: Literal["projectile"]
    speed: float
    radius: float
    lifetimeMs: float
    count: int = 1
    spreadDeg: float = 0.0
    pierce: bool = False
    onHit: List[Effect]

    _vs = field_validator("speed")(_ranged("projectile speed", *PROJECTILE_SPEED_RANGE))
    _vr = field_validator("radius")(_ranged("projectile radius", *PROJECTILE_RADIUS_RANGE))
    _vl = field_validator("lifetimeMs")(
        _ranged("projectile lifetimeMs", *PROJECTILE_LIFETIME_RANGE_MS)
    )

    @field_validator("count")
    @classmethod
    def _vc(cls, v: int) -> int:
        lo, hi = PROJECTILE_COUNT_RANGE
        if not lo <= v <= hi:
            raise ValueError(f"projectile count must be between {lo} and {hi}")
        return int(v)

    @field_validator("spreadDeg")
    @classmethod
    def _vsp(cls, v: float) -> float:
        lo, hi = PROJECTILE_SPREAD_RANGE_DEG
        if not lo <= v <= hi:
            raise ValueError(f"spreadDeg must be between {lo} and {hi}")
        return float(v)

    @field_validator("onHit")
    @classmethod
    def _vh(cls, v):
        return _validate_effects(v)


class AreaCast(_CastBase):
    """Persistent area-of-effect at the caster's location.

    Anyone other than the caster inside the area takes the listed effects
    each tick.
    """
    kind: Literal["area"]
    radius: float
    durationMs: float
    tickIntervalMs: float = 250
    followOwner: bool = False  # if true, the area moves with the caster
    onTick: List[Effect]

    _vr = field_validator("radius")(_ranged("area radius", *AREA_RADIUS_RANGE))
    _vd = field_validator("durationMs")(_ranged("area durationMs", *AREA_DURATION_RANGE_MS))
    _vt = field_validator("tickIntervalMs")(
        _ranged("area tickIntervalMs", *AREA_TICK_INTERVAL_RANGE_MS)
    )

    @field_validator("onTick")
    @classmethod
    def _vh(cls, v):
        return _validate_effects(v)


class MeleeCast(_CastBase):
    """A short-range cone in front of the caster, applied instantly."""
    kind: Literal["melee"]
    range: float
    arcDeg: float
    onHit: List[Effect]

    _vr = field_validator("range")(_ranged("melee range", *MELEE_RANGE_RANGE))

    @field_validator("arcDeg")
    @classmethod
    def _va(cls, v: float) -> float:
        lo, hi = MELEE_ARC_RANGE_DEG
        if not lo <= v <= hi:
            raise ValueError(f"melee arcDeg must be between {lo} and {hi}")
        return float(v)

    @field_validator("onHit")
    @classmethod
    def _vh(cls, v):
        return _validate_effects(v)


class DashCast(_CastBase):
    """A quick movement of the caster in their facing direction."""
    kind: Literal["dash"]
    distance: float
    durationMs: float
    invulnerable: bool = False

    _vd = field_validator("distance")(_ranged("dash distance", *DASH_DISTANCE_RANGE))
    _vt = field_validator("durationMs")(
        _ranged("dash durationMs", *DASH_DURATION_RANGE_MS)
    )


class ShieldCast(_CastBase):
    """Self-buff: absorb up to ``amount`` damage for ``durationMs``."""
    kind: Literal["shield"]
    amount: float
    durationMs: float

    _va = field_validator("amount")(_ranged("shield amount", *SHIELD_AMOUNT_RANGE))
    _vd = field_validator("durationMs")(
        _ranged("shield durationMs", *SHIELD_DURATION_RANGE_MS)
    )


class HealCast(_CastBase):
    """Self-buff: instantly restore ``amount`` health (clamped to maxHealth)."""
    kind: Literal["heal"]
    amount: float

    _va = field_validator("amount")(_ranged("heal amount", *HEAL_RANGE))


Cast = Union[ProjectileCast, AreaCast, MeleeCast, DashCast, ShieldCast, HealCast]


# ---------------------------------------------------------------------------
# Power & Character
# ---------------------------------------------------------------------------

class Power(BaseModel):
    name: str = Field(..., min_length=1, max_length=NAME_MAX_LEN)
    key: str = Field(..., min_length=1, max_length=12)
    cooldownMs: float
    cast: Cast = Field(..., discriminator="kind")

    _vc = field_validator("cooldownMs")(_ranged("cooldownMs", *COOLDOWN_RANGE_MS))

    @field_validator("key")
    @classmethod
    def _vk(cls, v: str) -> str:
        return v.strip().lower()


class CharacterManifest(BaseModel):
    characterName: str = Field(..., min_length=1, max_length=NAME_MAX_LEN)
    color: str = Field(..., min_length=1, max_length=24)
    size: float
    speed: float
    maxHealth: float
    powers: List[Power]
    sprites: Optional[Dict[str, List[str]]] = None

    _vsz = field_validator("size")(_ranged("size", *SIZE_RANGE))
    _vsp = field_validator("speed")(_ranged("speed", *SPEED_RANGE))
    _vhp = field_validator("maxHealth")(_ranged("maxHealth", *MAX_HEALTH_RANGE))

    @field_validator("color")
    @classmethod
    def _vcl(cls, v: str) -> str:
        return _safe_color(v)

    @field_validator("powers")
    @classmethod
    def _vp(cls, v: List[Power]) -> List[Power]:
        if not v:
            raise ValueError("character must have at least one power")
        if len(v) > MAX_POWERS:
            raise ValueError(f"too many powers (max {MAX_POWERS})")
        keys = [p.key for p in v]
        if len(set(keys)) != len(keys):
            raise ValueError("each power must use a different key")
        return v

    @field_validator("sprites")
    @classmethod
    def _vsprites(cls, v):
        if v is None:
            return None
        return _validate_sprites(v)


# ---------------------------------------------------------------------------
# Bundle + Join
# ---------------------------------------------------------------------------

BUNDLE_TEXT_MAX = 4000


class StudentBundle(BaseModel):
    html: Optional[str] = Field(default=None, max_length=BUNDLE_TEXT_MAX)
    css: Optional[str] = Field(default=None, max_length=BUNDLE_TEXT_MAX)


class JoinRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=NAME_MAX_LEN)
    manifest: CharacterManifest
    bundle: Optional[StudentBundle] = None

    @field_validator("username")
    @classmethod
    def _u(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("username cannot be blank")
        if not all(ch.isalnum() or ch in "-_ " for ch in v):
            raise ValueError("username may only use letters, digits, space, - or _")
        return v


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NAMED_COLORS = {
    "red", "orange", "yellow", "green", "blue", "purple", "pink", "white",
    "black", "gray", "grey", "cyan", "magenta", "brown", "lime", "teal",
    "gold", "silver", "navy", "maroon",
}


def _safe_color(v: str) -> str:
    s = v.strip().lower()
    if s in _NAMED_COLORS:
        return s
    if s.startswith("#") and len(s) in (4, 7) and all(
        c in "0123456789abcdef" for c in s[1:]
    ):
        return s
    raise ValueError(
        "color must be a basic name (e.g. 'red') or hex like '#ff8800'"
    )


# Sprite payload limits — keep small so the network and editor stay snappy.
SPRITE_SLOTS = {"idle", "walk", "attack", "hurt"}
SPRITE_FRAMES_MAX = 4
SPRITE_FRAME_BYTES_MAX = 16 * 1024  # 16 KB per frame
SPRITE_TOTAL_BYTES_MAX = 64 * 1024  # 64 KB across all frames
_SPRITE_DATA_PREFIXES = ("data:image/png;base64,", "data:image/gif;base64,")


def _validate_sprites(v: Dict[str, List[str]]) -> Dict[str, List[str]]:
    if not isinstance(v, dict):
        raise ValueError("sprites must be an object mapping slot -> [frames]")
    out: Dict[str, List[str]] = {}
    total = 0
    for slot, frames in v.items():
        if slot not in SPRITE_SLOTS:
            raise ValueError(
                f"sprites slot '{slot}' is not allowed; use one of "
                f"{sorted(SPRITE_SLOTS)}"
            )
        if not isinstance(frames, list) or not frames:
            raise ValueError(f"sprites['{slot}'] must be a non-empty list of frames")
        if len(frames) > SPRITE_FRAMES_MAX:
            raise ValueError(
                f"sprites['{slot}'] has too many frames "
                f"(max {SPRITE_FRAMES_MAX})"
            )
        clean: List[str] = []
        for i, frame in enumerate(frames):
            if not isinstance(frame, str):
                raise ValueError(
                    f"sprites['{slot}'][{i}] must be a data: URI string"
                )
            if not frame.startswith(_SPRITE_DATA_PREFIXES):
                raise ValueError(
                    f"sprites['{slot}'][{i}] must start with "
                    "'data:image/png;base64,' or 'data:image/gif;base64,'"
                )
            n = len(frame)
            if n > SPRITE_FRAME_BYTES_MAX:
                raise ValueError(
                    f"sprites['{slot}'][{i}] is too large "
                    f"({n} bytes; max {SPRITE_FRAME_BYTES_MAX})"
                )
            total += n
            if total > SPRITE_TOTAL_BYTES_MAX:
                raise ValueError(
                    f"sprites total payload exceeds {SPRITE_TOTAL_BYTES_MAX} bytes"
                )
            clean.append(frame)
        out[slot] = clean
    return out
