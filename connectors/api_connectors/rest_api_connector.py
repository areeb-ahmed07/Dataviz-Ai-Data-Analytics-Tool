"""
REST API Connector — handles executing HTTP GET requests & loading JSON responses into pandas DataFrames.
"""

from __future__ import annotations

import json
from typing import List, Optional

import pandas as pd
import requests

from connectors.base.base_connector import BaseConnector
from connectors.domain.entities import ConnectionConfig, ConnectionResult, QueryConfig


class RESTAPIConnector(BaseConnector):
    """REST API endpoint data connector."""

    def test_connection(self) -> ConnectionResult:
        url = self.config.api_url
        if not url or not url.startswith(("http://", "https://")):
            return ConnectionResult(
                success=False,
                message="Invalid REST API URL. Must start with http:// or https://",
                error="ValueError",
            )
        try:
            resp = requests.get(url, headers=self.config.headers, params=self.config.params, timeout=10)
            if resp.status_code == 200:
                df = self.load_data()
                return ConnectionResult(
                    success=True,
                    message=f"Successfully fetched API data ({df.shape[0]:,} rows × {df.shape[1]} cols)",
                    df=df,
                )
            else:
                return ConnectionResult(
                    success=False,
                    message=f"HTTP Status {resp.status_code}: {resp.reason}",
                    error=f"HTTPError_{resp.status_code}",
                )
        except Exception as exc:
            return ConnectionResult(success=False, message=str(exc), error=str(type(exc)))

    def get_tables(self) -> List[str]:
        return ["endpoint"]

    def load_data(self, query_config: Optional[QueryConfig] = None) -> pd.DataFrame:
        url = self.config.api_url
        if not url:
            raise ValueError("API URL is required.")

        resp = requests.get(url, headers=self.config.headers, params=self.config.params, timeout=15)
        resp.raise_for_status()

        payload = resp.json()

        if isinstance(payload, list):
            df = pd.json_normalize(payload)
        elif isinstance(payload, dict):
            key = self.config.json_path
            if key and key in payload and isinstance(payload[key], list):
                df = pd.json_normalize(payload[key])
            else:
                # Find first list key inside JSON dictionary (e.g., 'data', 'items', 'results')
                list_key = next(
                    (k for k, v in payload.items() if isinstance(v, list) and len(v) > 0), None
                )
                if list_key:
                    df = pd.json_normalize(payload[list_key])
                else:
                    df = pd.json_normalize([payload])
        else:
            raise ValueError("API response is not a valid JSON object or list.")

        if query_config and query_config.limit:
            df = df.head(query_config.limit)

        return df
