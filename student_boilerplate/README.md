# Student boilerplate

This folder is the **starting point** for your character. You only need to edit
`character.js`. The HTML and CSS files are optional decoration shown next to
your name on the character card (eventually) — they don't affect gameplay.

## Files

- `character.js` – defines `buildCharacter()` and is the only required file.
- `character.html` – a small piece of HTML for your character card.
- `character.css` – styles for that card.
- `manifest.example.json` – a peek at what `buildCharacter()` should return.

## How it works

1. You write `buildCharacter()` in `character.js`.
2. The browser runs it (in a sandboxed iframe) and gets back a plain JS object.
3. The browser sends that object to the server as a **manifest**.
4. The server validates it and adds your character to the arena.

The server **never runs your JavaScript**. Your code only runs in your own
browser. That's how the classroom stays safe.
