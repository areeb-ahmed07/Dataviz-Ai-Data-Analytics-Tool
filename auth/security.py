import os
import datetime
import secrets
from typing import Dict, Any, Optional
import jwt
import bcrypt
import bleach
from dotenv import load_dotenv

load_dotenv()

# JWT Config
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if not JWT_SECRET_KEY:
    # Use a persistent file or system env, otherwise fallback to runtime random token
    # To keep user sessions alive across app reload, we write/read a random key from a temp file if not set in .env
    token_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".session_key")
    if os.path.exists(token_file):
        try:
            with open(token_file, "r") as f:
                JWT_SECRET_KEY = f.read().strip()
        except Exception:
            pass
    if not JWT_SECRET_KEY:
        JWT_SECRET_KEY = secrets.token_urlsafe(64)
        try:
            with open(token_file, "w") as f:
                f.write(JWT_SECRET_KEY)
        except Exception:
            pass

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours

def hash_password(password: str) -> str:
    """Hash password using bcrypt"""
    pwd_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(pwd_bytes, salt)
    return hashed.decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against bcrypt hash"""
    try:
        return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
    except Exception:
        return False

def create_access_token(data: Dict[str, Any], expires_delta: Optional[datetime.timedelta] = None) -> str:
    """Generate JWT access token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.datetime.utcnow() + expires_delta
    else:
        expire = datetime.datetime.utcnow() + datetime.timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return encoded_jwt

def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """Decode and validate JWT access token"""
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload
    except (jwt.PyJWTError, Exception):
        return None

def sanitize_input(text: str) -> str:
    """Sanitize input string against XSS using bleach"""
    if not isinstance(text, str):
        return ""
    # Strip HTML tags
    return bleach.clean(text.strip(), tags=[], attributes={}, strip=True)
