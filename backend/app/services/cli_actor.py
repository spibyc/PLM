import getpass
import os

from app.context import Actor


def cli_actor() -> Actor:
    try:
        who = os.environ.get("USER") or getpass.getuser()
    except Exception:
        who = "unknown"
    return Actor.system(f"cli:{who}")
