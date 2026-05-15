"""Build-budget cost calculator and balance report.

Every character must fit inside ``BUDGET`` (default 100) points. The cost is
the sum of:

* baseline stat costs (HP, speed, smaller hitbox, extra power slots)
* a cost per power (cast-shape cost * cooldown-factor)

The math is intentionally simple so a student can read it. Tweak the
constants at the top of this file to rebalance the whole game.
"""

from __future__ import annotations

from typing import Iterable, List

from .models import CharacterManifest, Power


# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------

BUDGET = 100.0

# Stat baselines (free) and per-step rates.
HP_BASELINE = 80.0
HP_PER_PT = 4.0           # 1pt per +4hp above baseline

SPEED_BASELINE = 180.0
SPEED_PER_PT = 4.0

SIZE_BASELINE = 32.0      # bigger than this is free
SIZE_PER_PT = 1.5         # smaller costs

EXTRA_POWER_COST = 4.0    # first power free, then 4pts each

# Cooldown -> multiplier on power cost. Short CDs make a power expensive,
# long CDs make it cheap. Clamped so it can't go to zero or infinity.
COOLDOWN_REF_MS = 1500.0
COOLDOWN_FACTOR_MIN = 0.4
COOLDOWN_FACTOR_MAX = 4.0

# Single-power warning threshold.
HOT_POWER_COST = 25.0
HIGH_DPS = 80.0


# ---------------------------------------------------------------------------
# Cost formulas (all return floats; rounding is done at the report layer)
# ---------------------------------------------------------------------------

def cost_effect(eff: dict) -> float:
    """Cost of a single effect dict (already validated by Pydantic)."""
    kind = eff.get("effect")
    if kind == "damage":
        return float(eff["amount"]) / 3.5
    if kind == "heal":
        return float(eff["amount"]) / 4.0
    if kind == "slow":
        return (1.0 - float(eff["factor"])) * 6.0 + (float(eff["durationMs"]) / 1000.0) * 2.0
    if kind == "stun":
        return (float(eff["durationMs"]) / 1000.0) * 14.0
    if kind == "knockback":
        return float(eff["strength"]) / 60.0
    if kind == "dot":
        return float(eff["dps"]) / 3.0 + (float(eff["durationMs"]) / 1000.0) * 1.5
    return 0.0


def _sum_effects(effects: Iterable[dict]) -> float:
    return sum(cost_effect(e) for e in effects)


def cost_cast(cast_dict: dict) -> float:
    """Cost of a cast shape (without the cooldown multiplier)."""
    kind = cast_dict.get("kind")
    if kind == "projectile":
        eff_sum = _sum_effects(cast_dict.get("onHit", []))
        speed = float(cast_dict["speed"])
        lifetime_s = float(cast_dict["lifetimeMs"]) / 1000.0
        radius = float(cast_dict["radius"])
        count = int(cast_dict.get("count", 1))
        range_score = (speed * lifetime_s) / 200.0 + radius / 6.0
        cost = count * (eff_sum + range_score)
        if cast_dict.get("pierce"):
            cost += 3.0
        return cost
    if kind == "area":
        eff_sum = _sum_effects(cast_dict.get("onTick", []))
        radius = float(cast_dict["radius"])
        duration_s = float(cast_dict["durationMs"]) / 1000.0
        ticks_per_s = 1000.0 / max(50.0, float(cast_dict.get("tickIntervalMs", 250)))
        return radius / 12.0 + duration_s * ticks_per_s * eff_sum * 0.5
    if kind == "melee":
        eff_sum = _sum_effects(cast_dict.get("onHit", []))
        return float(cast_dict["range"]) / 15.0 + float(cast_dict["arcDeg"]) / 45.0 + eff_sum * 1.2
    if kind == "dash":
        cost = float(cast_dict["distance"]) / 40.0
        if cast_dict.get("invulnerable"):
            cost += 8.0
        return cost
    if kind == "shield":
        return float(cast_dict["amount"]) / 8.0 + float(cast_dict["durationMs"]) / 1000.0
    if kind == "heal":
        return float(cast_dict["amount"]) / 8.0
    return 0.0


def cooldown_factor(cooldown_ms: float) -> float:
    raw = COOLDOWN_REF_MS / max(200.0, float(cooldown_ms))
    return max(COOLDOWN_FACTOR_MIN, min(COOLDOWN_FACTOR_MAX, raw))


def cost_power(power: Power) -> float:
    cast_dict = power.cast.model_dump()
    return cost_cast(cast_dict) * cooldown_factor(power.cooldownMs)


