"""Build a throwaway database for the client-view accessibility check.

Creates the schema straight from the models (the Alembic chain cannot build
an empty database: its first revision assumes tables that predate it), seeds
the Medilink demo client, and prints that client's share token.

Run from backend/ against a THROWAWAY database only:
    DATABASE_URL=postgresql://.../seenby_a11y python -m scripts.a11y_bootstrap
"""
import importlib
import pkgutil
import sys

from app.core.config import settings


def main() -> None:
    if "railway" in settings.DATABASE_URL or "supabase" in settings.DATABASE_URL:
        sys.exit("Refusing to run: DATABASE_URL looks like a real database.")

    from app.core.database import SessionLocal, engine
    from app.models.base import Base
    import app.models as models

    for mod in pkgutil.iter_modules(models.__path__):
        importlib.import_module(f"app.models.{mod.name}")
    Base.metadata.create_all(engine)

    from scripts import seed_medilink_premium

    seed_medilink_premium.main()

    from app.models.client import Client

    db = SessionLocal()
    try:
        client = db.query(Client).filter(Client.share_token.isnot(None)).first()
        if client is None:
            sys.exit("Seed produced no client with a share link.")
        print(f"VIEW_TOKEN={client.share_token}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
