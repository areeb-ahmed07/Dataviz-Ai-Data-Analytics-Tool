import os
import datetime
import json
import pandas as pd
from typing import List, Tuple, Optional, Dict, Any
from sqlalchemy.orm import Session
from auth.database import get_session, ProjectDB, AnalysisDB, UserDB
from auth.domain.project import ProjectDomain, AnalysisDomain
from auth.security import sanitize_input

class ProjectService:
    def __init__(self, db: Optional[Session] = None, base_dir: str = "saved_projects"):
        self._db = db or get_session()
        self._base_dir = base_dir
        os.makedirs(self._base_dir, exist_ok=True)

    def save_project(self, user_id: int, project_name: str, df: pd.DataFrame) -> Tuple[bool, str, Optional[ProjectDomain]]:
        """Save a dataset to disk and log it in the database as a Project"""
        project_name = sanitize_input(project_name)
        if not project_name:
            return False, "Project name is required.", None

        # Sanitize filename
        safe_name = "".join(c for c in project_name if c.isalnum() or c in (" ", "_", "-")).strip()
        safe_name = safe_name.replace(" ", "_")
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{safe_name}_{timestamp}.csv"

        user_dir = os.path.join(self._base_dir, str(user_id))
        os.makedirs(user_dir, exist_ok=True)
        file_path = os.path.join(user_dir, filename)

        try:
            # Save file to disk
            df.to_csv(file_path, index=False)

            # Get file details
            row_count = len(df)
            col_count = len(df.columns)
            file_size_kb = os.path.getsize(file_path) / 1024.0

            # Save project to DB
            project_db = ProjectDB(
                user_id=user_id,
                project_name=project_name,
                dataset_path=file_path,
                row_count=row_count,
                col_count=col_count,
                file_size_kb=round(file_size_kb, 2),
                created_at=datetime.datetime.utcnow()
            )

            self._db.add(project_db)
            self._db.commit()
            self._db.refresh(project_db)

            return True, "Project saved successfully!", project_db.to_domain()

        except Exception as e:
            self._db.rollback()
            # Clean up saved file if DB fails
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except Exception:
                    pass
            return False, f"Failed to save project: {str(e)}", None

    def get_user_projects(self, user_id: int) -> List[ProjectDomain]:
        """Fetch all saved projects for a user"""
        try:
            projects = self._db.query(ProjectDB).filter(ProjectDB.user_id == user_id).order_by(ProjectDB.created_at.desc()).all()
            return [p.to_domain() for p in projects]
        except Exception:
            return []

    def get_project_by_id(self, project_id: int, user_id: int) -> Optional[ProjectDomain]:
        """Fetch a specific project checking ownership"""
        try:
            project = self._db.query(ProjectDB).filter(
                ProjectDB.id == project_id, ProjectDB.user_id == user_id
            ).first()
            return project.to_domain() if project else None
        except Exception:
            return None

    def delete_project(self, project_id: int, user_id: int) -> Tuple[bool, str]:
        """Delete project DB record and corresponding file from disk"""
        try:
            project = self._db.query(ProjectDB).filter(
                ProjectDB.id == project_id, ProjectDB.user_id == user_id
            ).first()

            if not project:
                return False, "Project not found or access denied."

            # Delete file on disk
            file_path = project.dataset_path
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except Exception as fe:
                    print(f"[ProjectService] Warning: Could not delete file {file_path}: {fe}")

            # Delete from DB
            self._db.delete(project)
            self._db.commit()
            return True, "Project deleted successfully."

        except Exception as e:
            self._db.rollback()
            return False, f"Failed to delete project: {str(e)}"

    def log_analysis(
        self, user_id: int, project_id: Optional[int], analysis_type: str, summary_metrics: Dict[str, Any], report_path: str
    ) -> Tuple[bool, str, Optional[AnalysisDomain]]:
        """Log an analysis run record"""
        try:
            analysis_db = AnalysisDB(
                user_id=user_id,
                project_id=project_id,
                analysis_type=analysis_type,
                summary_metrics=json.dumps(summary_metrics),
                report_path=report_path,
                created_at=datetime.datetime.utcnow()
            )

            self._db.add(analysis_db)
            self._db.commit()
            self._db.refresh(analysis_db)

            return True, "Analysis run logged.", analysis_db.to_domain()

        except Exception as e:
            self._db.rollback()
            return False, f"Failed to log analysis: {str(e)}", None

    def get_user_recent_analyses(self, user_id: int, limit: int = 15) -> List[AnalysisDomain]:
        """Retrieve recent analysis runs logged by a user"""
        try:
            analyses = self._db.query(AnalysisDB).filter(
                AnalysisDB.user_id == user_id
            ).order_by(AnalysisDB.created_at.desc()).limit(limit).all()
            return [a.to_domain() for a in analyses]
        except Exception:
            return []

    def delete_analysis(self, analysis_id: int, user_id: int) -> Tuple[bool, str]:
        """Delete an analysis run log entry"""
        try:
            analysis = self._db.query(AnalysisDB).filter(
                AnalysisDB.id == analysis_id, AnalysisDB.user_id == user_id
            ).first()

            if not analysis:
                return False, "Analysis record not found."

            self._db.delete(analysis)
            self._db.commit()
            return True, "Analysis history item removed."
        except Exception as e:
            self._db.rollback()
            return False, f"Failed to delete analysis record: {str(e)}"
