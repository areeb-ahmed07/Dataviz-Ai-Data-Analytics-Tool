"""
PostgreSQL Connector — handles connecting to PostgreSQL databases using SQLAlchemy + psycopg2.
"""

from __future__ import annotations

import re
from typing import List, Optional

import pandas as pd

from connectors.base.base_connector import BaseConnector
from connectors.domain.entities import ConnectionConfig, ConnectionResult, QueryConfig

try:
    import sqlalchemy
    from sqlalchemy import inspect
    SQLALCHEMY_AVAILABLE = True
except ImportError:
    SQLALCHEMY_AVAILABLE = False


# Valid identifier pattern for table names (Phase 14)
_VALID_IDENTIFIER = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')


def _quote_identifier(name: str) -> str:
    """Quote a SQL identifier safely. Only allows alphanumeric + underscore."""
    if not _VALID_IDENTIFIER.match(name):
        raise ValueError(f"Invalid SQL identifier: '{name}'")
    return f'"{name}"'


class PostgreSQLConnector(BaseConnector):
    """PostgreSQL database connector."""

    def _get_engine(self):
        if not SQLALCHEMY_AVAILABLE:
            raise RuntimeError("SQLAlchemy is required for PostgreSQL connection.")

        if self.config.connection_string:
            return sqlalchemy.create_engine(self.config.connection_string)

        host = self.config.host or "localhost"
        port = self.config.port or 5432
        user = self.config.username or "postgres"
        pwd = self.config.password or ""
        db = self.config.database or "postgres"

        url = f"postgresql+psycopg2://{user}:{pwd}@{host}:{port}/{db}"
        return sqlalchemy.create_engine(url)

    def test_connection(self) -> ConnectionResult:
        if not SQLALCHEMY_AVAILABLE:
            return ConnectionResult(
                success=False,
                message="SQLAlchemy is not installed. Run: pip install sqlalchemy psycopg2-binary",
                error="ImportError",
            )
        try:
            engine = self._get_engine()
            with engine.connect() as conn:
                tables = inspect(engine).get_table_names()
                return ConnectionResult(
                    success=True,
                    message=f"Successfully connected to PostgreSQL database ({len(tables)} tables found)",
                    tables=tables,
                )
        except Exception as exc:
            return ConnectionResult(success=False, message=str(exc), error=str(type(exc)))

    def get_tables(self) -> List[str]:
        try:
            engine = self._get_engine()
            return inspect(engine).get_table_names()
        except Exception:
            return []

    def load_data(self, query_config: Optional[QueryConfig] = None) -> pd.DataFrame:
        engine = self._get_engine()
        tables = self.get_tables()

        table_name = query_config.table_name if (query_config and query_config.table_name) else (tables[0] if tables else None)
        sql = query_config.sql_query if (query_config and query_config.sql_query) else None

        with engine.connect() as conn:
            if sql:
                return pd.read_sql_query(sql, conn)
            elif table_name:
                limit_clause = f" LIMIT {query_config.limit}" if (query_config and query_config.limit) else ""
                # Phase 14: safe identifier quoting
                safe_table = _quote_identifier(table_name)
                return pd.read_sql_query(f"SELECT * FROM {safe_table}{limit_clause}", conn)
            else:
                raise ValueError("No table or SQL query specified for PostgreSQL load.")
