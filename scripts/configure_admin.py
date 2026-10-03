"""Explicit one-time admin configuration; password is entered without echo."""
import sys
from pathlib import Path
from getpass import getpass
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from auth.database import init_db, get_session, UserDB
from auth.security import hash_password, verify_password

def configure(password):
    init_db()
    db = get_session()
    try:
        user = db.query(UserDB).filter_by(username='admin').first()
        if user is None:
            user = UserDB(username='admin', email='admin@datavizpro.com', full_name='System Administrator')
            db.add(user)
        user.hashed_password = hash_password(password)
        user.role = 'admin'
        user.is_active = True
        db.commit()
        assert verify_password(password, user.hashed_password)
        print('Admin account configured and password hash verified.')
    finally:
        db.close()

if __name__ == '__main__':
    configure(getpass('Admin password: '))
