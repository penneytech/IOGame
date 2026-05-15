// Fire Wizard — glass cannon with a fan of burning shots.
// Demonstrates: arrays, for loops, building one big object from many helpers.

function makeFireball(damage, count, spread) {
  return {
    name: "Fireball",
    key: "space",
    cooldownMs: 800,
    cast: {
      kind: "projectile",
      color: "orange",
      speed: 520,
      radius: 7,
      lifetimeMs: 1500,
      count: count,
      spreadDeg: spread,
      pierce: false,
      onHit: [
        { effect: "damage", amount: damage },
        { effect: "dot", dps: 8, durationMs: 1500 }, // a small burn
      ],
    },
  };
}

function buildCharacter() {
  // Pick a colour by walking an array.
  const flameColors = ["yellow", "orange", "red"];
  let pick = flameColors[0];
  for (let i = 0; i < flameColors.length; i++) {
    if (flameColors[i] === "orange") {
      pick = flameColors[i];
    }
  }

  // A second power: a slow-burning ground area you can drop on enemies.
  const inferno = {
    name: "Inferno",
    key: "q",
    cooldownMs: 5000,
    cast: {
      kind: "area",
      color: "red",
      radius: 90,
      durationMs: 2500,
      tickIntervalMs: 250,
      onTick: [
        { effect: "dot", dps: 12, durationMs: 800 },
        { effect: "slow", factor: 0.7, durationMs: 600 },
      ],
    },
  };

  return {
    characterName: "Fire Wizard",
    color: pick,
    size: 26,
    speed: 240,
    maxHealth: 80,
    powers: [
      makeFireball(20, 1, 0),
      inferno,
    ],
  };
}
