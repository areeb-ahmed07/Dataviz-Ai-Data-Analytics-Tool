"""
Domain enumerations for the Data Connectors module.
"""

from enum import Enum


class DataSourceType(Enum):
    """Supported data source types."""
    CSV = "csv"
    EXCEL = "excel"
    SQLITE = "sqlite"
    MYSQL = "mysql"
    POSTGRESQL = "postgresql"
    JSON = "json"
    REST_API = "rest_api"
