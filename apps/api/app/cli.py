"""Operational commands.

  python -m app.cli seed                         # tiers + default config
  python -m app.cli import-investors --directory data/private/ALL_investors_merged.csv \
                                     --enrichment data/private/enriched_master.jsonl
  python -m app.cli make-admin you@example.com
  python -m app.cli honeypots --count 5           # ASP-05 synthetic records
"""

import argparse
import secrets
from pathlib import Path

from sqlalchemy import select

from .db import SessionLocal
from .models import Investor, User
from .seed import seed
from .services.dataset_import import import_directory, import_enrichment


def main() -> None:
    ap = argparse.ArgumentParser(prog="app.cli")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("seed")
    imp = sub.add_parser("import-investors")
    imp.add_argument("--directory", type=Path)
    imp.add_argument("--enrichment", type=Path)
    adm = sub.add_parser("make-admin")
    adm.add_argument("email")
    hp = sub.add_parser("honeypots")
    hp.add_argument("--count", type=int, default=5)
    a = ap.parse_args()

    with SessionLocal() as db:
        if a.cmd == "seed":
            seed(db)
            print("seeded")
        elif a.cmd == "import-investors":
            if a.directory:
                print(import_directory(db, a.directory))
            if a.enrichment:
                print(import_enrichment(db, a.enrichment))
        elif a.cmd == "make-admin":
            u = db.scalar(select(User).where(User.email == a.email.lower()))
            if not u:
                raise SystemExit("user not found — sign in once first")
            u.is_admin = True
            db.commit()
            print(f"{u.email} is now an admin")
        elif a.cmd == "honeypots":
            for _ in range(a.count):
                tag = secrets.token_hex(4)
                db.add(Investor(linkedin=f"https://linkedin.com/in/hp-{tag}", name=f"Jordan {tag[:3].upper()}ley",
                                title="Partner", company="Northfield Seed", industries=["SaaS & Enterprise"],
                                email=f"jordan.{tag}@northfieldseed.vc", is_honeypot=True, source="honeypot",
                                investor_type="vc"))
            db.commit()
            print(f"created {a.count} honeypots")


if __name__ == "__main__":
    main()
