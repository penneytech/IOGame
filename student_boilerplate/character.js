// character.js  —  YOUR character.
//
// You write JavaScript that returns a character "manifest" object.
// The browser runs this; the server NEVER runs your JS.
//
// Read the Power Manual at /manual for every cast kind and effect.

// ---------- Helper builders --------------------------------------------------
//
// Notice how each helper is just a function that returns an object. Students
// can call these from buildCharacter() with different arguments.

function projectile({ name, key, color, damage, cooldownMs = 700,
                       speed = 480, radius = 6, count = 1, spreadDeg = 0,
                       pierce = false, extraEffects = [] }) {
  return {
    name, key, cooldownMs,
    cast: {
      kind: "projectile", color,
      speed, radius, lifetimeMs: 1800,
      count, spreadDeg, pierce,
      onHit: [{ effect: "damage", amount: damage }, ...extraEffects],
    },
  };
}

function shield({ name = "Shield", key = "e", color = "cyan",
                  amount = 50, durationMs = 3000, cooldownMs = 6000 } = {}) {
  return {
    name, key, cooldownMs,
    cast: { kind: "shield", color, amount, durationMs },
  };
}

// ---------- buildCharacter ---------------------------------------------------

function buildCharacter() {
  // Variables and arrays
  const flameColors = ["yellow", "orange", "red"];

  // For loop + if statement: pick the "hottest" colour.
  let hottest = flameColors[0];
  for (let i = 0; i < flameColors.length; i++) {
    if (flameColors[i] === "orange") {
      hottest = flameColors[i];
    }
  }

  // Build powers programmatically using the helpers above.
  const powers = [];
  powers.push(projectile({
    name: "Fireball", key: "space", color: hottest,
    damage: 18, cooldownMs: 700,
    extraEffects: [{ effect: "dot", dps: 6, durationMs: 1500 }], // burns!
  }));
  powers.push(shield({ name: "Mage Shield", key: "e", amount: 40, durationMs: 2500 }));

  return {
    characterName: "Fire Wizard",
    color: hottest,
    size: 28,
    speed: 220,
    maxHealth: 100,
    powers,
    // Optional: pixel-art sprites (PNG / GIF data: URIs).
    // Use the "Add custom pixel art" widget below the editor to import frames
    // from https://www.piskelapp.com/. Up to 4 frames per slot, 16 KB each.
    // sprites: {
    //   idle:   ["data:image/png;base64,..."],
    //   walk:   ["data:image/png;base64,...", "data:image/png;base64,..."],
    //   attack: ["data:image/png;base64,..."],
    //   hurt:   ["data:image/png;base64,..."],
    // },
  };
}
