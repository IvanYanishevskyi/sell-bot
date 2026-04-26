from __future__ import annotations

import sqlite3

from order_bot.db.query_builder import QueryBuilder


class BaseRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.qb = QueryBuilder(conn)
