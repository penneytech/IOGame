"""Print a useful LAN URL the teacher can share with the class."""

from __future__ import annotations

import socket


def best_lan_ip() -> str:
    # Trick: open a UDP socket "to" a public address. The OS picks the
    # interface it would route through; we never actually send anything.
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except OSError:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


def main() -> None:
    ip = best_lan_ip()
    print("Share this URL with your students:")
    print(f"  http://{ip}:8000/")
    print()
    print("If that doesn't work, try one of these instead:")
    host = socket.gethostname()
    try:
        for info in socket.getaddrinfo(host, None):
            addr = info[4][0]
            if addr.startswith("127.") or ":" in addr:
                continue
            print(f"  http://{addr}:8000/")
    except socket.gaierror:
        pass


if __name__ == "__main__":
    main()
