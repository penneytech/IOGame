# Classroom IO Game

A beginner-friendly multiplayer "IO game" framework for the classroom.
Students write a small `buildCharacter()` JavaScript function that produces a
character manifest. The manifest is sent to a Python server, validated, and the
character joins a shared top-down arena where everyone can move, shoot, and
battle.

The framework teaches:

- variables
- if statements
- for loops
- arrays
- objects
- functions
- event handling

## What the host does

1. **Open a terminal in VS Code.**

   In the menu bar: **Terminal → New Terminal** (shortcut: ``Ctrl+` `` /
   ``⌃+` ``). A panel will open at the bottom of the window. All
   the commands below get typed into that panel and run by pressing
   **Enter**. The terminal's current folder should already be this
   project folder.

2. From this folder run:

   ```bash
   pip install -r requirements.txt
   python -m server.main
   ```

   If `pip install` fails due to environment conflicts or package installation issues, use a local virtual environment instead:

   ```bash
   python3.13 -m venv .venv
   source .venv/bin/activate
   python --version
   python -m pip install --upgrade pip setuptools wheel
   python -m pip install -r requirements.txt
   python -m server.main
   ```

   If you are using Python 3.14, install may fail because `pydantic-core` is not yet compatible with that interpreter. In that case, use Python 3.13 or earlier.

   If `pip install` fails with proxy or network errors such as a tunnel connection failure or 403 response, your machine does not currently have direct access to PyPI. In that case:

   - ensure `HTTP_PROXY` / `HTTPS_PROXY` are configured correctly for your network, or
   - use a different network with internet access, or
   - download the dependency wheels on a machine with internet access and install them locally.

   Without the dependencies installed, the server will fail with errors such as `ModuleNotFoundError: No module named 'fastapi'`.

   The server listens on `0.0.0.0:8000` so other devices on the same LAN can
   connect.

2. Find your LAN IP. Easiest way:

   ```bash
   python scripts/print_lan_ip.py
   ```

   It prints something like `http://192.168.1.42:8000`.

3. Share that URL with the class.

## What the players do

Students just open the URL in their browser. They never need to clone the repo.

From the home page they pick:

- **Student Editor** – write/edit a character in the browser, test it, and join.
- **Watch the Arena** – spectate the shared game.

In the editor they edit `character.js` (a `buildCharacter()` function), click
**Run & Validate**, then **Join Game** to enter the arena.

Movement: `WASD` or arrow keys.
Fire power: `Space` (or whatever key the power defines).

## Project layout

```
classroom-io-game/
  server/                Python server (FastAPI + WebSockets)
  static/                Frontend pages and JS (no build step)
  tests/                 Pytest unit + integration tests
  scripts/               Helper scripts (LAN IP, smoke test)
```

## Security note

The server **does not execute student JavaScript**. Student JS only runs in the
student's own browser to *generate* a JSON character manifest. The server then
validates that manifest against a strict schema before letting the character
into the game.