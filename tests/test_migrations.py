"""Database migrations: fresh installs, upgrades, downgrades and model/schema consistency.

Every test runs against a new, empty database. SQLite always runs. Set
TRAYUP_MIGRATION_DATABASE_URL to also run the full cycle on PostgreSQL, for example:

    TRAYUP_MIGRATION_DATABASE_URL=postgresql+psycopg://user:pass@localhost/trayup_migrations pytest tests/test_migrations.py

That database is wiped before each test, so do not point it at real data.

The migration tools run in subprocesses, as they do in deployment (`flask --app run db upgrade`),
so the tests use the same configuration path as production.
"""
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.schema import MetaData

import app.models as registered_models  # importing registers every model on db.metadata
from app.extensions import db

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = ROOT / "migrations"
POSTGRES_URL = os.getenv("TRAYUP_MIGRATION_DATABASE_URL", "").strip()

# The revision before stock reservations were added, and the last one before refunds.
BEFORE_STOCK_RESERVATIONS = "99d21c7d2218"
BEFORE_REFUNDS = "e7a1b2c3d4f5"


def _script():
    return ScriptDirectory(str(MIGRATIONS_DIR))


def _head():
    (head,) = _script().get_heads()
    return head


def _run_flask(args, url):
    env = os.environ.copy()
    env["DATABASE_URL"] = url
    completed = subprocess.run(
        [sys.executable, "-m", "flask", "--app", "run", *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert completed.returncode == 0, f"flask {' '.join(args)} failed:\n{completed.stdout}\n{completed.stderr}"
    return completed.stdout


def _run_python(script, url):
    env = os.environ.copy()
    env["DATABASE_URL"] = url
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert completed.returncode == 0, f"migration script failed:\n{completed.stdout}\n{completed.stderr}"
    return completed.stdout


def _reset(url):
    """Make the database completely empty, including the alembic_version table."""
    engine = create_engine(url)
    try:
        metadata = MetaData()
        metadata.reflect(bind=engine)
        metadata.drop_all(bind=engine)
    finally:
        engine.dispose()


def _current_revision(url):
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            if not inspect(conn).has_table("alembic_version"):
                return None
            return conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    finally:
        engine.dispose()


def _table_names(url):
    engine = create_engine(url)
    try:
        return set(inspect(engine).get_table_names()) - {"alembic_version"}
    finally:
        engine.dispose()


def _column_names(url, table):
    engine = create_engine(url)
    try:
        return {column["name"] for column in inspect(engine).get_columns(table)}
    finally:
        engine.dispose()


def _schema_drift(url):
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            context = MigrationContext.configure(conn, opts={"compare_type": True})
            return compare_metadata(context, db.metadata)
    finally:
        engine.dispose()


def _model_tables():
    assert registered_models.__all__  # the models package is what populates db.metadata
    return set(db.metadata.tables)


@pytest.fixture(params=["sqlite", pytest.param("postgres", marks=pytest.mark.skipif(
    not POSTGRES_URL, reason="set TRAYUP_MIGRATION_DATABASE_URL to run migrations against PostgreSQL",
))])
def database_url(request, tmp_path):
    if request.param == "sqlite":
        url = f"sqlite:///{tmp_path / 'migrations.db'}"
    else:
        url = POSTGRES_URL
    _reset(url)
    yield url
    _reset(url)


# ---------- History integrity ----------

def test_migration_history_is_a_single_linear_chain():
    script = _script()

    assert len(script.get_heads()) == 1
    assert len(script.get_bases()) == 1
    # Walking from head to base visits every revision exactly once.
    walked = [rev.revision for rev in script.walk_revisions()]
    assert len(walked) == len(set(walked))


def test_every_revision_has_a_docstring_describing_it():
    """Revision messages show up in `flask db history`. An empty one is hard to review later."""
    for rev in _script().walk_revisions():
        assert rev.doc and rev.doc.strip(), rev.revision


# ---------- Fresh installation ----------

def test_fresh_install_reaches_head_and_matches_the_models(database_url):
    _run_flask(["db", "upgrade"], database_url)

    assert _current_revision(database_url) == _head()
    assert _table_names(database_url) == _model_tables()
    assert _schema_drift(database_url) == []


def test_upgrade_is_idempotent_at_head(database_url):
    _run_flask(["db", "upgrade"], database_url)
    _run_flask(["db", "upgrade"], database_url)

    assert _current_revision(database_url) == _head()
    assert _schema_drift(database_url) == []


# ---------- Downgrades and re-upgrades ----------

def test_every_revision_downgrades_and_upgrades_again(database_url):
    _run_flask(["db", "upgrade"], database_url)

    # Walk down one revision at a time, then back up. The script records each step.
    output = _run_python(
        f"""
import json
from alembic.script import ScriptDirectory
from flask_migrate import downgrade, upgrade
from app import create_app

app = create_app("development")
script = ScriptDirectory({str(MIGRATIONS_DIR)!r})
revisions = list(script.walk_revisions())  # newest first
steps = []
with app.app_context():
    for rev in revisions:
        target = rev.down_revision or "base"
        downgrade(directory={str(MIGRATIONS_DIR)!r}, revision=target)
        steps.append(["down", rev.revision])
    for rev in reversed(revisions):
        upgrade(directory={str(MIGRATIONS_DIR)!r}, revision=rev.revision)
        steps.append(["up", rev.revision])
print("STEPS " + json.dumps(steps))
""",
        database_url,
    )
    steps = json.loads(next(line for line in output.splitlines() if line.startswith("STEPS ")).removeprefix("STEPS "))

    revisions = [rev.revision for rev in _script().walk_revisions()]
    assert steps[: len(revisions)] == [["down", rev] for rev in revisions]
    assert steps[len(revisions):] == [["up", rev] for rev in reversed(revisions)]
    assert _current_revision(database_url) == _head()
    assert _schema_drift(database_url) == []


def test_full_downgrade_leaves_no_application_tables(database_url):
    _run_flask(["db", "upgrade"], database_url)

    _run_flask(["db", "downgrade", "base"], database_url)

    assert _current_revision(database_url) is None
    assert _table_names(database_url) == set()


def test_downgrading_one_revision_removes_only_its_schema(database_url):
    _run_flask(["db", "upgrade"], database_url)

    _run_flask(["db", "downgrade", BEFORE_REFUNDS], database_url)

    assert "refunds" not in _table_names(database_url)
    assert "stock_reservations" in _table_names(database_url)
    assert "reserved_quantity" in _column_names(database_url, "menu_items")


def test_downgrading_stock_reservations_drops_the_column_and_table(database_url):
    _run_flask(["db", "upgrade"], database_url)

    _run_flask(["db", "downgrade", BEFORE_STOCK_RESERVATIONS], database_url)

    assert _current_revision(database_url) == BEFORE_STOCK_RESERVATIONS
    assert "stock_reservations" not in _table_names(database_url)
    assert "reserved_quantity" not in _column_names(database_url, "menu_items")


# ---------- Upgrades with existing data ----------

def test_upgrade_keeps_existing_menu_data_and_defaults_holds_to_zero(database_url):
    _run_flask(["db", "upgrade", BEFORE_STOCK_RESERVATIONS], database_url)

    engine = create_engine(database_url)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO menu_items (id, name, description, category, price_paise, image_url, "
                "is_available, stock_quantity, created_at, updated_at) VALUES "
                "(1, 'Samosa', 'Crispy', 'Snacks', 1500, NULL, :available, 12, :now, :now)"
            ),
            {"available": True, "now": "2026-11-20 10:00:00"},
        )
    engine.dispose()

    _run_flask(["db", "upgrade"], database_url)

    engine = create_engine(database_url)
    with engine.connect() as conn:
        row = conn.execute(text(
            "SELECT name, price_paise, stock_quantity, reserved_quantity FROM menu_items WHERE id = 1"
        )).one()
    engine.dispose()

    assert tuple(row) == ("Samosa", 1500, 12, 0)
    assert _schema_drift(database_url) == []


def test_downgrade_then_upgrade_preserves_surviving_data(database_url):
    _run_flask(["db", "upgrade"], database_url)
    engine = create_engine(database_url)
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO menu_items (name, category, price_paise, is_available, stock_quantity, "
            "reserved_quantity, created_at, updated_at) VALUES "
            "('Tea', 'Drinks', 1000, :available, 30, 0, :now, :now)"
        ), {"available": True, "now": "2026-11-20 10:00:00"})
    engine.dispose()

    _run_flask(["db", "downgrade", BEFORE_STOCK_RESERVATIONS], database_url)
    _run_flask(["db", "upgrade"], database_url)

    engine = create_engine(database_url)
    with engine.connect() as conn:
        name, stock = conn.execute(text("SELECT name, stock_quantity FROM menu_items")).one()
    engine.dispose()

    assert (name, stock) == ("Tea", 30)
    assert _schema_drift(database_url) == []


# ---------- Only the SQLite fallback needs a raw file check ----------

def test_sqlite_file_is_created_by_the_migration_tool(tmp_path):
    url = f"sqlite:///{tmp_path / 'fresh.db'}"
    _run_flask(["db", "upgrade"], url)

    assert (tmp_path / "fresh.db").exists()
    connection = sqlite3.connect(tmp_path / "fresh.db")
    try:
        (count,) = connection.execute("SELECT COUNT(*) FROM alembic_version").fetchone()
    finally:
        connection.close()
    assert count == 1
