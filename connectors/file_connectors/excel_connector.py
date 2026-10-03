"""
Excel Connector — handles reading Excel files (.xlsx, .xls) with multi-sheet support.
"""

from __future__ import annotations

import os
from typing import List, Optional

import pandas as pd

from connectors.base.base_connector import BaseConnector
from connectors.domain.entities import ConnectionConfig, ConnectionResult, QueryConfig


class ExcelConnector(BaseConnector):
    """Excel file data connector."""

    def test_connection(self) -> ConnectionResult:
        if not self.config.file_path or not os.path.exists(self.config.file_path):
            return ConnectionResult(
                success=False,
                message="Excel file path does not exist.",
                error="FileNotFoundError",
            )
        try:
            sheets = self.get_tables()
            df = self.load_data()
            return ConnectionResult(
                success=True,
                message=f"Successfully loaded Excel sheet ({df.shape[0]:,} rows × {df.shape[1]} cols)",
                df=df,
                sheets=sheets,
            )
        except Exception as exc:
            return ConnectionResult(success=False, message=str(exc), error=str(type(exc)))

    def get_tables(self) -> List[str]:
        file_path = self.config.file_path
        if not file_path or not os.path.exists(file_path):
            return []
        try:
            xl = pd.ExcelFile(file_path)
            return xl.sheet_names
        except Exception:
            return ["Sheet1"]

    def load_data(self, query_config: Optional[QueryConfig] = None) -> pd.DataFrame:
        file_path = self.config.file_path
        if not file_path or not os.path.exists(file_path):
            raise FileNotFoundError(f"Excel file not found: {file_path}")

        sheet_name = self.config.sheet_name
        if query_config and query_config.table_name:
            sheet_name = query_config.table_name

        try:
            df = pd.read_excel(file_path, sheet_name=sheet_name, engine="openpyxl")
        except Exception:
            df = pd.read_excel(file_path, sheet_name=sheet_name)

        if query_config and query_config.limit:
            df = df.head(query_config.limit)

        return df
