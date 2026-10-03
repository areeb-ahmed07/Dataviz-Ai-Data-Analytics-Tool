"""
Domain entities for the Data Connectors module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import pandas as pd

from .enums import DataSourceType


@dataclass
class ConnectionConfig:
    """Connection credentials and configuration for a data source."""
    source_type: DataSourceType
    file_path: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    username: Optional[str] = None
    password: Optional[str] = None
    database: Optional[str] = None
    connection_string: Optional[str] = None
    api_url: Optional[str] = None
    headers: Dict[str, str] = field(default_factory=dict)
    params: Dict[str, str] = field(default_factory=dict)
    json_path: Optional[str] = None
    delimiter: str = ","
    encoding: str = "utf-8"
    sheet_name: Union[str, int] = 0


@dataclass
class QueryConfig:
    """Query configuration for databases or APIs."""
    table_name: Optional[str] = None
    sql_query: Optional[str] = None
    limit: Optional[int] = None


@dataclass
class ConnectionResult:
    """Result of testing or executing a data connection."""
    success: bool
    message: str
    df: Optional[pd.DataFrame] = None
    tables: List[str] = field(default_factory=list)
    sheets: List[str] = field(default_factory=list)
    error: Optional[str] = None
