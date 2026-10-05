"""One-time, manually-run data migration: moves the DEMO_OWNER profile and
missions (created before per-client ownership existed) to a real client_hash.

Usage (from backend/, with the same environment variables the deployed
backend service uses — INSTANCE_CONNECTION_NAME/DB_USER/DB_NAME/DB_PASSWORD,
or DATABASE_URL for a local database). PYTHONPATH=. is required because
plain script execution does not pick up pyproject.toml's pythonpath setting
(that setting only applies to pytest):

    PYTHONPATH=. uv run python scripts/migrate_demo_owner.py <target_client_hash>

This script is NOT called from migrate(), NOT called from any endpoint, and
NOT part of the automated test suite — it is meant to be run exactly once,
by a human, against the real database, after deploying the code from this
plan's Tasks 1-2.
"""
import sys

from michibiki import db


def main():
    if len(sys.argv) != 2:
        print("Usage: python scripts/migrate_demo_owner.py <target_client_hash>")
        sys.exit(1)
    target_client_hash = sys.argv[1]
    db.migrate_demo_owner_data(target_client_hash)
    print(f"Migrated DEMO_OWNER data to client_hash={target_client_hash}")


if __name__ == "__main__":
    main()
