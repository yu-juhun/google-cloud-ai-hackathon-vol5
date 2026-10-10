import os
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    create_engine,
    insert,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB

DEMO_OWNER = "hackathon-demo"
metadata = MetaData()
json_type = JSON().with_variant(JSONB(), "postgresql")
migrations = Table(
    "schema_migrations", metadata, Column("version", Integer, primary_key=True)
)
profiles = Table(
    "profiles",
    metadata,
    Column("owner_id", String, primary_key=True),
    Column("conditions", json_type, nullable=False),
    Column("version", Integer, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)
missions = Table(
    "missions",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("owner_id", String, ForeignKey("profiles.owner_id"), nullable=False),
    Column("idempotency_key", String, nullable=False),
    Column("input_snapshot", json_type, nullable=False),
    Column("status", String, nullable=False),
    Column("result", json_type),
    Column("error_code", String),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("completed_at", DateTime(timezone=True)),
    UniqueConstraint("owner_id", "idempotency_key"),
)
twins = Table(
    "twins",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("mission_id", String(36), ForeignKey("missions.id"), nullable=False),
    Column("ordinal", Integer, nullable=False),
    Column("role", String, nullable=False),
    Column("assignment", json_type, nullable=False),
    Column("status", String, nullable=False),
    UniqueConstraint("mission_id", "ordinal"),
)
reports = Table(
    "reports",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("twin_id", String(36), ForeignKey("twins.id"), nullable=False),
    Column("version", Integer, nullable=False),
    Column("body", json_type, nullable=False),
    UniqueConstraint("twin_id", "version"),
)
itineraries = Table(
    "itineraries",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("mission_id", String(36), ForeignKey("missions.id"), nullable=False),
    Column("version", Integer, nullable=False),
    Column("body", json_type, nullable=False),
    Column("saved_at", DateTime(timezone=True)),
    UniqueConstraint("mission_id", "version"),
)
avatar_sets = Table(
    "avatar_sets",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("client_hash", String(64), nullable=False),
    Column("provider_task_id", String, nullable=False),
    Column("status", String, nullable=False),
    Column("assets", json_type),
    Column("created_at", DateTime(timezone=True), nullable=False),
)
consultations = Table(
    "persona_consultations",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("client_hash", String(64), nullable=False),
    Column("body", json_type, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)
image_rate_windows = Table(
    "image_rate_windows",
    metadata,
    Column("model", String, primary_key=True),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("last_at", DateTime(timezone=True)),
    Column("requests", Integer, nullable=False),
)
video_jobs = Table(
    "video_jobs", metadata,
    Column("id", String(36), primary_key=True),
    Column("client_hash", String(64), nullable=False),
    Column("report_id", String(36), ForeignKey("reports.id"), nullable=False),
    Column("feedback", String, nullable=False),
    Column("style", String, nullable=False),
    Column("tone", String, nullable=False),
    Column("provider_operation_name", String),
    Column("status", String, nullable=False),  # queued / generating / rendering / ready / failed
    Column("object_name", String),
    Column("created_at", DateTime(timezone=True), nullable=False),
)
journey_video_jobs = Table(
    "journey_video_jobs", metadata,
    Column("id", String(36), primary_key=True),
    Column("client_hash", String(64), nullable=False),
    Column("mission_id", String(36), ForeignKey("missions.id"), nullable=False),
    Column("status", String, nullable=False),
    Column("body", json_type, nullable=False),
    Column("object_name", String),
    Column("progress_until", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), nullable=False),
)


def now():
    return datetime.now(UTC)


@lru_cache
def engine():
    if url := os.environ.get("DATABASE_URL"):
        return create_engine(url, pool_pre_ping=True)
    from google.cloud.sql.connector import Connector

    connector = Connector(refresh_strategy="LAZY")
    return create_engine(
        "postgresql+pg8000://",
        pool_size=2,
        max_overflow=1,
        pool_pre_ping=True,
        creator=lambda: connector.connect(
            os.environ["INSTANCE_CONNECTION_NAME"],
            "pg8000",
            user=os.environ["DB_USER"],
            password=os.environ["DB_PASSWORD"],
            db=os.environ["DB_NAME"],
        ),
    )


def migrate(db=None):
    db = db or engine()
    with db.begin() as conn:
        if db.dialect.name == "postgresql":
            from sqlalchemy import text

            conn.execute(text("SELECT pg_advisory_xact_lock(73184261)"))
        migrations.create(conn, checkfirst=True)
        if conn.execute(
            select(migrations.c.version).where(migrations.c.version == 1)
        ).first():
            if not conn.execute(
                select(migrations.c.version).where(migrations.c.version == 2)
            ).first():
                avatar_sets.create(conn, checkfirst=True)
                consultations.create(conn, checkfirst=True)
                conn.execute(insert(migrations).values(version=2))
            if not conn.execute(
                select(migrations.c.version).where(migrations.c.version == 3)
            ).first():
                image_rate_windows.create(conn, checkfirst=True)
                conn.execute(insert(migrations).values(version=3))
            if not conn.execute(select(migrations.c.version).where(migrations.c.version == 4)).first():
                video_jobs.create(conn, checkfirst=True)
                conn.execute(insert(migrations).values(version=4))
            if not conn.execute(select(migrations.c.version).where(migrations.c.version == 5)).first():
                journey_video_jobs.create(conn, checkfirst=True)
                conn.execute(insert(migrations).values(version=5))
            return
        metadata.create_all(conn)
        conn.execute(insert(migrations).values(version=1))
        conn.execute(insert(migrations).values(version=2))
        conn.execute(insert(migrations).values(version=3))
        conn.execute(insert(migrations).values(version=4))
        conn.execute(insert(migrations).values(version=5))


def find_journey_video(owner, mission_id):
    with engine().connect() as conn:
        row = conn.execute(select(journey_video_jobs).where(
            journey_video_jobs.c.client_hash == owner,
            journey_video_jobs.c.mission_id == mission_id,
        ).order_by(journey_video_jobs.c.created_at.desc()).limit(1)).mappings().first()
    return dict(row) if row else None


def begin_journey_video(owner, mission_id, body):
    """One active/completed movie per trip; serialize concurrent button presses."""
    with engine().begin() as conn:
        if conn.dialect.name == "postgresql":
            from sqlalchemy import text
            conn.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                         {"key": f"journey:{owner}:{mission_id}"})
        latest = conn.execute(select(journey_video_jobs).where(
            journey_video_jobs.c.client_hash == owner,
            journey_video_jobs.c.mission_id == mission_id,
        ).order_by(journey_video_jobs.c.created_at.desc()).limit(1)).mappings().first()
        if latest and latest["status"] != "failed":
            return dict(latest), False
        record = dict(id=str(uuid4()), client_hash=owner, mission_id=mission_id,
                      status="queued", body=body, created_at=now())
        conn.execute(insert(journey_video_jobs).values(**record))
        return record, True


