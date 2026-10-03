"""
Data Connectors Module — Public API & Factory pattern orchestrator.

Supports 7 Data Source Types:
  1. CSV (.csv)
  2. Excel (.xlsx, .xls)
  3. SQLite (.db, .sqlite, .sqlite3)
  4. MySQL (SQLAlchemy)
  5. PostgreSQL (SQLAlchemy + psycopg2)
  6. JSON / JSONL (.json, .jsonl)
  7. REST API (HTTP GET JSON endpoints)
"""

from __future__ import annotations

from typing import Dict, Type

from connectors.api_connectors.rest_api_connector import RESTAPIConnector
from connectors.base.base_connector import BaseConnector
from connectors.database_connectors.mysql_connector import MySQLConnector
from connectors.database_connectors.postgresql_connector import PostgreSQLConnector
from connectors.database_connectors.sqlite_connector import SQLiteConnector
from connectors.domain.entities import ConnectionConfig, ConnectionResult, QueryConfig
from connectors.domain.enums import DataSourceType
from connectors.file_connectors.csv_connector import CSVConnector
from connectors.file_connectors.excel_connector import ExcelConnector
from connectors.file_connectors.json_connector import JSONConnector


class ConnectorFactory:
    """
    Factory pattern for instantiating the appropriate BaseConnector instance.
    """

    _REGISTRY: Dict[DataSourceType, Type[BaseConnector]] = {
        DataSourceType.CSV: CSVConnector,
        DataSourceType.EXCEL: ExcelConnector,
        DataSourceType.SQLITE: SQLiteConnector,
        DataSourceType.MYSQL: MySQLConnector,
        DataSourceType.POSTGRESQL: PostgreSQLConnector,
        DataSourceType.JSON: JSONConnector,
        DataSourceType.REST_API: RESTAPIConnector,
    }

    @classmethod
    def create_connector(cls, config: ConnectionConfig) -> BaseConnector:
        connector_cls = cls._REGISTRY.get(config.source_type)
        if not connector_cls:
            raise ValueError(f"No connector registered for source type: {config.source_type}")
        return connector_cls(config)


__all__ = [
    "ConnectorFactory",
    "BaseConnector",
    "DataSourceType",
    "ConnectionConfig",
    "ConnectionResult",
    "QueryConfig",
    "CSVConnector",
    "ExcelConnector",
    "JSONConnector",
    "SQLiteConnector",
    "MySQLConnector",
    "PostgreSQLConnector",
    "RESTAPIConnector",
]
