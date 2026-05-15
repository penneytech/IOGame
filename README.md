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

## What the teacher does

1. Install Python 3.11 through 3.13.
   - On macOS, if `python` is not available, use `python3`.
2. From this folder run:

   ```bash
   pip install -r requirements.txt
   python -m server.main
   ```

   If `pip install` fails due to a Homebrew-managed environment, proxy/network restrictions, or other local package issues, use a local virtual environment instead:

   ```bash
   python3.13 -m venv .venv
   source .venv/bin/activate
   python -m pip install -r requirements.txt
   python -m server.main
   ```

   If you are using Python 3.14, install may fail because `pydantic-core` is not yet compatible with that interpreter. In that case, use Python 3.13 or earlier.

   Without the dependencies installed, the server will fail with errors such as `ModuleNotFoundError: No module named 'fastapi'`.

   The server listens on `0.0.0.0:8000` so other devices on the same LAN can
   connect.

3. Find your LAN IP. Easiest way:

   ```bash
   python scripts/print_lan_ip.py
   ```

   It prints something like `http://192.168.1.42:8000`.

4. Share that URL with the class.

## What the students do

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
  student_boilerplate/   Starter character files for students
  examples/              Two finished example characters
  tests/                 Pytest unit + integration tests
  scripts/               Helper scripts (LAN IP, smoke test)
```

## Running tests

First activate the virtual environment created earlier:

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt
pytest -q
```

## Running the smoke test

The smoke test boots the server, connects multiple fake students over
WebSockets, uploads manifests, sends movement and combat, and verifies that the
world state is broadcast.

```bash
python scripts/smoke_test.py
```

## Security note

The server **does not execute student JavaScript**. Student JS only runs in the
student's own browser to *generate* a JSON character manifest. The server then
validates that manifest against a strict schema before letting the character
into the game.