def claim_journey_progress(job_id):
    with engine().begin() as conn:
        changed = conn.execute(update(journey_video_jobs).where(
            journey_video_jobs.c.id == job_id,
            (journey_video_jobs.c.progress_until.is_(None)) |
            (journey_video_jobs.c.progress_until < now()),
        ).values(progress_until=now() + timedelta(seconds=300)))
        return changed.rowcount == 1


def get_journey_video(job_id, owner):
    with engine().connect() as conn:
        row = conn.execute(select(journey_video_jobs).where(
            journey_video_jobs.c.id == job_id, journey_video_jobs.c.client_hash == owner,
        )).mappings().first()
    return dict(row) if row else None


def save_journey_video(job_id, status, body, object_name=None):
    with engine().begin() as conn:
        conn.execute(update(journey_video_jobs).where(journey_video_jobs.c.id == job_id)
                     .values(status=status, body=body, object_name=object_name))


def release_journey_progress(job_id):
    with engine().begin() as conn:
        conn.execute(update(journey_video_jobs).where(journey_video_jobs.c.id == job_id)
                     .values(progress_until=None))


def reserve_image_request(models):
    """Two requests / 61-second window per model, shared across Cloud Run instances.

    Never hold a database connection while waiting for the next window.
    """
    with engine().begin() as conn:
        if conn.dialect.name == "postgresql":
            from sqlalchemy import text

            conn.execute(text("SELECT pg_advisory_xact_lock(73184262)"))
        timestamp = now()
        waits = []
        for model in dict.fromkeys(models):
            row = (
                conn.execute(
                    select(image_rate_windows).where(
                        image_rate_windows.c.model == model
                    )
                )
                .mappings()
                .first()
            )
            recent = sorted(
                t.replace(tzinfo=UTC)
                for t in ([row["started_at"], row["last_at"]] if row else [])
                if t and t.replace(tzinfo=UTC) > timestamp - timedelta(seconds=61)
            )
            if len(recent) >= 2:
                waits.append(
                    (recent[0] + timedelta(seconds=61) - timestamp).total_seconds()
                )
                continue
            values = {
                "started_at": recent[0] if recent else timestamp,
                "last_at": timestamp if recent else None,
                "requests": len(recent) + 1,
            }
            if row:
                conn.execute(
                    update(image_rate_windows)
                    .where(image_rate_windows.c.model == model)
                    .values(**values)
                )
            else:
                conn.execute(insert(image_rate_windows).values(model=model, **values))
            return model, 0
        return None, max(0.1, min(waits))


