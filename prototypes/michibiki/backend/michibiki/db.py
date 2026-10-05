import os
from datetime import UTC, datetime
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
    "avatar_sets", metadata,
    Column("id", String(36), primary_key=True),
    Column("client_hash", String(64), nullable=False),
    Column("provider_task_id", String, nullable=False),
    Column("status", String, nullable=False),
    Column("assets", json_type),
    Column("created_at", DateTime(timezone=True), nullable=False),
)
consultations = Table(
    "persona_consultations", metadata,
    Column("id", String(36), primary_key=True),
    Column("client_hash", String(64), nullable=False),
    Column("body", json_type, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
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
            if not conn.execute(select(migrations.c.version).where(migrations.c.version == 2)).first():
                avatar_sets.create(conn, checkfirst=True)
                consultations.create(conn, checkfirst=True)
                conn.execute(insert(migrations).values(version=2))
            if not conn.execute(select(migrations.c.version).where(migrations.c.version == 3)).first():
                video_jobs.create(conn, checkfirst=True)
                conn.execute(insert(migrations).values(version=3))
            return
        metadata.create_all(conn)
        conn.execute(insert(migrations).values(version=1))
        conn.execute(insert(migrations).values(version=2))
        conn.execute(insert(migrations).values(version=3))


def save_profile(conditions):
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert

    database = engine()
    upsert = pg_insert if database.dialect.name == "postgresql" else sqlite_insert
    statement = (
        upsert(profiles)
        .values(owner_id=DEMO_OWNER, conditions=conditions, version=1, updated_at=now())
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


def begin_mission(request, retry=True):
    from sqlalchemy.exc import IntegrityError

    payload = request.model_dump()
    payload.pop("idempotency_key")
    with engine().connect() as conn:
        old = (
            conn.execute(
                select(missions).where(
                    missions.c.owner_id == DEMO_OWNER,
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
    save_profile(payload["profile"])
    mission = {
        "id": str(uuid4()),
        "owner_id": DEMO_OWNER,
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
        return begin_mission(request, retry=False)
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


def get_mission(mission_id):
    with engine().connect() as conn:
        row = (
            conn.execute(
                select(missions).where(
                    missions.c.id == mission_id, missions.c.owner_id == DEMO_OWNER
                )
            )
            .mappings()
            .first()
        )
    return dict(row) if row else None


def save_itinerary(mission_id):
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
    record = dict(id=str(uuid4()), client_hash=client_hash, provider_task_id=provider_task_id,
                  status="generating", created_at=now())
    with engine().begin() as conn:
        conn.execute(insert(avatar_sets).values(**record))
    return record


def get_avatar_set(set_id, client_hash):
    with engine().connect() as conn:
        record = conn.execute(select(avatar_sets).where(
            avatar_sets.c.id == set_id, avatar_sets.c.client_hash == client_hash,
        )).mappings().first()
    return dict(record) if record else None


def update_avatar_set(set_id, status, assets=None):
    with engine().begin() as conn:
        conn.execute(update(avatar_sets).where(avatar_sets.c.id == set_id)
                     .values(status=status, assets=assets))


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


def find_active_video_job(client_hash, report_id):
    with engine().connect() as conn:
        record = conn.execute(select(video_jobs).where(
            video_jobs.c.client_hash == client_hash,
            video_jobs.c.report_id == report_id,
            video_jobs.c.status.in_(("queued", "generating", "rendering")),
        )).mappings().first()
    return dict(record) if record else None


def save_consultation(client_hash, body):
    record_id = str(uuid4())
    with engine().begin() as conn:
        conn.execute(insert(consultations).values(id=record_id, client_hash=client_hash,
                                                 body=body, created_at=now()))
    return record_id
