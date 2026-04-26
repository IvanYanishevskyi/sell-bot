from __future__ import annotations

import sqlite3
from typing import Any, Iterable, Sequence


class QueryBuilder:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def insert(self, table: str, data: dict[str, Any]) -> int:
        columns = ", ".join(data.keys())
        placeholders = ", ".join(["?"] * len(data))
        sql = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"
        cur = self.conn.execute(sql, tuple(data.values()))
        return int(cur.lastrowid)

    def bulk_insert(self, table: str, rows: Iterable[dict[str, Any]]) -> None:
        rows = list(rows)
        if not rows:
            return
        columns = list(rows[0].keys())
        columns_sql = ", ".join(columns)
        placeholders = ", ".join(["?"] * len(columns))
        sql = f"INSERT INTO {table} ({columns_sql}) VALUES ({placeholders})"
        values = [tuple(row[col] for col in columns) for row in rows]
        self.conn.executemany(sql, values)

    def update(
        self,
        table: str,
        data: dict[str, Any],
        where_sql: str,
        where_params: Sequence[Any] = (),
    ) -> int:
        set_clause = ", ".join([f"{col} = ?" for col in data.keys()])
        sql = f"UPDATE {table} SET {set_clause} WHERE {where_sql}"
        cur = self.conn.execute(sql, tuple(data.values()) + tuple(where_params))
        return cur.rowcount

    def upsert(self, table: str, data: dict[str, Any], conflict_columns: list[str], update_columns: list[str]) -> None:
        columns = list(data.keys())
        placeholders = ", ".join(["?"] * len(columns))
        columns_sql = ", ".join(columns)
        conflict_sql = ", ".join(conflict_columns)
        update_sql = ", ".join([f"{col}=excluded.{col}" for col in update_columns])
        sql = (
            f"INSERT INTO {table} ({columns_sql}) VALUES ({placeholders}) "
            f"ON CONFLICT({conflict_sql}) DO UPDATE SET {update_sql}"
        )
        self.conn.execute(sql, tuple(data[col] for col in columns))

    def fetch_one(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Row | None:
        cur = self.conn.execute(sql, params)
        return cur.fetchone()

    def fetch_all(self, sql: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
        cur = self.conn.execute(sql, params)
        return list(cur.fetchall())

    def execute(self, sql: str, params: Sequence[Any] = ()) -> int:
        cur = self.conn.execute(sql, params)
        return cur.rowcount
