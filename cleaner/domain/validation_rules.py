"""
Domain models for Data Validation Rules and Inspection Reports
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

@dataclass
class ValidationRule:
    """Definition of a single data validation constraint rule"""
    rule_id: str
    column: str
    rule_type: str  # 'non_null', 'range', 'unique', 'regex', 'type', 'allowed_values'
    min_val: Optional[float] = None
    max_val: Optional[float] = None
    regex_pattern: Optional[str] = None
    allowed_values: Optional[List[Any]] = None
    expected_type: Optional[str] = None  # 'numeric', 'string', 'datetime', 'boolean'
    description: Optional[str] = None

@dataclass
class RuleViolation:
    """Details of a failed validation rule"""
    rule_id: str
    column: str
    rule_type: str
    violating_count: int
    violating_percentage: float
    sample_indices: List[Any]
    error_message: str

@dataclass
class ValidationReport:
    """Overall Data Validation Inspection Report"""
    total_rules: int
    passed_rules: int
    failed_rules: int
    violations: List[RuleViolation] = field(default_factory=list)
    overall_passed: bool = True

    @property
    def pass_rate(self) -> float:
        if self.total_rules == 0:
            return 100.0
        return round((self.passed_rules / self.total_rules) * 100.0, 2)
