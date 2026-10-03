from typing import Dict, List, Any
from ml.domain.ml_result import ModelResult, LeaderboardEntry

class LeaderboardService:
    def build(self, results: Dict[str, ModelResult], task_type: str, primary_metric: str = None) -> List[LeaderboardEntry]:
        lb = []
        primary_metric = primary_metric or ('accuracy' if task_type == 'classification' else 'r2')
        for name, res in results.items():
            if not res.is_valid or primary_metric not in res.test_metrics:
                continue
                
            test_metrics = res.test_metrics or {}
            cv_metrics = res.cv_result
            
            primary_metric_val = test_metrics.get(primary_metric, cv_metrics.mean_score if cv_metrics else 0.0)
            
            entry = LeaderboardEntry(
                rank=0,
                model_name=name,
                primary_metric_name=primary_metric or "accuracy",
                primary_metric_value=primary_metric_val,
                cv_mean=cv_metrics.mean_score if cv_metrics else 0.0,
                cv_std=cv_metrics.std_score if cv_metrics else 0.0,
                composite_score=primary_metric_val,
                metrics=test_metrics,
                fit_time_seconds=res.fit_time_seconds
            )
            lb.append(entry)
            
        if not lb:
            return []
            
        # Sort by primary metric if available
        lb.sort(key=lambda x: x.primary_metric_value, reverse=primary_metric not in {'rmse', 'mae', 'mape', 'mse'})
        
        # Assign ranks
        for i, entry in enumerate(lb):
            entry.rank = i + 1
            
        return lb
