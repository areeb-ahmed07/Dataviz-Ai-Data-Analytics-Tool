import datetime
from dataclasses import dataclass
from typing import Optional, Dict, Any

@dataclass
class ProjectDomain:
    id: Optional[int]
    user_id: int
    project_name: str
    dataset_path: str
    row_count: Optional[int] = None
    col_count: Optional[int] = None
    file_size_kb: Optional[float] = None
    created_at: Optional[datetime.datetime] = None

@dataclass
class AnalysisDomain:
    id: Optional[int]
    user_id: int
    project_id: Optional[int]
    analysis_type: str
    summary_metrics: Dict[str, Any]
    report_path: str
    created_at: Optional[datetime.datetime] = None