def cost_stats(m: CharacterManifest) -> dict:
    hp_cost    = max(0.0, (m.maxHealth - HP_BASELINE) / HP_PER_PT)
    speed_cost = max(0.0, (m.speed - SPEED_BASELINE) / SPEED_PER_PT)
    size_cost  = max(0.0, (SIZE_BASELINE - m.size) / SIZE_PER_PT)
    slot_cost  = max(0, len(m.powers) - 1) * EXTRA_POWER_COST
    return {
        "maxHealth": round(hp_cost, 1),
        "speed":     round(speed_cost, 1),
        "size":      round(size_cost, 1),
        "extraPowerSlots": round(slot_cost, 1),
    }


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def build_report(manifest: CharacterManifest) -> dict:
    """Return a balance report dict. Adds ``warnings`` and ``ok`` flag.

    The ``ok`` flag is True iff the total is <= ``BUDGET``. Callers (e.g.
    validation) decide whether to reject.
    """
    stats = cost_stats(manifest)
    stats_total = sum(stats.values())

    powers_breakdown: List[dict] = []
    for p in manifest.powers:
        pc = cost_power(p)
        powers_breakdown.append({
            "name": p.name,
            "key": p.key,
            "kind": p.cast.kind,
            "cooldownMs": p.cooldownMs,
            "cost": round(pc, 1),
        })
    powers_total = sum(item["cost"] for item in powers_breakdown)

    total = round(stats_total + powers_total, 1)
    warnings = _warnings(manifest, powers_breakdown)

    return {
        "budget": BUDGET,
        "total": total,
        "remaining": round(BUDGET - total, 1),
        "ok": total <= BUDGET,
        "stats": stats,
        "statsTotal": round(stats_total, 1),
        "powers": powers_breakdown,
        "powersTotal": round(powers_total, 1),
        "warnings": warnings,
        "metrics": _metrics(manifest),
    }


def _warnings(manifest: CharacterManifest, powers_breakdown: List[dict]) -> List[str]:
    out: List[str] = []
    for p, pb in zip(manifest.powers, powers_breakdown):
        cast = p.cast.model_dump()
        if pb["cost"] > HOT_POWER_COST:
            out.append(
                f"'{p.name}' is very strong ({pb['cost']} pts). Try lowering damage "
                f"or raising cooldownMs."
            )
        if cast.get("kind") in ("projectile", "melee"):
            dmg = sum(float(e["amount"]) for e in cast.get("onHit", [])
                      if e["effect"] == "damage")
            if dmg > 0:
                dps = dmg * 1000.0 / max(200.0, p.cooldownMs)
                if dps > HIGH_DPS:
                    out.append(
                        f"'{p.name}' deals ~{dps:.0f} DPS. That's spammy — "
                        f"raise cooldownMs or lower damage."
                    )
        if cast.get("kind") in ("projectile", "melee"):
            for e in cast.get("onHit", []):
                if e["effect"] == "stun" and e["durationMs"] * 3 >= p.cooldownMs:
                    out.append(
                        f"'{p.name}' can perma-stun (stun {e['durationMs']}ms, "
                        f"cooldown {p.cooldownMs}ms). Make cooldown >= 3x stun."
                    )
        if cast.get("kind") == "area":
            heal = sum(float(e["amount"]) for e in cast.get("onTick", [])
                       if e["effect"] == "heal")
            if heal > 0:
                ticks = 1000.0 / max(50.0, cast["tickIntervalMs"])
                hps = heal * ticks
                if hps > 30:
                    out.append(
                        f"'{p.name}' heals ~{hps:.0f} HP/sec. Consider lowering "
                        f"the heal amount or slowing the tick interval."
                    )
    return out


def _metrics(m: CharacterManifest) -> dict:
    """Rough class-feel metrics so students can describe their build."""
    burst = 0.0
    dps = 0.0
    cc = 0.0
    heal_score = 0.0
    mobility = m.speed / 200.0
    for p in m.powers:
        cast = p.cast.model_dump()
        if cast["kind"] in ("projectile", "melee"):
            for e in cast.get("onHit", []):
                if e["effect"] == "damage":
                    burst = max(burst, float(e["amount"]) * cast.get("count", 1))
                    dps += float(e["amount"]) * cast.get("count", 1) * 1000.0 / p.cooldownMs
                if e["effect"] == "stun":
                    cc += float(e["durationMs"]) / 100.0
                if e["effect"] == "slow":
                    cc += (1.0 - float(e["factor"])) * 5.0
        if cast["kind"] == "dash":
            mobility += cast["distance"] / 200.0
        if cast["kind"] == "heal":
            heal_score += cast["amount"]
        if cast["kind"] == "area":
            for e in cast.get("onTick", []):
                if e["effect"] == "heal":
                    heal_score += float(e["amount"]) * 5.0
    eff_health = m.maxHealth + sum(
        cast["amount"] for p in m.powers
        for cast in [p.cast.model_dump()] if cast["kind"] == "shield"
    )
    return {
        "burst": round(burst, 1),
        "dps": round(dps, 1),
        "effectiveHealth": round(eff_health, 1),
        "mobility": round(mobility, 2),
        "healing": round(heal_score, 1),
        "crowdControl": round(cc, 1),
    }
