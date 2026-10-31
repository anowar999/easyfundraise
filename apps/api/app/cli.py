"""Operational commands.

  python -m app.cli seed                         # tiers + default config
  python -m app.cli import-investors --directory data/private/ALL_investors_merged.csv \
                                     --enrichment data/private/enriched_master.jsonl
  python -m app.cli make-admin you@example.com
  python -m app.cli honeypots --count 5           # ASP-05 synthetic records
  python -m app.cli demo-investors --count 200     # synthetic investors for dev without the real dataset
"""

import argparse
import secrets
from pathlib import Path

from sqlalchemy import select

from .db import SessionLocal
from .models import Investor, User
from .seed import seed
from .services.dataset_import import import_directory, import_enrichment


def demo_investors(db, count: int) -> int:
    """Synthetic, clearly fake investors so the app is usable in dev/CI without the private dataset."""
    import random

    from .services.dataset_import import apply_enrichment
    from .services.derive import infer_timezone, investor_type

    rnd = random.Random(42)
    first = ["Alex", "Sam", "Priya", "Jordan", "Mia", "Omar", "Lena", "Kofi", "Hana", "Diego", "Ines", "Tom"]
    last = ["Rivera", "Okafor", "Lindqvist", "Patel", "Nakamura", "Dubois", "Moreau", "Haddad", "Kim", "Silva"]
    firms = ["Northwind Seed", "Bluebird Ventures", "Lattice Capital", "Harbor Angels", "Summit Health Fund",
             "Orbit VC", "Copperline Partners", "Fieldstone PE", "Kite Family Office", "Atlas Growth"]
    sectors = ["Artificial Intelligence", "Digital Health & HealthTech", "FinTech", "SaaS & Enterprise",
               "Climate & Energy", "EdTech", "Consumer Goods (CPG)", "Cybersecurity"]
    places = ["London, England, United Kingdom", "Berlin, Germany", "San Francisco, California, United States",
              "New York, New York, United States", "Singapore", "Bengaluru, Karnataka, India", "Paris, France"]
    titles = ["General Partner", "Partner", "Principal", "Angel Investor", "Managing Partner", "CFO", "Associate"]
    n = 0
    for i in range(count):
        name = f"{rnd.choice(first)} {rnd.choice(last)} (demo {i})"
        firm, loc, title = rnd.choice(firms), rnd.choice(places), rnd.choice(titles)
        inds = rnd.sample(sectors, rnd.randint(1, 3))
        inv = Investor(linkedin=f"https://linkedin.com/in/demo-investor-{i}", name=name, title=title, company=firm,
                       industries=inds, location=loc, timezone=infer_timezone(loc),
                       email=f"demo{i}@example.com", stages_src=rnd.choice(["Seed", "Pre-Seed; Seed", "Series A"]),
                       investor_type=investor_type("", title), source="demo")
        if i % 3 == 0:
            pe = "PE" in firm or "Growth" in firm or "Family" in firm
            apply_enrichment(inv, {
                "current_firm": firm, "role_at_firm": title, "identity_confidence": rnd.choice(["high", "high", "medium"]),
                "firm_type": "PE firm" if pe else rnd.choice(["seed VC", "angel (individual)", "VC fund"]),
                "focus_sectors": "; ".join(inds), "focus_stages": "growth equity" if pe else "pre-seed; seed",
                "geography_focus": loc.split(", ")[-1], "investment_thesis": f"Backs {inds[0].lower()} founders early.",
                "active_last_12mo": rnd.choice(["yes", "unknown", "unknown"]), "notable_portfolio": ["DemoCo", "SampleAI"],
                "personalization_hooks": [f"Writes about {inds[0].lower()} (demo)"], "sources": ["https://example.com"],
            })
        if db.scalar(select(Investor.id).where(Investor.linkedin == inv.linkedin)) is None:
            db.add(inv)
            n += 1
    db.commit()
    return n


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
    demo = sub.add_parser("demo-investors")
    demo.add_argument("--count", type=int, default=200)
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
        elif a.cmd == "demo-investors":
            print(f"created {demo_investors(db, a.count)} synthetic investors")


if __name__ == "__main__":
    main()
