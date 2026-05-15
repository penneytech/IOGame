// Rogue — fragile, fast, gets in and gets out.
//
// Build budget walkthrough (~95 / 100):
//   stats: speed 300 (30), small size 22 (~7), 2 extra slots (8) → 45
//   Backstab ~31   Blink ~6   Knife Fan ~15
//
// Tradeoffs:
//   + huge mobility, hard to hit, invulnerable dash
//   - low HP, single weakness moment between dashes

function buildCharacter() {
  const backstab = {
    name: "Backstab",
    key: "space",
    cooldownMs: 800,
    cast: {
      kind: "melee", color: "purple",
      range: 50, arcDeg: 60,
      onHit: [
        { effect: "damage", amount: 22 },
        { effect: "stun", durationMs: 250 },
      ],
    },
  };

  const blink = {
    name: "Blink",
    key: "f",
    cooldownMs: 3500,
    cast: {
      kind: "dash", color: "white",
      distance: 220, durationMs: 200, invulnerable: true,
    },
  };

  const knives = {
    name: "Knife Fan",
    key: "q",
    cooldownMs: 1800,
    cast: {
      kind: "projectile", color: "silver",
      speed: 560, radius: 4, lifetimeMs: 900,
      count: 3, spreadDeg: 25,
      onHit: [{ effect: "damage", amount: 10 }],
    },
  };

  return {
    characterName: "Rogue",
    color: "purple",
    size: 22,
    speed: 300,
    maxHealth: 70,
    powers: [backstab, blink, knives],
  };
}
