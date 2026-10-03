"""
Service: Data Validation & Constraint Engine
"""
import re
from typing import List, Dict, Any
import pandas as pd
import numpy as np

from cleaner.domain.validation_rules import ValidationRule, RuleViolation, ValidationReport

class DataValidatorService:
    """Service to validate data against custom constraints and schemas"""

    def validate(self, df: pd.DataFrame, rules: List[ValidationRule]) -> ValidationReport:
        violations: List[RuleViolation] = []
        passed_count = 0

        for rule in rules:
            if rule.column not in df.columns:
                violations.append(RuleViolation(
                    rule_id=rule.rule_id,
                    column=rule.column,
                    rule_type=rule.rule_type,
                    violating_count=len(df),
                    violating_percentage=100.0,
                    sample_indices=[],
                    error_message=f"Column '{rule.column}' missing from dataset."
                ))
                continue

            col_data = df[rule.column]
            violating_mask = pd.Series(False, index=df.index)

            # Rule 1: Non-Null Check
            if rule.rule_type == 'non_null':
                violating_mask = col_data.isnull()

            # Rule 2: Range Check (Min / Max bounds)
            elif rule.rule_type == 'range':
                numeric_data = pd.to_numeric(col_data, errors='coerce')
                min_fail = (numeric_data < rule.min_val) if rule.min_val is not None else False
                max_fail = (numeric_data > rule.max_val) if rule.max_val is not None else False
                violating_mask = min_fail | max_fail

            # Rule 3: Unique Constraint
            elif rule.rule_type == 'unique':
                violating_mask = col_data.duplicated(keep=False)

            # Rule 4: Regex Pattern Matching
            elif rule.rule_type == 'regex' and rule.regex_pattern:
                try:
                    pattern = re.compile(rule.regex_pattern)
                    str_data = col_data.astype(str)
                    violating_mask = ~str_data.apply(lambda x: bool(pattern.match(x)) if pd.notnull(x) else True)
                except Exception:
                    pass

            # Rule 5: Allowed Values Check
            elif rule.rule_type == 'allowed_values' and rule.allowed_values is not None:
                violating_mask = ~col_data.isin(rule.allowed_values) & col_data.notnull()

            # Rule 6: Type Check
            elif rule.rule_type == 'type' and rule.expected_type:
                exp_type = rule.expected_type.lower()
                if exp_type == 'numeric':
                    violating_mask = pd.to_numeric(col_data, errors='coerce').isnull() & col_data.notnull()
                elif exp_type == 'datetime':
                    violating_mask = pd.to_datetime(col_data, errors='coerce').isnull() & col_data.notnull()

            num_violating = int(violating_mask.sum())
            if num_violating > 0:
                sample_indices = df.index[violating_mask].tolist()[:5]
                violations.append(RuleViolation(
                    rule_id=rule.rule_id,
                    column=rule.column,
                    rule_type=rule.rule_type,
                    violating_count=num_violating,
                    violating_percentage=round((num_violating / len(df) * 100.0) if len(df) > 0 else 0.0, 2),
                    sample_indices=sample_indices,
                    error_message=rule.description or f"Failed {rule.rule_type} validation on {num_violating:,} row(s)."
                ))
            else:
                passed_count += 1

        total_rules = len(rules)
        overall_passed = (len(violations) == 0)

        return ValidationReport(
            total_rules=total_rules,
            passed_rules=passed_count,
            failed_rules=len(violations),
            violations=violations,
            overall_passed=overall_passed
        )

    def auto_generate_rules(self, df: pd.DataFrame) -> List[ValidationRule]:
        """Automatically suggest validation rules based on current DataFrame schema"""
        rules = []

        # 1. Non-null rules for columns with no missing values currently
        for col in df.columns:
            if df[col].isnull().sum() == 0:
                rules.append(ValidationRule(
                    rule_id=f"rule_non_null_{col}",
                    column=col,
                    rule_type='non_null',
                    description=f"Column '{col}' must contain no null values."
                ))

        # 2. Range rules for numerical columns
        for col in df.select_dtypes(include=[np.number]).columns:
            series = df[col].dropna()
            if len(series) > 0:
                min_v = float(series.min())
                max_v = float(series.max())
                # Extend bounds slightly
                padding = (max_v - min_v) * 0.1 if max_v != min_v else 1.0
                rules.append(ValidationRule(
                    rule_id=f"rule_range_{col}",
                    column=col,
                    rule_type='range',
                    min_val=min_v - padding,
                    max_val=max_v + padding,
                    description=f"Column '{col}' should be within range [{round(min_v - padding, 2)}, {round(max_v + padding, 2)}]."
                ))

        # 3. Unique rule for primary key candidates
        for col in df.columns:
            if df[col].nunique() == len(df) and len(df) > 0:
                rules.append(ValidationRule(
                    rule_id=f"rule_unique_{col}",
                    column=col,
                    rule_type='unique',
                    description=f"Column '{col}' must contain unique values (Key Candidate)."
                ))

        return rules
