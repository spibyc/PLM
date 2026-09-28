"""Administrative CLI. Usage: python -m app.cli <command> ...

  bootstrap                     create default roles (idempotent)
  create-user USERNAME "Full Name" --roles ADMIN[,QUALITY...]   (password prompted, never on the command line)
  seed-demo                     load sample development data (refuses in production)
  verify-audit                  verify the audit hash chain
  verify-files                  re-hash every stored file and report missing/modified/orphaned files
  verify-inventory              rebuild balances from the ledger and compare with the projection
  version                       print application and schema version (JSON)
"""
import argparse
import getpass
import json
import os
import sys

from app.context import Actor
from app.core.config import get_settings
from app.db import new_session
from app.services import audit, auth


def _cli_actor() -> Actor:
    from app.services.cli_actor import cli_actor

    return cli_actor()


def cmd_bootstrap(_: argparse.Namespace) -> None:
    with new_session() as db:
        created = auth.bootstrap_roles(db)
        db.commit()
    print(f"Roles created: {', '.join(created) or 'none (already present)'}")


def _read_password(env: str | None) -> str:
    if env and os.environ.get(env):
        return os.environ[env]
    p1 = getpass.getpass("Password: ")
    p2 = getpass.getpass("Repeat password: ")
    if p1 != p2:
        sys.exit("Passwords do not match")
    return p1


def cmd_create_user(a: argparse.Namespace) -> None:
    pw = _read_password(a.password_env)
    with new_session() as db:
        u = auth.create_user(db, _cli_actor(), a.username, a.full_name, a.email, pw,
                             [r.strip().upper() for r in a.roles.split(",") if r.strip()])
        db.commit()
        print(f"Created user {u.username} with roles {auth.roles_for(db, u.id)}")


def cmd_verify_audit(_: argparse.Namespace) -> None:
    with new_session() as db:
        res = audit.verify_chain(db)
    print(json.dumps(res))
    sys.exit(0 if res["ok"] else 2)


def cmd_verify_files(_: argparse.Namespace) -> None:
    from app.services import files

    with new_session() as db:
        res = files.verify_integrity(db, _cli_actor())
        db.commit()
    print(json.dumps(res, indent=2))
    sys.exit(0 if not res["findings"] else 2)


def cmd_verify_inventory(_: argparse.Namespace) -> None:
    from app.services import inventory

    with new_session() as db:
        res = inventory.verify_balances(db)
    print(json.dumps(res, indent=2))
    sys.exit(0 if res["ok"] else 2)


def cmd_version(_: argparse.Namespace) -> None:
    from app.db import current_schema_revision
    from app.version import EXPECTED_SCHEMA_REVISION

    st = get_settings()
    with new_session() as db:
        schema = current_schema_revision(db)
    print(json.dumps({"version": st.app_version, "commit": st.git_commit, "build_time": st.build_time,
                      "schema_revision": schema, "expected_schema_revision": EXPECTED_SCHEMA_REVISION}))


def cmd_seed_demo(a: argparse.Namespace) -> None:
    if get_settings().environment == "production":
        sys.exit("Refusing to load demo data when PLM_ENVIRONMENT=production")
    from app.seed import seed

    pw = _read_password(a.password_env)
    seed(pw)
    print("Demo data loaded. Users: admin, eng1, eng2, qa1, prod1, buyer1 (all share the password you supplied).")


def main() -> None:
    p = argparse.ArgumentParser(prog="plm")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("bootstrap").set_defaults(fn=cmd_bootstrap)
    c = sub.add_parser("create-user")
    c.add_argument("username")
    c.add_argument("full_name")
    c.add_argument("--email")
    c.add_argument("--roles", default="")
    c.add_argument("--password-env", help="read password from this environment variable instead of prompting")
    c.set_defaults(fn=cmd_create_user)
    sub.add_parser("verify-audit").set_defaults(fn=cmd_verify_audit)
    sub.add_parser("verify-files").set_defaults(fn=cmd_verify_files)
    sub.add_parser("verify-inventory").set_defaults(fn=cmd_verify_inventory)
    sub.add_parser("version").set_defaults(fn=cmd_version)
    s = sub.add_parser("seed-demo")
    s.add_argument("--password-env")
    s.set_defaults(fn=cmd_seed_demo)
    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
