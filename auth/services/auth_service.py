import datetime
from typing import Tuple, List, Optional
from sqlalchemy.orm import Session
from auth.database import get_session, UserDB, init_db
from auth.domain.user import UserDomain, Role
from auth.security import (
    hash_password,
    verify_password,
    create_access_token,
    decode_access_token,
    sanitize_input
)

class AuthService:
    def __init__(self, db: Optional[Session] = None):
        # Auto-initialize database tables if not exist
        init_db()
        self._db = db or get_session()
        self._seed_default_admin()

    def _seed_default_admin(self):
        """Seed a default administrator if the database is empty.

        Security (Phase 14): Uses a cryptographically secure random password
        instead of hardcoded "admin123". Prints the password to stdout on
        first creation only. Admin must change password on first login.
        """
        try:
            admin_exists = self._db.query(UserDB).first() is not None
            if not admin_exists:
                # Generate a secure random admin password
                import secrets
                admin_password = secrets.token_urlsafe(16)
                default_admin = UserDB(
                    username="admin",
                    email="admin@datavizpro.com",
                    full_name="System Administrator",
                    hashed_password=hash_password(admin_password),
                    role=Role.ADMIN.value,
                    is_active=True,
                    created_at=datetime.datetime.utcnow()
                )
                self._db.add(default_admin)
                self._db.commit()
                print(f"[AuthService] Seeded default admin: admin / {admin_password}")
                print("[AuthService] IMPORTANT: Change this password immediately after first login.")
        except Exception as e:
            self._db.rollback()
            print(f"[AuthService] Seed admin failed: {e}")

    def register_user(
        self, full_name: str, username: str, email: str, password: str
    ) -> Tuple[bool, str, Optional[UserDomain]]:
        """Register a new user account"""
        # Sanitize fields
        full_name = sanitize_input(full_name)
        username = sanitize_input(username).lower()
        email = sanitize_input(email).lower()

        if not full_name or not username or not email or not password:
            return False, "All fields are required.", None

        if len(password) < 8:
            return False, "Password must be at least 8 characters.", None

        try:
            # Check for existing username or email
            existing_user = self._db.query(UserDB).filter(
                (UserDB.username == username) | (UserDB.email == email)
            ).first()

            if existing_user:
                if existing_user.username == username:
                    return False, f"Username '{username}' is already taken.", None
                else:
                    return False, f"Email '{email}' is already registered.", None

            # Create User
            new_user = UserDB(
                username=username,
                email=email,
                full_name=full_name,
                hashed_password=hash_password(password),
                role=Role.USER.value,  # Defaults to standard user
                is_active=True,
                created_at=datetime.datetime.utcnow()
            )

            self._db.add(new_user)
            self._db.commit()
            self._db.refresh(new_user)

            return True, "Registration successful!", new_user.to_domain()

        except Exception as e:
            self._db.rollback()
            return False, f"Database error during registration: {str(e)}", None

    def login_user(self, identifier: str, password: str) -> Tuple[bool, str, Optional[str], Optional[UserDomain]]:
        """Log in a user by username or email. Returns (Success, Message, JWT Token, Domain User)"""
        identifier = sanitize_input(identifier).lower()

        if not identifier or not password:
            return False, "Username/Email and Password are required.", None, None

        try:
            # Retrieve User by username or email
            user = self._db.query(UserDB).filter(
                (UserDB.username == identifier) | (UserDB.email == identifier)
            ).first()

            if not user:
                return False, "Invalid username/email or password.", None, None

            if not user.is_active:
                return False, "Your account has been disabled by an administrator.", None, None

            # Verify password
            if not verify_password(password, user.hashed_password):
                return False, "Invalid username/email or password.", None, None

            # Generate Token
            token_payload = {
                "sub": str(user.id),
                "username": user.username,
                "role": user.role
            }
            token = create_access_token(token_payload)

            return True, "Login successful!", token, user.to_domain()

        except Exception as e:
            return False, f"Login failed: {str(e)}", None, None

    def verify_jwt_token(self, token: str) -> Tuple[bool, str, Optional[UserDomain]]:
        """Verify JWT and return domain user if valid"""
        payload = decode_access_token(token)
        if not payload:
            return False, "Invalid or expired token.", None

        user_id = payload.get("sub")
        if not user_id:
            return False, "Token missing user identifier.", None

        try:
            user = self._db.query(UserDB).filter(UserDB.id == int(user_id)).first()
            if not user:
                return False, "User not found.", None
            if not user.is_active:
                return False, "User account is inactive.", None

            return True, "Token verified.", user.to_domain()
        except Exception as e:
            return False, f"Error retrieving user from token: {e}", None

    def change_password(self, user_id: int, current_password: str, new_password: str) -> Tuple[bool, str]:
        """Change user password"""
        if len(new_password) < 8:
            return False, "New password must be at least 8 characters."

        try:
            user = self._db.query(UserDB).filter(UserDB.id == user_id).first()
            if not user:
                return False, "User not found."

            if not verify_password(current_password, user.hashed_password):
                return False, "Incorrect current password."

            user.hashed_password = hash_password(new_password)
            self._db.commit()
            return True, "Password updated successfully!"

        except Exception as e:
            self._db.rollback()
            return False, f"Failed to change password: {str(e)}"

    def list_all_users(self) -> List[UserDomain]:
        """List all users (Admin operation)"""
        try:
            users = self._db.query(UserDB).order_by(UserDB.created_at.desc()).all()
            return [u.to_domain() for u in users]
        except Exception:
            return []

    def update_user_role(self, target_user_id: int, new_role: Role) -> Tuple[bool, str]:
        """Update a user's role (Admin operation)"""
        try:
            user = self._db.query(UserDB).filter(UserDB.id == target_user_id).first()
            if not user:
                return False, "User not found."

            user.role = new_role.value
            self._db.commit()
            return True, f"User role updated to {new_role.value}."
        except Exception as e:
            self._db.rollback()
            return False, f"Failed to update role: {str(e)}"

    def toggle_user_status(self, target_user_id: int) -> Tuple[bool, str]:
        """Toggle active status of a user (Admin operation)"""
        try:
            user = self._db.query(UserDB).filter(UserDB.id == target_user_id).first()
            if not user:
                return False, "User not found."

            user.is_active = not user.is_active
            self._db.commit()
            status_str = "enabled" if user.is_active else "disabled"
            return True, f"User account has been {status_str}."
        except Exception as e:
            self._db.rollback()
            return False, f"Failed to toggle user status: {str(e)}"

    def update_profile(self, user_id: int, full_name: str, email: str) -> Tuple[bool, str]:
        """Update a user's full name and email address."""
        full_name = sanitize_input(full_name)
        email = sanitize_input(email).lower()

        if not full_name or len(full_name) < 2:
            return False, "Full name must be at least 2 characters."
        if not email:
            return False, "Email address is required."

        try:
            user = self._db.query(UserDB).filter(UserDB.id == user_id).first()
            if not user:
                return False, "User not found."

            # Check for email collision with another user
            existing = self._db.query(UserDB).filter(
                UserDB.email == email,
                UserDB.id != user_id,
            ).first()
            if existing:
                return False, "That email address is already in use by another account."

            user.full_name = full_name
            user.email = email
            self._db.commit()
            return True, "Profile updated successfully."

        except Exception as e:
            self._db.rollback()
            return False, f"Failed to update profile: {str(e)}"

    def get_system_stats(self) -> dict:
        """Get database usage stats (Admin operation)"""
        from auth.database import ProjectDB, AnalysisDB
        try:
            total_users = self._db.query(UserDB).count()
            active_users = self._db.query(UserDB).filter(UserDB.is_active == True).count()
            admin_users = self._db.query(UserDB).filter(UserDB.role == Role.ADMIN.value).count()
            total_projects = self._db.query(ProjectDB).count()
            total_analyses = self._db.query(AnalysisDB).count()

            return {
                "total_users": total_users,
                "active_users": active_users,
                "admin_users": admin_users,
                "total_projects": total_projects,
                "total_analyses": total_analyses
            }
        except Exception as e:
            print(f"[AuthService] Error fetching system stats: {e}")
            return {
                "total_users": 0,
                "active_users": 0,
                "admin_users": 0,
                "total_projects": 0,
                "total_analyses": 0
            }

    def update_preferences(self, user_id: int, theme: str, notifications_enabled: bool) -> Tuple[bool, str]:
        """Update user preferences for theme and notifications."""
        try:
            user = self._db.query(UserDB).filter(UserDB.id == user_id).first()
            if not user:
                return False, "User not found."

            if theme not in ["light", "dark", "system"]:
                return False, "Invalid theme selection."

            user.theme = theme
            user.notifications_enabled = notifications_enabled
            self._db.commit()
            return True, "Preferences updated successfully."
        except Exception as e:
            self._db.rollback()
            return False, f"Failed to update preferences: {str(e)}"
