"""20-bot free-for-all soak test (offline — no server).

Spawns 20 bots from ``server.bot_runner.BOT_MANIFESTS`` directly into a
GameState, lets them brawl until each has lost 3 lives (or until a hard
time cap), then writes a structured log to ``soak_test.log`` plus a
console summary so you can spot anything that misbehaved.

Run from the repo root with the venv:

    .venv/bin/python scripts/soak_test.py

…or activate first:

    source .venv/bin/activate
    python scripts/soak_test.py

Optional args:

    --duration N    Hard cap in seconds (default 60).
    --tick-rate N   Simulated ticks per second (default 30).
    --speedup N     Wall-clock divisor; higher = runs faster (default 8).
"""
from __future__ import annotations

import argparse
import json
import logging
import random
import sys
import time
import traceback
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from server.bot_runner import BOT_MANIFESTS, build_manifests, step_bot_ai  # noqa: E402
from server.game_state import GameState  # noqa: E402

LIVES = 3
LOG_PATH = REPO / "soak_test.log"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=float, default=60.0)
    parser.add_argument("--tick-rate", type=int, default=30)
    parser.add_argument("--speedup", type=float, default=8.0)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)

    LOG_PATH.unlink(missing_ok=True)
    logging.basicConfig(
        filename=LOG_PATH, filemode="w", level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    log = logging.getLogger("soak")

    rng = random.Random(args.seed)
    game = GameState()

    try:
        manifests = build_manifests()
    except Exception:
        log.error("MANIFEST_INVALID\n%s", traceback.format_exc())
        print("Manifest validation failed; see soak_test.log")
        return 2

    bots: dict[str, dict] = {}
    for spec, manifest in zip(BOT_MANIFESTS, manifests):
        p = game.add_player(spec["characterName"], manifest)
        bots[p.pid] = {"name": spec["characterName"], "lives_left": LIVES}
        log.info("BOT_SPAWN pid=%s name=%s powers=%s",
                 p.pid, spec["characterName"], [pw.name for pw in manifest.powers])

    fire_counts: Counter[str] = Counter()
    death_counts: Counter[str] = Counter()
    kill_counts: Counter[str] = Counter()
    error_count = 0

    dt = 1.0 / args.tick_rate
    sim_now = 0.0
    start_wall = time.monotonic()
    ticks = 0

    while True:
        for pid, info in bots.items():
            if info["lives_left"] <= 0:
                continue
            try:
                step_bot_ai(game, pid, sim_now, rng)
            except Exception:
                error_count += 1
                log.error("AI_ERROR pid=%s\n%s", pid, traceback.format_exc())

        try:
            game.step(dt, now=sim_now)
        except Exception:
            error_count += 1
            log.error("STEP_ERROR tick=%d\n%s", ticks, traceback.format_exc())

        for ev in game.events:
            kind = ev.get("kind")
            if kind == "fire":
                fire_counts[ev.get("power", "?")] += 1
            elif kind == "death":
                pid = ev.get("pid")
                by = ev.get("by")
                death_counts[bots.get(pid, {}).get("name", pid)] += 1
                if by and by != pid and by in bots:
                    kill_counts[bots[by]["name"]] += 1
                info = bots.get(pid)
                if info:
                    info["lives_left"] -= 1
                    if info["lives_left"] <= 0:
                        log.info("BOT_OUT pid=%s name=%s", pid, info["name"])
                        try:
                            game.remove_player(pid)
                        except Exception:
                            error_count += 1
                            log.error("REMOVE_ERROR pid=%s\n%s", pid,
                                      traceback.format_exc())
        game.events.clear()

        sim_now += dt
        ticks += 1
        alive_bots = sum(1 for info in bots.values() if info["lives_left"] > 0)
        if alive_bots <= 1:
            log.info("END_REASON last_bot_standing alive=%d", alive_bots)
            break
        if time.monotonic() - start_wall > args.duration:
            log.info("END_REASON time_cap ticks=%d", ticks)
            break
        if ticks % max(1, int(args.speedup)) == 0:
            time.sleep(0.001)

    survivors = [info["name"] for info in bots.values() if info["lives_left"] > 0]
    log.info("SUMMARY ticks=%d sim_seconds=%.1f errors=%d survivors=%s",
             ticks, sim_now, error_count, survivors)
    log.info("FIRES_BY_POWER %s", json.dumps(dict(fire_counts.most_common())))
    log.info("KILLS_BY_BOT %s", json.dumps(dict(kill_counts.most_common())))
    log.info("DEATHS_BY_BOT %s", json.dumps(dict(death_counts.most_common())))

    issues: list[str] = []
    all_names = {pw["name"] for spec in BOT_MANIFESTS for pw in spec["powers"]}
    never = sorted(all_names - set(fire_counts))
    if never:
        issues.append(f"Powers never fired: {never}")
    expected = {"projectile", "area", "melee", "dash", "shield", "heal"}
    seen = {pw["cast"]["kind"] for spec in BOT_MANIFESTS for pw in spec["powers"]
            if pw["name"] in fire_counts}
    if expected - seen:
        issues.append(f"Cast kinds never observed: {sorted(expected - seen)}")
    if error_count:
        issues.append(f"{error_count} tracebacks logged")

    print("=" * 64)
    print(f"Soak test: {ticks} ticks ({sim_now:.1f}s sim) in "
          f"{time.monotonic() - start_wall:.1f}s wall")
    print(f"Survivors: {survivors or 'none'}")
    print(f"Errors:    {error_count}")
    print(f"Top kills: {kill_counts.most_common(5)}")
    print(f"Top deaths: {death_counts.most_common(5)}")
    print(f"Fires per power (top 10): {fire_counts.most_common(10)}")
    print()
    if issues:
        print("ISSUES FOUND:")
        for i in issues:
            print(f"  - {i}")
        print(f"\nFull log: {LOG_PATH}")
        return 1
    print("OK — all powers fired, all cast kinds exercised, no errors.")
    print(f"Full log: {LOG_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
