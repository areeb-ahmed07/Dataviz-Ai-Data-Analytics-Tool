"""
JSON Connector — handles reading JSON & JSONL files with normalization for nested payloads.
"""

from __future__ import annotations

import json
import os
from typing import List, Optional

import pandas as pd

from connectors.base.base_connector import BaseConnector
from connectors.domain.entities import ConnectionConfig, ConnectionResult, QueryConfig


class JSONConnector(BaseConnector):
    """JSON / JSONL data connector."""

    def test_connection(self) -> ConnectionResult:
        if not self.config.file_path or not os.path.exists(self.config.file_path):
            return ConnectionResult(
                success=False,
                message="JSON file path does not exist.",
                error="FileNotFoundError",
            )
        try:
            df = self.load_data()
            return ConnectionResult(
                success=True,
                message=f"Successfully loaded JSON data ({df.shape[0]:,} rows × {df.shape[1]} cols)",
                df=df,
            )
        except Exception as exc:
            return ConnectionResult(success=False, message=str(exc), error=str(type(exc)))

    def get_tables(self) -> List[str]:
        return ["root"]

    def load_data(self, query_config: Optional[QueryConfig] = None) -> pd.DataFrame:
        file_path = self.config.file_path
        if not file_path or not os.path.exists(file_path):
            raise FileNotFoundError(f"JSON file not found: {file_path}")

        # 1. Try reading as standard JSON array or object
        try:
            with open(file_path, "r", encoding=self.config.encoding) as f:
                payload = json.load(f)

            if isinstance(payload, list):
                df = pd.json_normalize(payload)
            elif isinstance(payload, dict):
                # If json_path specified or nested key
                key = self.config.json_path
                if key and key in payload and isinstance(payload[key], list):
                    df = pd.json_normalize(payload[key])
                else:
                    # Look for first list inside root object
                    list_key = next((k for k, v in payload.items() if isinstance(v, list)), None)
                    if list_key:
                        df = pd.json_normalize(payload[list_key])
                    else:
                        df = pd.json_normalize([payload])
            else:
                df = pd.read_json(file_path)
        except Exception:
            # 2. Try JSON Lines (JSONL)
            try:
                df = pd.read_json(file_path, lines=True)
            except Exception as exc:
                raise ValueError(f"Could not parse JSON file: {exc}")

        if query_config and query_config.limit:
            df = df.head(query_config.limit)

        return df
