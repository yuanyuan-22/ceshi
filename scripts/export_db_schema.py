#!/usr/bin/env python
"""Export database schema metadata for documentation."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "scripts" / "output"
SYSTEM_APP_LABELS = {"admin", "auth", "contenttypes", "sessions"}
SYSTEM_TABLE_PREFIXES = ("auth_", "django_")


def bootstrap_django() -> None:
    project_root = str(PROJECT_ROOT)
    apps_root = str(PROJECT_ROOT / "backend" / "apps")

    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    if apps_root not in sys.path:
        sys.path.insert(0, apps_root)

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

    import django

    django.setup()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read the live database schema and export Markdown/JSON reports."
    )
    parser.add_argument(
        "--database",
        default="default",
        help="Django database alias to inspect. Default: default",
    )
    parser.add_argument(
        "--tables",
        nargs="*",
        help="Only export these table names. Example: auth_user feedback_feedback",
    )
    parser.add_argument(
        "--exclude-system",
        action="store_true",
        help="Skip Django system tables such as auth_* and django_*.",
    )
    parser.add_argument(
        "--include-views",
        action="store_true",
        help="Include database views in addition to physical tables.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory for generated files. Default: scripts/output",
    )
    parser.add_argument(
        "--markdown-name",
        default="",
        help="Optional Markdown file name. Default: <db_name>_schema_report.md",
    )
    parser.add_argument(
        "--json-name",
        default="",
        help="Optional JSON file name. Default: <db_name>_schema_report.json",
    )
    return parser.parse_args()


def normalize_scalar(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            return value.hex()
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def escape_md(value: Any) -> str:
    text = normalize_scalar(value).strip()
    if not text:
        return "-"
    return text.replace("\\", "\\\\").replace("|", "\\|").replace("\n", "<br>")


def bool_mark(value: bool) -> str:
    return "Y" if value else "-"


def classify_table(table_name: str, model_label: str) -> str:
    if model_label:
        app_label = model_label.split(".", 1)[0]
        return "系统表" if app_label in SYSTEM_APP_LABELS else "业务表"
    if table_name.startswith(SYSTEM_TABLE_PREFIXES):
        return "系统表"
    return "业务表"


def build_model_table_map() -> dict[str, str]:
    from django.apps import apps

    table_map: dict[str, str] = {}
    for model in apps.get_models():
        table_map[model._meta.db_table] = f"{model._meta.app_label}.{model.__name__}"
    return table_map


def get_db_config(database_alias: str) -> dict[str, Any]:
    from django.conf import settings

    if database_alias not in settings.DATABASES:
        aliases = ", ".join(sorted(settings.DATABASES))
        raise SystemExit(f"Unknown database alias: {database_alias}. Available: {aliases}")
    return settings.DATABASES[database_alias]


def get_table_entries(connection: Any, include_views: bool) -> list[dict[str, str]]:
    table_entries: list[dict[str, str]] = []
    with connection.cursor() as cursor:
        for table_info in connection.introspection.get_table_list(cursor):
            raw_type = getattr(table_info, "type", "t")
            table_type = "view" if raw_type == "v" else "table"
            if table_type == "view" and not include_views:
                continue
            table_entries.append({"name": table_info.name, "type": table_type})
    table_entries.sort(key=lambda item: item["name"])
    return table_entries


def open_mysql_connection(db_config: dict[str, Any]) -> Any:
    import pymysql

    options = db_config.get("OPTIONS", {}) or {}
    connect_kwargs = {
        "host": db_config.get("HOST") or "127.0.0.1",
        "user": db_config.get("USER") or "",
        "password": db_config.get("PASSWORD") or "",
        "database": db_config.get("NAME") or "",
        "port": int(db_config.get("PORT") or 3306),
        "charset": options.get("charset") or "utf8mb4",
        "autocommit": True,
        "ssl_disabled": True,
    }
    init_command = options.get("init_command")
    if init_command:
        connect_kwargs["init_command"] = init_command
    return pymysql.connect(**connect_kwargs)


def get_mysql_table_entries(
    sql_connection: Any, schema_name: str, include_views: bool
) -> list[dict[str, str]]:
    allowed_types = ["BASE TABLE"]
    if include_views:
        allowed_types.append("VIEW")

    placeholders = ", ".join(["%s"] * len(allowed_types))
    query = f"""
        SELECT TABLE_NAME, TABLE_TYPE
        FROM information_schema.TABLES
        WHERE TABLE_SCHEMA = %s
          AND TABLE_TYPE IN ({placeholders})
        ORDER BY TABLE_NAME
    """

    with sql_connection.cursor() as cursor:
        cursor.execute(query, [schema_name, *allowed_types])
        rows = cursor.fetchall()

    table_entries = []
    for table_name, table_type in rows:
        table_entries.append(
            {
                "name": normalize_scalar(table_name),
                "type": "view" if normalize_scalar(table_type).upper() == "VIEW" else "table",
            }
        )
    return table_entries


def fetch_mysql_table_summary(cursor: Any, schema_name: str, table_name: str) -> dict[str, Any]:
    cursor.execute(
        """
        SELECT
            TABLE_NAME,
            ENGINE,
            TABLE_COLLATION,
            TABLE_ROWS,
            TABLE_COMMENT,
            CREATE_TIME,
            UPDATE_TIME
        FROM information_schema.TABLES
        WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
        """,
        [schema_name, table_name],
    )
    row = cursor.fetchone()
    if not row:
        return {
            "engine": "",
            "collation": "",
            "row_estimate": None,
            "comment": "",
            "created_at": "",
            "updated_at": "",
        }
    return {
        "engine": normalize_scalar(row[1]),
        "collation": normalize_scalar(row[2]),
        "row_estimate": row[3],
        "comment": normalize_scalar(row[4]),
        "created_at": normalize_scalar(row[5]),
        "updated_at": normalize_scalar(row[6]),
    }


def fetch_mysql_columns(cursor: Any, schema_name: str, table_name: str) -> list[dict[str, Any]]:
    cursor.execute(
        """
        SELECT
            ORDINAL_POSITION,
            COLUMN_NAME,
            COLUMN_TYPE,
            IS_NULLABLE,
            COLUMN_DEFAULT,
            COLUMN_KEY,
            EXTRA,
            COLUMN_COMMENT,
            DATA_TYPE,
            CHARACTER_MAXIMUM_LENGTH,
            NUMERIC_PRECISION,
            NUMERIC_SCALE,
            DATETIME_PRECISION,
            CHARACTER_SET_NAME,
            COLLATION_NAME
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
        ORDER BY ORDINAL_POSITION
        """,
        [schema_name, table_name],
    )

    columns: list[dict[str, Any]] = []
    for row in cursor.fetchall():
        extra = normalize_scalar(row[6])
        column_key = normalize_scalar(row[5])
        columns.append(
            {
                "position": row[0],
                "name": normalize_scalar(row[1]),
                "db_type": normalize_scalar(row[2]),
                "nullable": normalize_scalar(row[3]).upper() == "YES",
                "default": normalize_scalar(row[4]),
                "is_primary": column_key == "PRI",
                "is_unique": column_key == "UNI",
                "is_indexed": column_key in {"PRI", "UNI", "MUL"},
                "auto_increment": "auto_increment" in extra.lower(),
                "extra": extra,
                "comment": normalize_scalar(row[7]),
                "data_type": normalize_scalar(row[8]),
                "char_length": row[9],
                "numeric_precision": row[10],
                "numeric_scale": row[11],
                "datetime_precision": row[12],
                "charset": normalize_scalar(row[13]),
                "collation": normalize_scalar(row[14]),
            }
        )
    return columns


def fetch_mysql_indexes(cursor: Any, schema_name: str, table_name: str) -> list[dict[str, Any]]:
    cursor.execute(
        """
        SELECT
            INDEX_NAME,
            NON_UNIQUE,
            INDEX_TYPE,
            SEQ_IN_INDEX,
            COLUMN_NAME,
            COLLATION
        FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
        ORDER BY INDEX_NAME, SEQ_IN_INDEX
        """,
        [schema_name, table_name],
    )

    grouped: dict[str, dict[str, Any]] = {}
    for row in cursor.fetchall():
        index_name = normalize_scalar(row[0])
        grouped.setdefault(
            index_name,
            {
                "name": index_name,
                "unique": row[1] == 0,
                "type": normalize_scalar(row[2]),
                "columns": [],
                "orders": [],
                "is_primary": index_name == "PRIMARY",
            },
        )
        grouped[index_name]["columns"].append(normalize_scalar(row[4]))
        grouped[index_name]["orders"].append(normalize_scalar(row[5]))

    indexes = list(grouped.values())
    indexes.sort(key=lambda item: (not item["is_primary"], item["name"]))
    return indexes


def fetch_mysql_foreign_keys(cursor: Any, schema_name: str, table_name: str) -> list[dict[str, Any]]:
    cursor.execute(
        """
        SELECT
            CONSTRAINT_NAME,
            COLUMN_NAME,
            REFERENCED_TABLE_NAME,
            REFERENCED_COLUMN_NAME,
            ORDINAL_POSITION
        FROM information_schema.KEY_COLUMN_USAGE
        WHERE TABLE_SCHEMA = %s
          AND TABLE_NAME = %s
          AND REFERENCED_TABLE_NAME IS NOT NULL
        ORDER BY CONSTRAINT_NAME, ORDINAL_POSITION
        """,
        [schema_name, table_name],
    )

    grouped: dict[str, dict[str, Any]] = {}
    for row in cursor.fetchall():
        fk_name = normalize_scalar(row[0])
        grouped.setdefault(
            fk_name,
            {
                "name": fk_name,
                "columns": [],
                "referenced_table": normalize_scalar(row[2]),
                "referenced_columns": [],
            },
        )
        grouped[fk_name]["columns"].append(normalize_scalar(row[1]))
        grouped[fk_name]["referenced_columns"].append(normalize_scalar(row[3]))

    return list(grouped.values())


def fetch_generic_table_metadata(connection: Any, table_name: str) -> dict[str, Any]:
    with connection.cursor() as cursor:
        description = connection.introspection.get_table_description(cursor, table_name)
        constraints = connection.introspection.get_constraints(cursor, table_name)

    unique_single_columns = {
        columns[0]
        for meta in constraints.values()
        for columns in [meta.get("columns", [])]
        if meta.get("unique") and len(columns) == 1
    }

    columns: list[dict[str, Any]] = []
    for position, field in enumerate(description, start=1):
        name = getattr(field, "name", field[0])
        type_code = getattr(field, "type_code", None)
        try:
            db_type = connection.introspection.get_field_type(type_code, field)
        except Exception:
            db_type = normalize_scalar(type_code)
        columns.append(
            {
                "position": position,
                "name": normalize_scalar(name),
                "db_type": normalize_scalar(db_type),
                "nullable": bool(getattr(field, "null_ok", False)),
                "default": normalize_scalar(getattr(field, "default", "")),
                "is_primary": any(
                    meta.get("primary_key") and name in meta.get("columns", [])
                    for meta in constraints.values()
                ),
                "is_unique": name in unique_single_columns,
                "is_indexed": any(
                    meta.get("index") and name in meta.get("columns", [])
                    for meta in constraints.values()
                ),
                "auto_increment": False,
                "extra": "",
                "comment": "",
                "data_type": normalize_scalar(db_type),
                "char_length": getattr(field, "internal_size", None),
                "numeric_precision": getattr(field, "precision", None),
                "numeric_scale": getattr(field, "scale", None),
                "datetime_precision": None,
                "charset": "",
                "collation": "",
            }
        )

    indexes: list[dict[str, Any]] = []
    foreign_keys: list[dict[str, Any]] = []
    for name, meta in constraints.items():
        columns_in_constraint = [normalize_scalar(col) for col in meta.get("columns", [])]
        if meta.get("foreign_key"):
            ref_table, ref_column = meta["foreign_key"]
            foreign_keys.append(
                {
                    "name": normalize_scalar(name),
                    "columns": columns_in_constraint,
                    "referenced_table": normalize_scalar(ref_table),
                    "referenced_columns": [normalize_scalar(ref_column)],
                }
            )
        if meta.get("index") or meta.get("unique") or meta.get("primary_key"):
            indexes.append(
                {
                    "name": normalize_scalar(name),
                    "unique": bool(meta.get("unique") or meta.get("primary_key")),
                    "type": "PRIMARY" if meta.get("primary_key") else "INDEX",
                    "columns": columns_in_constraint,
                    "orders": [normalize_scalar(order) for order in meta.get("orders", [])],
                    "is_primary": bool(meta.get("primary_key")),
                }
            )

    indexes.sort(key=lambda item: (not item["is_primary"], item["name"]))

    return {
        "summary": {
            "engine": connection.vendor,
            "collation": "",
            "row_estimate": None,
            "comment": "",
            "created_at": "",
            "updated_at": "",
        },
        "columns": columns,
        "indexes": indexes,
        "foreign_keys": foreign_keys,
    }


def read_table_metadata(connection: Any, database_name: str, table_name: str) -> dict[str, Any]:
    if connection.vendor == "mysql":
        with connection.cursor() as cursor:
            return {
                "summary": fetch_mysql_table_summary(cursor, database_name, table_name),
                "columns": fetch_mysql_columns(cursor, database_name, table_name),
                "indexes": fetch_mysql_indexes(cursor, database_name, table_name),
                "foreign_keys": fetch_mysql_foreign_keys(cursor, database_name, table_name),
            }
    return fetch_generic_table_metadata(connection, table_name)


def render_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    db_meta = report["database"]
    tables = report["tables"]

    lines.append("# 数据库结构导出报告")
    lines.append("")
    lines.append(f"生成时间：{escape_md(report['generated_at'])}")
    lines.append("")
    lines.append("该报告来自真实数据库结构，可直接作为数据库设计说明书的辅助素材。")
    lines.append("")
    lines.append("## 1. 数据库环境")
    lines.append("")
    lines.append("| 项目 | 值 |")
    lines.append("| --- | --- |")
    lines.append(f"| Django 数据源 | {escape_md(db_meta['alias'])} |")
    lines.append(f"| 数据库名 | {escape_md(db_meta['name'])} |")
    lines.append(f"| 数据库引擎 | {escape_md(db_meta['engine'])} |")
    lines.append(f"| 主机 | {escape_md(db_meta['host'])} |")
    lines.append(f"| 端口 | {escape_md(db_meta['port'])} |")
    lines.append(f"| 字符集 | {escape_md(db_meta['charset'])} |")
    lines.append(f"| 时区 | {escape_md(db_meta['timezone'])} |")
    lines.append(f"| 表数量 | {escape_md(db_meta['table_count'])} |")
    lines.append("")
    lines.append("## 2. 数据表列表")
    lines.append("")
    lines.append("| 序号 | 表名 | 类型 | 来源模型 | 分类 | 预估行数 | 表注释 |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    for index, table in enumerate(tables, start=1):
        summary = table["summary"]
        row_estimate = summary["row_estimate"]
        lines.append(
            "| {idx} | {name} | {table_type} | {model} | {category} | {rows} | {comment} |".format(
                idx=index,
                name=escape_md(table["name"]),
                table_type=escape_md(table["table_type"]),
                model=escape_md(table["model_label"]),
                category=escape_md(table["category"]),
                rows=escape_md("" if row_estimate is None else row_estimate),
                comment=escape_md(summary["comment"]),
            )
        )

    lines.append("")
    lines.append("## 3. 数据表详情")
    lines.append("")
    lines.append("> 注：MySQL `TABLE_ROWS` 对 InnoDB 通常是估算值，可用于文档参考，但不应当作为精确统计口径。")
    lines.append("")

    for index, table in enumerate(tables, start=1):
        summary = table["summary"]
        lines.append(f"### 3.{index} {table['name']}")
        lines.append("")
        lines.append(f"- 表类型：{table['table_type']}")
        lines.append(f"- 来源模型：{table['model_label'] or '-'}")
        lines.append(f"- 分类：{table['category']}")
        lines.append(f"- 存储引擎：{summary['engine'] or '-'}")
        lines.append(f"- 排序规则：{summary['collation'] or '-'}")
        lines.append(
            f"- 预估行数：{summary['row_estimate'] if summary['row_estimate'] is not None else '-'}"
        )
        lines.append(f"- 表注释：{summary['comment'] or '-'}")
        if summary["created_at"]:
            lines.append(f"- 创建时间：{summary['created_at']}")
        if summary["updated_at"]:
            lines.append(f"- 最近更新时间：{summary['updated_at']}")
        lines.append("")
        lines.append("#### 字段信息")
        lines.append("")
        lines.append(
            "| 序号 | 字段名 | 数据库类型 | 可空 | 默认值 | 主键 | 唯一 | 自增 | 额外属性 | 字段注释 |"
        )
        lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
        for column in table["columns"]:
            lines.append(
                "| {position} | {name} | {db_type} | {nullable} | {default} | {primary} | {unique} | {auto_increment} | {extra} | {comment} |".format(
                    position=column["position"],
                    name=escape_md(column["name"]),
                    db_type=escape_md(column["db_type"]),
                    nullable=bool_mark(column["nullable"]),
                    default=escape_md(column["default"]),
                    primary=bool_mark(column["is_primary"]),
                    unique=bool_mark(column["is_unique"]),
                    auto_increment=bool_mark(column["auto_increment"]),
                    extra=escape_md(column["extra"]),
                    comment=escape_md(column["comment"]),
                )
            )

        lines.append("")
        lines.append("#### 索引信息")
        lines.append("")
        if table["indexes"]:
            lines.append("| 索引名 | 类型 | 唯一 | 主键 | 字段列表 | 排序 |")
            lines.append("| --- | --- | --- | --- | --- | --- |")
            for index_info in table["indexes"]:
                lines.append(
                    "| {name} | {index_type} | {unique} | {primary} | {columns} | {orders} |".format(
                        name=escape_md(index_info["name"]),
                        index_type=escape_md(index_info["type"]),
                        unique=bool_mark(index_info["unique"]),
                        primary=bool_mark(index_info["is_primary"]),
                        columns=escape_md(", ".join(index_info["columns"])),
                        orders=escape_md(", ".join(index_info["orders"])),
                    )
                )
        else:
            lines.append("无索引信息。")

        lines.append("")
        lines.append("#### 外键信息")
        lines.append("")
        if table["foreign_keys"]:
            lines.append("| 外键名 | 字段 | 关联表 | 关联字段 |")
            lines.append("| --- | --- | --- | --- |")
            for fk in table["foreign_keys"]:
                lines.append(
                    "| {name} | {columns} | {ref_table} | {ref_columns} |".format(
                        name=escape_md(fk["name"]),
                        columns=escape_md(", ".join(fk["columns"])),
                        ref_table=escape_md(fk["referenced_table"]),
                        ref_columns=escape_md(", ".join(fk["referenced_columns"])),
                    )
                )
        else:
            lines.append("无外键信息。")

        lines.append("")

    return "\n".join(lines).strip() + "\n"


def build_report(
    connection: Any,
    db_config: dict[str, Any],
    table_entries: list[dict[str, str]],
    model_table_map: dict[str, str],
    args: argparse.Namespace,
) -> dict[str, Any]:
    from django.conf import settings

    database_name = normalize_scalar(db_config.get("NAME"))
    options = db_config.get("OPTIONS", {}) or {}
    charset = normalize_scalar(options.get("charset"))
    timezone = normalize_scalar(options.get("timezone")) or normalize_scalar(settings.TIME_ZONE)

    tables: list[dict[str, Any]] = []
    selected_tables = set(args.tables or [])
    for entry in table_entries:
        table_name = entry["name"]
        if selected_tables and table_name not in selected_tables:
            continue

        model_label = model_table_map.get(table_name, "")
        category = classify_table(table_name, model_label)
        if args.exclude_system and category == "系统表":
            continue

        metadata = read_table_metadata(connection, database_name, table_name)
        tables.append(
            {
                "name": table_name,
                "table_type": entry["type"],
                "model_label": model_label,
                "category": category,
                "summary": metadata["summary"],
                "columns": metadata["columns"],
                "indexes": metadata["indexes"],
                "foreign_keys": metadata["foreign_keys"],
            }
        )

    tables.sort(key=lambda item: item["name"])

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "database": {
            "alias": args.database,
            "name": database_name,
            "engine": normalize_scalar(db_config.get("ENGINE")),
            "host": normalize_scalar(db_config.get("HOST")),
            "port": normalize_scalar(db_config.get("PORT")),
            "charset": charset,
            "timezone": timezone,
            "table_count": len(tables),
        },
        "tables": tables,
    }


def build_mysql_report(
    sql_connection: Any,
    db_config: dict[str, Any],
    model_table_map: dict[str, str],
    args: argparse.Namespace,
) -> dict[str, Any]:
    from django.conf import settings

    database_name = normalize_scalar(db_config.get("NAME"))
    options = db_config.get("OPTIONS", {}) or {}
    charset = normalize_scalar(options.get("charset"))
    timezone = normalize_scalar(options.get("timezone")) or normalize_scalar(settings.TIME_ZONE)

    table_entries = get_mysql_table_entries(sql_connection, database_name, args.include_views)
    selected_tables = set(args.tables or [])
    tables: list[dict[str, Any]] = []

    with sql_connection.cursor() as cursor:
        for entry in table_entries:
            table_name = entry["name"]
            if selected_tables and table_name not in selected_tables:
                continue

            model_label = model_table_map.get(table_name, "")
            category = classify_table(table_name, model_label)
            if args.exclude_system and category == "系统表":
                continue

            tables.append(
                {
                    "name": table_name,
                    "table_type": entry["type"],
                    "model_label": model_label,
                    "category": category,
                    "summary": fetch_mysql_table_summary(cursor, database_name, table_name),
                    "columns": fetch_mysql_columns(cursor, database_name, table_name),
                    "indexes": fetch_mysql_indexes(cursor, database_name, table_name),
                    "foreign_keys": fetch_mysql_foreign_keys(cursor, database_name, table_name),
                }
            )

    tables.sort(key=lambda item: item["name"])

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "database": {
            "alias": args.database,
            "name": database_name,
            "engine": normalize_scalar(db_config.get("ENGINE")),
            "host": normalize_scalar(db_config.get("HOST")),
            "port": normalize_scalar(db_config.get("PORT")),
            "charset": charset,
            "timezone": timezone,
            "table_count": len(tables),
        },
        "tables": tables,
    }


def ensure_output_names(report: dict[str, Any], args: argparse.Namespace) -> tuple[Path, Path]:
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    safe_db_name = report["database"]["name"] or args.database
    safe_db_name = safe_db_name.replace(" ", "_")

    markdown_name = args.markdown_name or f"{safe_db_name}_schema_report.md"
    json_name = args.json_name or f"{safe_db_name}_schema_report.json"

    return output_dir / markdown_name, output_dir / json_name


def main() -> None:
    args = parse_args()
    bootstrap_django()

    from django.db import connections

    db_config = get_db_config(args.database)

    model_table_map = build_model_table_map()
    engine = normalize_scalar(db_config.get("ENGINE")).lower()

    if "mysql" in engine:
        try:
            sql_connection = open_mysql_connection(db_config)
        except Exception as exc:
            raise SystemExit(
                f"Database connection failed for alias '{args.database}': {exc}"
            ) from exc

        try:
            report = build_mysql_report(sql_connection, db_config, model_table_map, args)
        finally:
            sql_connection.close()
    else:
        connection = connections[args.database]
        try:
            connection.ensure_connection()
        except Exception as exc:
            raise SystemExit(
                f"Database connection failed for alias '{args.database}': {exc}"
            ) from exc

        table_entries = get_table_entries(connection, args.include_views)
        report = build_report(connection, db_config, table_entries, model_table_map, args)

    markdown_path, json_path = ensure_output_names(report, args)
    markdown_path.write_text(render_markdown(report), encoding="utf-8-sig")
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8-sig")

    print(f"Exported {report['database']['table_count']} table(s).")
    print(f"Markdown: {markdown_path}")
    print(f"JSON: {json_path}")


if __name__ == "__main__":
    main()
