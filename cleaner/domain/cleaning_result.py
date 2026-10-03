"""
Domain models for Data Cleaning Results and Audit Trail
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any, Optional
import pandas as pd

@dataclass
class AuditEntry:
    """Represents a single cleaning operation step in audit log"""
    timestamp: str
    operation: str
    details: str
    rows_before: int
    rows_after: int
    cols_before: int
    cols_after: int
    affected_columns: List[str] = field(default_factory=list)

@dataclass
class CleaningResult:
    """Result of a cleaning execution step or entire pipeline"""
    df_cleaned: pd.DataFrame
    rows_before: int
    rows_after: int
    cols_before: int
    cols_after: int
    duration_seconds: float
    audit_entries: List[AuditEntry] = field(default_factory=list)
    success: bool = True
    error_message: Optional[str] = None

    @property
    def rows_changed(self) -> int:
        return self.rows_before - self.rows_after

    @property
    def cols_changed(self) -> int:
        return self.cols_before - self.cols_after
