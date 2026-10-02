"""Regression: SQLite must store uuids as text, never coerce them to numbers."""
import uuid

from app.models.client import Client

# All-digit hex with one "e": a valid float literal, so NUMERIC affinity
# would store it as 1.2345678123412342e+40.
_FLOAT_LOOKING = uuid.UUID("12345678123412341234123456789e12")


def test_float_looking_uuid_round_trips_through_sqlite(db):
    db.add(Client(id=_FLOAT_LOOKING, name="Acme", website="https://acme.com", industry="dental"))
    db.commit()
    db.expire_all()

    assert db.get(Client, _FLOAT_LOOKING).id == _FLOAT_LOOKING