def defer_image_model(model):
    """A 429 can include calls outside this app; cool down for a full window."""
    with engine().begin() as conn:
        if conn.dialect.name == "postgresql":
            from sqlalchemy import text

            conn.execute(text("SELECT pg_advisory_xact_lock(73184262)"))
        conn.execute(
            update(image_rate_windows)
            .where(image_rate_windows.c.model == model)
            .values(started_at=now(), last_at=now(), requests=2)
        )


def save_profile(owner_id, conditions):
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert

    database = engine()
    upsert = pg_insert if database.dialect.name == "postgresql" else sqlite_insert
    statement = (
        upsert(profiles)
        .values(owner_id=owner_id, conditions=conditions, version=1, updated_at=now())
        .on_conflict_do_update(
            index_elements=[profiles.c.owner_id],
            set_={
                "conditions": conditions,
                "version": profiles.c.version + 1,
                "updated_at": now(),
            },
        )
    )
    with database.begin() as conn:
        version = conn.execute(statement.returning(profiles.c.version)).scalar_one()
    return {"conditions": conditions, "version": version}


def get_profile(owner_id):
    with engine().connect() as conn:
        row = conn.execute(
            select(profiles.c.conditions).where(profiles.c.owner_id == owner_id)
        ).first()
    return row[0] if row else None


def begin_mission(owner_id, request, retry=True):
    from sqlalchemy.exc import IntegrityError

    payload = request.model_dump()
    payload.pop("idempotency_key")
    with engine().connect() as conn:
        old = (
            conn.execute(
                select(missions).where(
                    missions.c.owner_id == owner_id,
                    missions.c.idempotency_key == request.idempotency_key,
                )
            )
            .mappings()
            .first()
        )
    if old:
        if old["input_snapshot"] != payload:
            raise ValueError("idempotency_conflict")
        return dict(old), False
    save_profile(owner_id, payload["profile"])
    mission = {
        "id": str(uuid4()),
        "owner_id": owner_id,
        "idempotency_key": request.idempotency_key,
        "input_snapshot": payload,
        "status": "running",
        "created_at": now(),
    }
    try:
        with engine().begin() as conn:
            conn.execute(insert(missions).values(**mission))
    except IntegrityError:
        if not retry:
            raise
        return begin_mission(owner_id, request, retry=False)
    return mission, True


def finish_mission(mission_id, result):
    with engine().begin() as conn:
        for ordinal, twin in enumerate(result["twins"], 1):
            twin_id = str(uuid4())
            conn.execute(
                insert(twins).values(
                    id=twin_id,
                    mission_id=mission_id,
                    ordinal=ordinal,
                    role=twin["assignment"]["role"],
                    assignment=twin["assignment"],
                    status=twin["status"],
                )
            )
            report_id = str(uuid4())
            conn.execute(
                insert(reports).values(
                    id=report_id, twin_id=twin_id, version=1, body=twin
                )
            )
            twin["id"], twin["report_id"] = twin_id, report_id
        itinerary_id = str(uuid4())
        conn.execute(
            insert(itineraries).values(
                id=itinerary_id,
                mission_id=mission_id,
                version=1,
                body=result["itinerary"],
            )
        )
        result.update(
            mission_id=mission_id, itinerary_id=itinerary_id, version=1, persisted=True
        )
        conn.execute(
            update(missions)
            .where(missions.c.id == mission_id)
            .values(status=result["status"], result=result, completed_at=now())
        )
    return result


