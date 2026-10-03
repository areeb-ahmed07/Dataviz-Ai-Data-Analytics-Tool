"""
CSV Connector — handles reading CSV files with automatic encoding & delimiter detection.
"""

from __future__ import annotations

import os
from typing import List, Optional

import pandas as pd

from connectors.base.base_connector import BaseConnector
from connectors.domain.entities import ConnectionConfig, ConnectionResult, QueryConfig


class CSVConnector(BaseConnector):
    """CSV file data connector."""

    def test_connection(self) -> ConnectionResult:
        if not self.config.file_path or not os.path.exists(self.config.file_path):
            return ConnectionResult(
                success=False,
                message="CSV file path does not exist.",
                error="FileNotFoundError",
            )
        try:
            df = self.load_data()
            return ConnectionResult(
                success=True,
                message=f"Successfully loaded CSV ({df.shape[0]:,} rows × {df.shape[1]} cols)",
                df=df,
            )
        except Exception as exc:
            return ConnectionResult(success=False, message=str(exc), error=str(type(exc)))

    def get_tables(self) -> List[str]:
        return ["default"]

    def load_data(self, query_config: Optional[QueryConfig] = None) -> pd.DataFrame:
        file_path = self.config.file_path
        if not file_path or not os.path.exists(file_path):
            raise FileNotFoundError(f"CSV file not found: {file_path}")

        encodings = [self.config.encoding, "utf-8", "latin1", "cp1252"]
        delimiters = [self.config.delimiter, ",", ";", "\t", "|"]

        last_exc = None
        for enc in dict.fromkeys(encodings):
            for sep in dict.fromkeys(delimiters):
                try:
                    df = pd.read_csv(file_path, encoding=enc, sep=sep)
                    if not df.empty and len(df.columns) > 1:
                        if query_config and query_config.limit:
                            df = df.head(query_config.limit)
                        return df
                except Exception as exc:
                    last_exc = exc

        # Fallback basic read_csv
        try:
            df = pd.read_csv(file_path)
            if query_config and query_config.limit:
                df = df.head(query_config.limit)
            return df
        except Exception as exc:
            raise last_exc or exc
