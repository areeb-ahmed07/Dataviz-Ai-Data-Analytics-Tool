"""Domain layer for the Data Connectors module."""

from .enums import DataSourceType
from .entities import ConnectionConfig, ConnectionResult, QueryConfig

__all__ = [
    "DataSourceType",
    "ConnectionConfig",
    "ConnectionResult",
    "QueryConfig",
]
