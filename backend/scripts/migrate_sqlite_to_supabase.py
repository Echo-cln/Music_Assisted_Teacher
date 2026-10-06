"""Safely copy this application's SQLite rows into the configured PostgreSQL DB.

Run from the repository root with its backend virtual environment active:
    python backend/scripts/migrate_sqlite_to_supabase.py

The destination is DATABASE_URL from backend/.env. The source defaults to
backend/data/zhiban.db. The script never deletes or modifies source rows and
refuses to import when any application table in the destination is non-empty.
"""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import shutil
import sys

from sqlalchemy import MetaData, func, inspect, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.sql.schema import Table

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
DEFAULT_SOURCE = BACKEND_DIR / "data" / "zhiban.db"


def _application_tables() -> dict[str, Table]:
    # Import after adding backend so this works when invoked at repository root.
    sys.path.insert(0, str(BACKEND_DIR))
    from app.db.session import Base  # noqa: PLC0415
    from app.models import entities  # noqa: F401, PLC0415

    return dict(Base.metadata.tables)


def _dependency_order(tables: dict[str, Table]) -> list[str]:
    """Topologically order mapped tables by their in-app foreign keys."""
    dependencies = {
        name: {
            fk.column.table.name
            for fk in table.foreign_keys
            if fk.column.table.name in tables and fk.column.table.name != name
        }
        for name, table in tables.items()
    }
    ordered: list[str] = []
    ready = sorted(name for name, deps in dependencies.items() if not deps)
    while ready:
        name = ready.pop(0)
        ordered.append(name)
        for other in sorted(dependencies):
            if name in dependencies[other]:
                dependencies[other].remove(name)
                if not dependencies[other] and other not in ordered and other not in ready:
                    ready.append(other)
                    ready.sort()
    if len(ordered) != len(tables):
        unresolved = sorted(set(tables) - set(ordered))
        raise RuntimeError(f"表之间存在循环外键，无法安全排序：{', '.join(unresolved)}")
    return ordered


def _count(engine: Engine, table: Table) -> int:
    with engine.connect() as conn:
        return int(conn.execute(select(func.count()).select_from(table)).scalar_one())


def _reset_postgres_sequence(conn, table: Table) -> None:
    if len(table.primary_key.columns) != 1:
        return
    pk = next(iter(table.primary_key.columns))
    if not isinstance(pk.type.python_type, type) or pk.type.python_type is not int:
        return
    sequence = conn.execute(
        text("SELECT pg_get_serial_sequence(:table_name, :column_name)"),
        {"table_name": f"public.{table.name}", "column_name": pk.name},
    ).scalar_one_or_none()
    if not sequence:
        return
    maximum = conn.execute(select(func.max(pk))).scalar_one_or_none()
    conn.execute(
        text("SELECT setval(CAST(:sequence_name AS regclass), :last_value, :is_called)"),
        {
            "sequence_name": sequence,
            "last_value": int(maximum) if maximum is not None else 1,
            "is_called": maximum is not None,
        },
    )


def migrate(source_path: Path, target_engine: Engine, *, assume_yes: bool = False) -> None:
    from app.db.init_db import init_db  # noqa: PLC0415
    from app.db.session import settings  # noqa: PLC0415

    if not source_path.is_file():
        raise FileNotFoundError(f"找不到 SQLite 数据库：{source_path}")
    if target_engine.dialect.name != "postgresql":
        raise RuntimeError("当前 DATABASE_URL 不是 PostgreSQL；为避免写错库，已停止。")

    source_url = f"sqlite:///{source_path.resolve().as_posix()}"
    from sqlalchemy import create_engine  # noqa: PLC0415

    source_engine = create_engine(source_url)
    app_tables = _application_tables()

    try:
        source_names = set(inspect(source_engine).get_table_names())
        selected_names = [name for name in _dependency_order(app_tables) if name in source_names]
        if not selected_names:
            raise RuntimeError("SQLite 文件里没有找到本项目的业务表。")

        # Ensure current application schema exists. This does not copy or alter source data.
        init_db()
        destination_counts = {name: _count(target_engine, table) for name, table in app_tables.items()}
        nonempty = {name: count for name, count in destination_counts.items() if count}
        if nonempty:
            details = ", ".join(f"{name}={count}" for name, count in nonempty.items())
            raise RuntimeError(
                "目标 Supabase 中已有业务数据，脚本拒绝覆盖或合并，以免重复或串号。"
                f"非空表：{details}。请先备份并确认目标库后再处理。"
            )

        source_meta = MetaData()
        source_meta.reflect(bind=source_engine, only=selected_names)
        source_counts = {
            name: _count(source_engine, source_meta.tables[name]) for name in selected_names
        }

        target = settings.database_url
        # URL rendering hides the password.
        print(f"SQLite 来源：{source_path.resolve()}")
        print(f"PostgreSQL 目标：{target_engine.url.render_as_string(hide_password=True)}")
        print("将迁移的记录数：")
        for name in selected_names:
            print(f"  {name}: {source_counts[name]}")
        print("注意：数据库中的音频/乐谱路径会迁移；路径指向的本地文件本身不在 SQLite 内。")
        if not assume_yes:
            answer = input("确认继续请输入 MIGRATE：").strip()
            if answer != "MIGRATE":
                print("已取消；没有向 Supabase 写入数据。")
                return

        backup_path = source_path.with_name(
            f"{source_path.name}.before-supabase-{datetime.now().strftime('%Y%m%d-%H%M%S')}.bak"
        )
        shutil.copy2(source_path, backup_path)
        print(f"已备份 SQLite：{backup_path}")

        # One PostgreSQL transaction: a failed insert rolls the whole import back.
        with target_engine.begin() as destination, source_engine.connect() as source:
            for name in selected_names:
                source_table = source_meta.tables[name]
                target_table = app_tables[name]
                common_columns = [
                    column.name
                    for column in target_table.columns
                    if column.name in source_table.c
                ]
                result = source.execute(select(source_table)).mappings()
                batch: list[dict] = []
                inserted = 0
                for row in result:
                    batch.append({column: row[column] for column in common_columns})
                    if len(batch) >= 500:
                        destination.execute(target_table.insert(), batch)
                        inserted += len(batch)
                        batch.clear()
                if batch:
                    destination.execute(target_table.insert(), batch)
                    inserted += len(batch)
                if inserted != source_counts[name]:
                    raise RuntimeError(
                        f"{name} 读取数量不一致：预期 {source_counts[name]}，实际 {inserted}"
                    )
                print(f"已导入 {name}: {inserted}")

            for name in selected_names:
                _reset_postgres_sequence(destination, app_tables[name])

        mismatches = {
            name: (_count(target_engine, app_tables[name]), source_counts[name])
            for name in selected_names
            if _count(target_engine, app_tables[name]) != source_counts[name]
        }
        if mismatches:
            raise RuntimeError(f"导入后核对数量不一致：{mismatches}")
        print("迁移完成：所有业务表数量已核对一致。")
    finally:
        source_engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="将旧 SQLite 业务数据安全迁移到 DATABASE_URL 指向的 Supabase PostgreSQL")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE, help="SQLite 文件路径；默认 backend/data/zhiban.db")
    parser.add_argument("--yes", action="store_true", help="跳过交互确认；适合已核对目标地址后的自动化运行")
    args = parser.parse_args()

    try:
        sys.path.insert(0, str(BACKEND_DIR))
        from app.db.session import engine  # noqa: PLC0415

        migrate(args.source.resolve(), engine, assume_yes=args.yes)
    except Exception as exc:  # concise actionable failure for Windows terminal
        print(f"迁移失败：{exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
