"""
Domain models for Data Cleaning Configurations
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Union, Tuple

@dataclass
class DuplicateConfig:
    """Configuration for Duplicate Removal"""
    subset: Optional[List[str]] = None
    keep: Union[str, bool] = 'first'  # 'first', 'last', False (remove all)
    fuzzy_enable: bool = False
    fuzzy_columns: Optional[List[str]] = None
    fuzzy_threshold: float = 0.85  # Similarity ratio between 0 and 1

@dataclass
class ImputationConfig:
    """Configuration for Missing Value Imputation"""
    # Mapping of column name to strategy ('mean', 'median', 'mode', 'constant', 'knn', 'ffill', 'bfill')
    column_strategies: Dict[str, str] = field(default_factory=dict)
    default_numeric_strategy: str = 'median'  # 'mean', 'median', 'mode', 'constant', 'knn', 'ffill', 'bfill'
    default_categorical_strategy: str = 'mode'  # 'mode', 'constant', 'ffill', 'bfill'
    constant_value: Any = "Missing"
    numeric_constant: float = 0.0
    knn_neighbors: int = 5
    group_by_col: Optional[str] = None
    drop_threshold_cols: Optional[float] = None  # Drop col if missing % > threshold (e.g. 0.5)
    drop_threshold_rows: Optional[float] = None  # Drop row if missing % > threshold

@dataclass
class OutlierConfig:
    """Configuration for Outlier Detection and Capping/Trimming"""
    method: str = 'iqr'  # 'iqr', 'zscore', 'isolation_forest', 'lof'
    action: str = 'cap'   # 'cap' (Winsorization) or 'drop' (Trimming)
    columns: Optional[List[str]] = None
    iqr_multiplier: float = 1.5
    zscore_threshold: float = 3.0
    contamination: float = 0.05  # For Isolation Forest & LOF

@dataclass
class EncodingConfig:
    """Configuration for Categorical Encoding"""
    strategy: str = 'onehot'  # 'onehot', 'ordinal', 'frequency', 'target'
    columns: Optional[List[str]] = None
    target_col: Optional[str] = None  # Required for target encoding
    drop_first: bool = True           # For One-Hot Encoding

@dataclass
class ScalingConfig:
    """Configuration for Feature Scaling & Normalization"""
    strategy: str = 'standard'  # 'standard', 'minmax', 'robust', 'maxabs', 'quantile', 'power'
    columns: Optional[List[str]] = None
    feature_range: Tuple[float, float] = (0.0, 1.0)  # For MinMaxScaler

