"""Wire protocol helpers.

Messages are JSON objects with a ``type`` field. Keeping all of the type
strings in one module means the client and tests can reference them.
"""

from __future__ import annotations

# Client -> Server
C2S_JOIN = "join"
C2S_INPUT = "input"          # movement intent
C2S_FIRE = "fire"            # use a power
C2S_ROLL = "roll"            # universal dodge-roll skill move
C2S_PING = "ping"

# Server -> Client
S2C_WELCOME = "welcome"      # sent right after a successful join
S2C_JOIN_ERROR = "join_error"
S2C_PENDING = "pending"      # safe-mode: waiting for teacher approval
S2C_STATE = "state"          # periodic world snapshot
S2C_EVENT = "event"          # one-off events (hit, death, respawn, chat)
S2C_PONG = "pong"
