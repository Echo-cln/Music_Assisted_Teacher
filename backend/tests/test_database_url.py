from app.core.config import normalize_database_url


def test_supabase_postgresql_uri_uses_psycopg_driver():
    url = "postgresql://postgres.project-ref:secret@pooler.example:5432/postgres?sslmode=require"
    assert normalize_database_url(url) == (
        "postgresql+psycopg://postgres.project-ref:secret@pooler.example:5432/postgres?sslmode=require"
    )


def test_legacy_postgres_scheme_uses_psycopg_driver():
    url = "postgres://postgres:secret@localhost:5432/postgres"
    assert normalize_database_url(url) == "postgresql+psycopg://postgres:secret@localhost:5432/postgres"


def test_sqlite_and_explicit_driver_urls_are_unchanged():
    sqlite_url = "sqlite:///./data/zhiban.db"
    psycopg_url = "postgresql+psycopg://postgres:secret@localhost:5432/postgres"
    assert normalize_database_url(sqlite_url) == sqlite_url
    assert normalize_database_url(psycopg_url) == psycopg_url
