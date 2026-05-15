// Ice Tank — slow, tanky, controls space with a piercing slow.
//
// Build budget walkthrough (~95 / 100):
//   stats: maxHealth 240 (40), 2 extra power slots (8) → 48
//   Ice Spear ~26   Bulwark ~6   Shield Bash ~15
//
// Tradeoffs:
//   + tons of HP, slows enemies, pushes them around
//   - small movement speed, mediocre damage, big hitbox

function buildCharacter() {
  const stats = { health: 0, speed: 0 };
  for (let i = 0; i < 3; i++) {
    stats.health += 80;       // 80, 160, 240
    stats.speed = 130 + i;    // ends at 132 (below baseline = free)
  }

  const iceSpear = {
    name: "Ice Spear",
    key: "space",
    cooldownMs: 900,
    cast: {
      kind: "projectile",
      color: "cyan",
      speed: 420, radius: 6, lifetimeMs: 1500,
      count: 1, spreadDeg: 0, pierce: true,
      onHit: [
        { effect: "damage", amount: 12 },
        { effect: "slow", factor: 0.5, durationMs: 1000 },
      ],
    },
  };

  const bulwark = {
    name: "Bulwark",
    key: "e",
    cooldownMs: 8000,
    cast: { kind: "shield", color: "cyan", amount: 80, durationMs: 4000 },
  };

  const bash = {
    name: "Shield Bash",
    key: "f",
    cooldownMs: 2500,
    cast: {
      kind: "melee", color: "blue",
      range: 70, arcDeg: 90,
      onHit: [
        { effect: "damage", amount: 18 },
        { effect: "knockback", strength: 300 },
        { effect: "stun", durationMs: 400 },
      ],
    },
  };

  return {
    characterName: "Ice Tank",
    color: "cyan",
    size: 38,
    speed: stats.speed,
    maxHealth: stats.health,
    powers: [iceSpear, bulwark, bash],
  };
}
