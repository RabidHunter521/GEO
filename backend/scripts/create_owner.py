"""Create (or re-issue) the owner account and print its one-time setup link.

Run once in production, inside the api container:

    railway ssh -s api -- python -m scripts.create_owner you@seenby.my "Your Name"

Open the printed link, choose a password and scan the QR code with an
authenticator app. From that moment the legacy single-admin login
(ADMIN_USERNAME / ADMIN_PASSWORD) stops working and everyone signs in with
their own account. The link is also emailed (best effort).

If the email already belongs to an owner who hasn't finished setup, a fresh
link is issued. Refuses to touch an owner who is already set up — use
"Reset" on the Team page for that.
"""
import argparse
import importlib
import pkgutil
import sys
import uuid

from app.core.constants import DEFAULT_WORKSPACE_ID
from app.core.database import SessionLocal
from app.models.user import User
from app.services import user_service
from app.services.user_invite_email import link_url, send_invite_email


def _load_all_models() -> None:
    # Run standalone, nothing else imports the model modules; relationships
    # between them only resolve once every one is registered.
    import app.models as models

    for mod in pkgutil.iter_modules(models.__path__):
        importlib.import_module(f"app.models.{mod.name}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("email")
    parser.add_argument("name")
    args = parser.parse_args(argv)
    _load_all_models()

    db = SessionLocal()
    try:
        email = user_service.normalize_email(args.email)
        existing = db.query(User).filter(User.email == email).first()
        if existing is not None:
            if user_service.is_usable(existing):
                print(f"{email} is already set up. Use Reset on the Team page instead.", file=sys.stderr)
                return 1
            if existing.role != "owner":
                print(f"{email} exists as {existing.role}; refusing to change its role here.", file=sys.stderr)
                return 1
            raw = user_service.issue_reset(db, existing)
            user = existing
        else:
            user, raw = user_service.create_invite(
                db,
                workspace_id=uuid.UUID(DEFAULT_WORKSPACE_ID),
                email=email,
                name=args.name,
                role="owner",
            )
        emailed = send_invite_email(user, raw)
        print(f"Owner setup link for {email} (one-time, 48 h):\n{link_url(raw)}")
        print("Also emailed." if emailed else "Email could not be sent; use the link above.")
        return 0
    except user_service.UserError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
