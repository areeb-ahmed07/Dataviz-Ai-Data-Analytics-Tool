"""
Abstract Base Connector — interface for all data source connectors.

Single Responsibility: defines contract for testing connection, listing tables/sheets, and loading DataFrame.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

import pandas as pd

from connectors.domain.entities import ConnectionConfig, ConnectionResult, QueryConfig


class BaseConnector(ABC):
    """Abstract base class for all data source connectors."""

    def __init__(self, config: ConnectionConfig) -> None:
        self.config = config

    @abstractmethod
    def test_connection(self) -> ConnectionResult:
        """Test whether the data source is accessible."""
        pass

    @abstractmethod
    def get_tables(self) -> List[str]:
        """List available tables, sheets, or endpoints."""
        pass

    @abstractmethod
    def load_data(self, query_config: Optional[QueryConfig] = None) -> pd.DataFrame:
        """Load data into a pandas DataFrame."""
        pass
