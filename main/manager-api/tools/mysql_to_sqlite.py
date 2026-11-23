#!/usr/bin/env python3
"""Copy the manager-api MySQL database into a SQLite file (schema + data).

The schema is read from MySQL's information_schema (the state after every Liquibase
changeset ran), converted to SQLite types, and the rows are copied as-is. Dates are
stored as 'YYYY-MM-DD HH:MM:SS' text, which is what sqlite-jdbc reads back when the
JDBC URL sets date_class=TEXT and date_string_format=yyyy-MM-dd HH:mm:ss.

Usage (pymysql required):
  python3 mysql_to_sqlite.py --host DB --user root --password ... --database xiaozhi_esp32_server \
      --out xiaozhi.db [--schema-out baseline.sql]
"""
import argparse
import datetime as dt
import decimal
import sqlite3
import sys

import pymysql

SKIP_TABLES = {"DATABASECHANGELOG", "DATABASECHANGELOGLOCK"}  # Liquibase bookkeeping (SQLite gets its own)

INT_TYPES = {"tinyint", "smallint", "mediumint", "int", "integer", "bigint", "bit", "year"}
REAL_TYPES = {"float", "double", "real"}
NUM_TYPES = {"decimal", "numeric"}
BLOB_TYPES = {"blob", "tinyblob", "mediumblob", "longblob", "binary", "varbinary"}
DATE_TYPES = {"datetime", "timestamp", "date", "time"}


def sqlite_type(data_type: str) -> str:
    t = data_type.lower()
    if t in INT_TYPES:
        return "INTEGER"
    if t in REAL_TYPES:
        return "REAL"
    if t in NUM_TYPES:
        return "NUMERIC"
    if t in BLOB_TYPES:
        return "BLOB"
    return "TEXT"  # char/varchar/text/json/enum/set/date-time


def q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def sqlite_default(col) -> str:
    default, data_type, extra = col["COLUMN_DEFAULT"], col["DATA_TYPE"].lower(), (col["EXTRA"] or "").lower()
    if default is None:
        return ""
    d = str(default)
    if d.upper().startswith("CURRENT_TIMESTAMP") or d.lower() in ("now()", "current_timestamp()"):
        return " DEFAULT (datetime('now','localtime'))"
    if "default_generated" in extra and d.startswith("("):
        return ""  # expression defaults (rare) are left to the application
    if d.upper() == "NULL":
        return " DEFAULT NULL"
    if sqlite_type(data_type) in ("INTEGER", "REAL", "NUMERIC"):
        try:
            float(d)
            return f" DEFAULT {d}"
        except ValueError:
            pass
    if d.startswith("'") and d.endswith("'"):
        d = d[1:-1]
    return " DEFAULT '" + d.replace("'", "''") + "'"


def convert_value(v):
    if isinstance(v, dt.datetime):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(v, dt.date):
        return v.strftime("%Y-%m-%d")
    if isinstance(v, dt.timedelta):
        total = int(v.total_seconds())
        return f"{total // 3600:02d}:{total % 3600 // 60:02d}:{total % 60:02d}"
    if isinstance(v, decimal.Decimal):
        return int(v) if v == v.to_integral_value() else float(v)
    if isinstance(v, (bytes, bytearray)) and len(v) == 1 and v in (b"\x00", b"\x01"):
        return v[0]  # BIT(1)
    return v


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", required=True)
    ap.add_argument("--port", type=int, default=3306)
    ap.add_argument("--user", required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument("--database", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--schema-out")
    a = ap.parse_args()

    my = pymysql.connect(host=a.host, port=a.port, user=a.user, password=a.password, database=a.database,
                         charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor)
    cur = my.cursor()
    cur.execute("SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s AND TABLE_TYPE='BASE TABLE' "
                "ORDER BY TABLE_NAME", (a.database,))
    tables = [r["TABLE_NAME"] for r in cur.fetchall() if r["TABLE_NAME"] not in SKIP_TABLES]

    ddl = []
    for t in tables:
        cur.execute("SELECT * FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s "
                    "ORDER BY ORDINAL_POSITION", (a.database, t))
        cols = cur.fetchall()
        cur.execute("SELECT INDEX_NAME, NON_UNIQUE, SEQ_IN_INDEX, COLUMN_NAME FROM information_schema.STATISTICS "
                    "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s ORDER BY INDEX_NAME, SEQ_IN_INDEX", (a.database, t))
        idx = {}
        for r in cur.fetchall():
            idx.setdefault(r["INDEX_NAME"], {"unique": not r["NON_UNIQUE"], "cols": []})["cols"].append(r["COLUMN_NAME"])
        pk = idx.pop("PRIMARY", {"cols": []})["cols"]
        autoinc = [c["COLUMN_NAME"] for c in cols if "auto_increment" in (c["EXTRA"] or "").lower()]

        lines = []
        for c in cols:
            name, typ = c["COLUMN_NAME"], sqlite_type(c["DATA_TYPE"])
            line = f"  {q(name)} {typ}"
            # MySQL *_ci collations compare text case-insensitively ('LLM' = 'llm'); SQLite's
            # default is case-sensitive, so keep MySQL's behaviour with COLLATE NOCASE.
            if typ == "TEXT" and (c.get("COLLATION_NAME") or "").lower().endswith("_ci"):
                line += " COLLATE NOCASE"
            if pk == [name] and name in autoinc and typ == "INTEGER":
                line += " PRIMARY KEY AUTOINCREMENT"
            elif pk == [name] and len(pk) == 1:
                line += " PRIMARY KEY"
            if c["IS_NULLABLE"] == "NO" and not line.endswith(("PRIMARY KEY", "AUTOINCREMENT")):
                line += " NOT NULL"
            line += sqlite_default(c)
            lines.append(line)
        if len(pk) > 1:
            lines.append("  PRIMARY KEY (" + ", ".join(q(x) for x in pk) + ")")
        ddl.append(f"CREATE TABLE {q(t)} (\n" + ",\n".join(lines) + "\n);")
        for name, info in sorted(idx.items()):
            kind = "UNIQUE INDEX" if info["unique"] else "INDEX"
            ddl.append(f"CREATE {kind} {q(t + '__' + name)} ON {q(t)} (" + ", ".join(q(x) for x in info["cols"]) + ");")

    schema_sql = "\n".join(ddl) + "\n"
    if a.schema_out:
        with open(a.schema_out, "w", encoding="utf-8") as f:
            f.write(schema_sql)

    lite = sqlite3.connect(a.out)
    lite.executescript("PRAGMA journal_mode=WAL;\n" + schema_sql)
    total = 0
    for t in tables:
        cur.execute(f"SELECT * FROM `{t}`")
        rows = cur.fetchall()
        if not rows:
            continue
        names = list(rows[0].keys())
        sql = f"INSERT INTO {q(t)} (" + ", ".join(q(n) for n in names) + ") VALUES (" + ", ".join("?" for _ in names) + ")"
        lite.executemany(sql, [tuple(convert_value(r[n]) for n in names) for r in rows])
        total += len(rows)
        print(f"{t}: {len(rows)}")
    lite.commit()
    print(f"tables={len(tables)} rows={total}")
    bad = lite.execute("PRAGMA integrity_check").fetchone()[0]
    print("integrity:", bad)
    lite.close()
    return 0 if bad == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
