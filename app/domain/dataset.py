"""
DataViz Pro — Dataset Domain Model

Represents a dataset in the domain layer.
Dataclass used for passing dataset information
between the service layer and templates.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Dict, Any


@dataclass
class ColumnProfile:
    """Profile metadata for a single column."""
    name: str
    dtype: str
    missing_count: int = 0
    missing_pct: float = 0.0
    unique_count: int = 0
    # Numeric stats (optional)
    min_val: Optional[float] = None
    max_val: Optional[float] = None
    mean_val: Optional[float] = None
    median_val: Optional[float] = None
    std_val: Optional[float] = None
    # Categorical stats (optional)
    top_values: Optional[List[str]] = None
    # Sample values
    sample_values: Optional[List[str]] = None


@dataclass
class DatasetDomain:
    """Domain representation of a user-uploaded dataset."""
    id: int
    user_id: int
    name: str
    original_filename: str
    file_format: str
    file_size: Optional[int] = None
    storage_path: Optional[str] = None
    row_count: Optional[int] = None
    column_count: Optional[int] = None
    description: Optional[str] = None
    encoding: Optional[str] = None
    delimiter: Optional[str] = None
    column_info: Optional[List[Dict[str, Any]]] = None
    quality_info: Optional[Dict[str, Any]] = None
    parent_dataset_id: Optional[int] = None
    cleaning_pipeline: Optional[List[Dict[str, Any]]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