def fail_mission(mission_id, error_code):
    with engine().begin() as conn:
        conn.execute(
            update(missions)
            .where(missions.c.id == mission_id)
            .values(
                status="timed_out" if error_code == "timeout" else "failed",
                error_code=error_code,
                completed_at=now(),
            )
        )


def get_mission(owner_id, mission_id):
    with engine().connect() as conn:
        row = (
            conn.execute(
                select(missions).where(
                    missions.c.id == mission_id, missions.c.owner_id == owner_id
                )
            )
            .mappings()
            .first()
        )
    return dict(row) if row else None


def list_missions(owner_id, limit=20):
    with engine().connect() as conn:
        rows = conn.execute(
            select(
                missions.c.id,
                missions.c.status,
                missions.c.created_at,
                missions.c.input_snapshot,
            )
            .where(missions.c.owner_id == owner_id)
            .order_by(missions.c.created_at.desc())
            .limit(limit)
        ).mappings().all()
    return [
        {
            "id": row["id"],
            "destination": row["input_snapshot"]["trip"]["destination"],
            "date": row["input_snapshot"]["trip"]["date"],
            "status": row["status"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def save_itinerary(owner_id, mission_id):
    if not get_mission(owner_id, mission_id):
        return False
    with engine().begin() as conn:
        result = conn.execute(
            update(itineraries)
            .where(itineraries.c.mission_id == mission_id)
            .values(saved_at=now())
        )
    return result.rowcount > 0


def is_itinerary_saved(mission_id):
    with engine().connect() as conn:
        return (
            conn.execute(
                select(itineraries.c.saved_at).where(
                    itineraries.c.mission_id == mission_id
                )
            ).scalar()
            is not None
        )


def create_avatar_set(client_hash, provider_task_id):
    record = dict(
        id=str(uuid4()),
        client_hash=client_hash,
        provider_task_id=provider_task_id,
        status="generating",
        created_at=now(),
    )
    with engine().begin() as conn:
        conn.execute(insert(avatar_sets).values(**record))
    return record


def get_avatar_set(set_id, client_hash):
    with engine().connect() as conn:
        record = (
            conn.execute(
                select(avatar_sets).where(
                    avatar_sets.c.id == set_id,
                    avatar_sets.c.client_hash == client_hash,
                )
            )
            .mappings()
            .first()
        )
    return dict(record) if record else None


def update_avatar_set(set_id, status, assets=None):
    with engine().begin() as conn:
        conn.execute(
            update(avatar_sets)
            .where(avatar_sets.c.id == set_id)
            .values(status=status, assets=assets)
        )


def create_video_job(client_hash, report_id, feedback, style, tone):
    record = dict(id=str(uuid4()), client_hash=client_hash, report_id=report_id,
                  feedback=feedback, style=style, tone=tone, status="queued", created_at=now())
    with engine().begin() as conn:
        conn.execute(insert(video_jobs).values(**record))
    return record


def get_video_job(job_id, client_hash):
    with engine().connect() as conn:
        record = conn.execute(select(video_jobs).where(
            video_jobs.c.id == job_id, video_jobs.c.client_hash == client_hash,
        )).mappings().first()
    return dict(record) if record else None


def update_video_job(job_id, status, provider_operation_name=None, object_name=None):
    values = {"status": status}
    if provider_operation_name is not None:
        values["provider_operation_name"] = provider_operation_name
    if object_name is not None:
        values["object_name"] = object_name
    with engine().begin() as conn:
        conn.execute(update(video_jobs).where(video_jobs.c.id == job_id).values(**values))


def get_report(report_id, owner_id=None):
    with engine().connect() as conn:
        query = select(reports).where(reports.c.id == report_id)
        if owner_id is not None:
            query = query.join(twins, reports.c.twin_id == twins.c.id).join(
                missions, twins.c.mission_id == missions.c.id
            ).where(missions.c.owner_id == owner_id)
        record = conn.execute(query).mappings().first()
    return dict(record) if record else None


def find_latest_ready_avatar_set(client_hash):
    with engine().connect() as conn:
        record = conn.execute(select(avatar_sets).where(
            avatar_sets.c.client_hash == client_hash,
            avatar_sets.c.status == "ready",
        ).order_by(avatar_sets.c.created_at.desc()).limit(1)).mappings().first()
    return dict(record) if record else None


def find_active_video_job(client_hash, report_id):
    with engine().connect() as conn:
        record = conn.execute(select(video_jobs).where(
            video_jobs.c.client_hash == client_hash,
            video_jobs.c.report_id == report_id,
            video_jobs.c.status.in_(("queued", "generating", "rendering")),
        )).mappings().first()
    return dict(record) if record else None


def find_latest_video_job(client_hash, report_id):
    with engine().connect() as conn:
        record = conn.execute(select(video_jobs).where(
            video_jobs.c.client_hash == client_hash,
            video_jobs.c.report_id == report_id,
        ).order_by(video_jobs.c.created_at.desc()).limit(1)).mappings().first()
    return dict(record) if record else None


def get_mission_profile(report_id):
    with engine().connect() as conn:
        row = conn.execute(
            select(missions.c.input_snapshot)
            .select_from(
                reports.join(twins, reports.c.twin_id == twins.c.id)
                .join(missions, twins.c.mission_id == missions.c.id)
            )
            .where(reports.c.id == report_id)
        ).first()
    if not row:
        return None
    return row[0].get("profile")


def save_consultation(client_hash, body):
    record_id = str(uuid4())
    with engine().begin() as conn:
        conn.execute(
            insert(consultations).values(
                id=record_id, client_hash=client_hash, body=body, created_at=now()
            )
        )
    return record_id


def get_report_scene_context(report_id):
    with engine().connect() as conn:
        row = conn.execute(
            select(missions.c.input_snapshot, missions.c.result, reports.c.body)
            .select_from(reports.join(twins, reports.c.twin_id == twins.c.id)
                         .join(missions, twins.c.mission_id == missions.c.id))
            .where(reports.c.id == report_id)
        ).mappings().first()
    if not row:
        return {}
    trip = row["input_snapshot"].get("trip", {})
    assessment = (row["body"].get("assessments") or [{}])[0]
    itinerary = (row["result"] or {}).get("itinerary", {})
    stop = next((s for s in itinerary.get("stops", [])
                 if s.get("place_id") == assessment.get("place_id")), {})
    return {"destination": trip.get("destination", ""), "wish": trip.get("wish", ""),
            "activity": stop.get("activity", ""), "trip_title": itinerary.get("title", "")}


def migrate_demo_owner_data(target_client_hash):
    """One-time, manually-invoked data migration — never called from migrate() or
    any endpoint. Moves DEMO_OWNER's profile and missions to a real client_hash.
    Inserts a new profiles row before updating missions.owner_id (not the other way
    around) because missions.owner_id has a plain, non-deferrable FK to
    profiles.owner_id — updating either side first in the wrong order would violate
    that FK mid-transaction."""
    with engine().begin() as conn:
        old_profile = conn.execute(
            select(profiles).where(profiles.c.owner_id == DEMO_OWNER)
        ).mappings().first()
        if not old_profile:
            return
        target_exists = conn.execute(
            select(profiles.c.owner_id).where(profiles.c.owner_id == target_client_hash)
        ).first()
        if not target_exists:
            conn.execute(
                insert(profiles).values(
                    owner_id=target_client_hash,
                    conditions=old_profile["conditions"],
                    version=old_profile["version"],
                    updated_at=old_profile["updated_at"],
                )
            )
        conn.execute(
            update(missions)
            .where(missions.c.owner_id == DEMO_OWNER)
            .values(owner_id=target_client_hash)
        )
        # Keep the legacy profile as a recoverable record; never delete user data.
