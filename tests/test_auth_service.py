import unittest
import os
import shutil
import datetime
import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from auth.database import Base, UserDB, ProjectDB, AnalysisDB
from auth.services.auth_service import AuthService
from auth.services.project_service import ProjectService
from auth.domain.user import Role
from auth.security import decode_access_token

class TestAuthModule(unittest.TestCase):
    def setUp(self):
        # Create in-memory database session
        self.engine = create_engine("sqlite:///:memory:")
        Session = sessionmaker(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)
        self.db = Session()
        
        # Instantiate services with test database session
        self.auth_service = AuthService(db=self.db)
        self.test_projects_dir = "temp_test_projects"
        self.project_service = ProjectService(db=self.db, base_dir=self.test_projects_dir)

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        
        # Clean up temporary test files directory
        if os.path.exists(self.test_projects_dir):
            shutil.rmtree(self.test_projects_dir)
            
    def test_default_admin_seeded(self):
        """Verify that default admin is automatically seeded when empty"""
        admin = self.db.query(UserDB).filter(UserDB.username == "admin").first()
        self.assertIsNotNone(admin)
        self.assertEqual(admin.role, Role.ADMIN.value)
        self.assertEqual(admin.email, "admin@datavizpro.com")

    def test_register_user_success(self):
        """Test successful registration of a user account"""
        success, msg, user = self.auth_service.register_user(
            full_name="Alice Green",
            username="alice",
            email="alice@test.com",
            password="alicepassword"
        )
        self.assertTrue(success)
        self.assertEqual(msg, "Registration successful!")
        self.assertIsNotNone(user)
        self.assertEqual(user.username, "alice")
        self.assertEqual(user.role, Role.USER)

        # Check DB record exists
        user_db = self.db.query(UserDB).filter(UserDB.username == "alice").first()
        self.assertIsNotNone(user_db)
        self.assertEqual(user_db.full_name, "Alice Green")

    def test_register_duplicate_username_or_email(self):
        """Test registration fails with duplicate username or email"""
        # Register first user
        self.auth_service.register_user("Alice", "alice", "alice@test.com", "password")
        
        # Duplicate username
        success, msg, _ = self.auth_service.register_user("Alice Copy", "alice", "alice2@test.com", "password")
        self.assertFalse(success)
        self.assertIn("already taken", msg)

        # Duplicate email
        success, msg, _ = self.auth_service.register_user("Alice Copy", "alice2", "alice@test.com", "password")
        self.assertFalse(success)
        self.assertIn("already registered", msg)

    def test_register_invalid_password(self):
        """Test registration fails with too short passwords"""
        success, msg, _ = self.auth_service.register_user("Short", "short", "short@test.com", "123")
        self.assertFalse(success)
        self.assertIn("Password must be at least 8 characters", msg)

    def test_login_success(self):
        """Test logging in with valid credentials"""
        # Register a test user
        self.auth_service.register_user("Bob Smith", "bob", "bob@test.com", "bobpassword")
        
        # Log in
        success, msg, token, user = self.auth_service.login_user("bob", "bobpassword")
        self.assertTrue(success)
        self.assertEqual(msg, "Login successful!")
        self.assertIsNotNone(token)
        self.assertEqual(user.username, "bob")
        
        # Verify JWT token payload
        payload = decode_access_token(token)
        self.assertIsNotNone(payload)
        self.assertEqual(payload.get("username"), "bob")
        self.assertEqual(payload.get("role"), Role.USER.value)

    def test_login_by_email(self):
        """Test logging in with email address identifier"""
        self.auth_service.register_user("Bob Smith", "bob", "bob@test.com", "bobpassword")
        
        success, _, token, _ = self.auth_service.login_user("bob@test.com", "bobpassword")
        self.assertTrue(success)
        self.assertIsNotNone(token)

    def test_login_invalid_credentials(self):
        """Test logging in with invalid username or password"""
        self.auth_service.register_user("Bob Smith", "bob", "bob@test.com", "bobpassword")
        
        # Wrong password
        success, msg, _, _ = self.auth_service.login_user("bob", "wrongpassword")
        self.assertFalse(success)
        self.assertIn("Invalid username/email or password", msg)
        
        # Wrong username
        success, msg, _, _ = self.auth_service.login_user("nonexistent", "bobpassword")
        self.assertFalse(success)
        self.assertIn("Invalid username/email or password", msg)

    def test_login_disabled_user(self):
        """Test logging in fails if user is disabled by administrator"""
        _, _, user = self.auth_service.register_user("Bob Smith", "bob", "bob@test.com", "bobpassword")
        
        # Disable user
        self.auth_service.toggle_user_status(user.id)
        
        success, msg, _, _ = self.auth_service.login_user("bob", "bobpassword")
        self.assertFalse(success)
        self.assertIn("disabled", msg)

    def test_change_password(self):
        """Test changing user password"""
        _, _, user = self.auth_service.register_user("Bob", "bob", "bob@test.com", "bobpassword")
        
        # Success change
        success, msg = self.auth_service.change_password(user.id, "bobpassword", "newpassword")
        self.assertTrue(success)
        self.assertEqual(msg, "Password updated successfully!")
        
        # Try logging in with new password
        login_success, _, _, _ = self.auth_service.login_user("bob", "newpassword")
        self.assertTrue(login_success)

    def test_jwt_verification(self):
        """Test JWT validation logic"""
        self.auth_service.register_user("Alice", "alice", "alice@test.com", "password")
        _, _, token, _ = self.auth_service.login_user("alice", "password")
        
        # Verify valid token
        success, msg, user = self.auth_service.verify_jwt_token(token)
        self.assertTrue(success)
        self.assertEqual(user.username, "alice")
        
        # Verify invalid token
        success, msg, user = self.auth_service.verify_jwt_token("invalid.token.signature")
        self.assertFalse(success)
        self.assertIsNone(user)

    def test_admin_list_users(self):
        """Test that list users returns all users"""
        users_before = len(self.auth_service.list_all_users())
        self.auth_service.register_user("Alice", "alice", "alice@test.com", "password")
        self.auth_service.register_user("Bob", "bob", "bob@test.com", "password")
        
        users = self.auth_service.list_all_users()
        self.assertEqual(len(users), users_before + 2)

    def test_admin_update_role(self):
        """Test admin role modifications"""
        _, _, user = self.auth_service.register_user("User", "testuser", "test@test.com", "password")
        self.assertEqual(user.role, Role.USER)
        
        # Upgrade to admin
        success, msg = self.auth_service.update_user_role(user.id, Role.ADMIN)
        self.assertTrue(success)
        
        # Verify updated in DB
        updated_user = self.db.query(UserDB).filter(UserDB.id == user.id).first().to_domain()
        self.assertEqual(updated_user.role, Role.ADMIN)

    def test_save_project(self):
        """Test saving dataset files and DB logging"""
        # Mock dataframe
        df = pd.DataFrame({"col1": [1, 2, 3], "col2": ["A", "B", "C"]})
        
        success, msg, project = self.project_service.save_project(
            user_id=1,
            project_name="E-Commerce Sales",
            df=df
        )
        
        self.assertTrue(success)
        self.assertIsNotNone(project)
        self.assertEqual(project.project_name, "E-Commerce Sales")
        self.assertEqual(project.row_count, 3)
        self.assertEqual(project.col_count, 2)
        
        # Verify saved on disk
        self.assertTrue(os.path.exists(project.dataset_path))
        
        # Verify logged in DB
        proj_db = self.db.query(ProjectDB).filter(ProjectDB.id == project.id).first()
        self.assertIsNotNone(proj_db)
        
    def test_log_analysis(self):
        """Test analysis history logging"""
        success, msg, analysis = self.project_service.log_analysis(
            user_id=1,
            project_id=10,
            analysis_type="AutoML Benchmarking",
            summary_metrics={"accuracy": 0.94, "r2": 0.88},
            report_path="reports/output.html"
        )
        
        self.assertTrue(success)
        self.assertIsNotNone(analysis)
        self.assertEqual(analysis.analysis_type, "AutoML Benchmarking")
        self.assertEqual(analysis.summary_metrics.get("accuracy"), 0.94)
        
        # Verify logged in DB
        analysis_db = self.db.query(AnalysisDB).filter(AnalysisDB.id == analysis.id).first()
        self.assertIsNotNone(analysis_db)
        self.assertEqual(analysis_db.to_domain().summary_metrics.get("r2"), 0.88)

    def test_delete_project_removes_file(self):
        """Test that deleting a project cascades and deletes files on disk"""
        df = pd.DataFrame({"a": [1]})
        _, _, project = self.project_service.save_project(1, "DeleteMe", df)
        file_path = project.dataset_path
        self.assertTrue(os.path.exists(file_path))
        
        # Delete project
        success, msg = self.project_service.delete_project(project.id, 1)
        self.assertTrue(success)
        
        # Verify removed from DB
        proj_db = self.db.query(ProjectDB).filter(ProjectDB.id == project.id).first()
        self.assertIsNone(proj_db)
        
        # Verify removed from disk
        self.assertFalse(os.path.exists(file_path))

if __name__ == "__main__":
    unittest.main()
