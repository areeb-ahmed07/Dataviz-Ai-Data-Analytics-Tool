"""
SQLite Connector — handles connecting to SQLite databases (.db, .sqlite, .sqlite3).

Security (Phase 14): Table name validation via identifier quoting.
"""

from __future__ import annotations

import os
import sqlite3
import re
from typing import List, Optional

import pandas as pd

from connectors.base.base_connector import BaseConnector
from connectors.domain.entities import ConnectionConfig, ConnectionResult, QueryConfig


# Valid identifier pattern for table names
_VALID_IDENTIFIER = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')


def _quote_identifier(name: str) -> str:
    """Quote a SQL identifier (table/column name) safely.

    Only allows alphanumeric + underscore. Rejects anything else.
    """
    if not _VALID_IDENTIFIER.match(name):
        raise ValueError(f"Invalid SQL identifier: '{name}'")
    return f'"{name}"'


class SQLiteConnector(BaseConnector):
    """SQLite database connector."""

    def test_connection(self) -> ConnectionResult:
        file_path = self.config.file_path or self.config.database
        if file_path and file_path != ":memory:" and not os.path.exists(file_path):
            return ConnectionResult(
                success=False,
                message=f"SQLite database file not found: {file_path}",
                error="FileNotFoundError",
            )
        try:
            tables = self.get_tables()
            return ConnectionResult(
                success=True,
                message=f"Successfully connected to SQLite database ({len(tables)} tables found)",
                tables=tables,
            )
        except Exception as exc:
            return ConnectionResult(success=False, message=str(exc), error=str(type(exc)))

    def get_tables(self) -> List[str]:
        file_path = self.config.file_path or self.config.database or ":memory:"
        with sqlite3.connect(file_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
            rows = cursor.fetchall()
            return [r[0] for r in rows]

    def load_data(self, query_config: Optional[QueryConfig] = None) -> pd.DataFrame:
        file_path = self.config.file_path or self.config.database or ":memory:"
        if file_path != ":memory:" and not os.path.exists(file_path):
            raise FileNotFoundError(f"SQLite database file not found: {file_path}")

        tables = self.get_tables()
        table_name = query_config.table_name if (query_config and query_config.table_name) else (tables[0] if tables else None)
        sql = query_config.sql_query if (query_config and query_config.sql_query) else None

        with sqlite3.connect(file_path) as conn:
            if sql:
                df = pd.read_sql_query(sql, conn)
            elif table_name:
                limit_clause = f" LIMIT {query_config.limit}" if (query_config and query_config.limit) else ""
                # Phase 14: safe identifier quoting
                safe_table = _quote_identifier(table_name)
                df = pd.read_sql_query(f"SELECT * FROM {safe_table}{limit_clause}", conn)
            else:
                raise ValueError("No table or SQL query specified for SQLite load.")

        return df
