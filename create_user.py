import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

print("DATABASE_URL:", os.getenv('DATABASE_URL'))

from . import create_app, db
from .models import User
from werkzeug.security import generate_password_hash
from datetime import datetime
from .datetime_utils import utc_now  # utc_now 関数をインポート

app = create_app()

def create_user(user_id, last_name, email, password, first_name=None, grade_id=None, class_id=None, is_staff=False, admission_year=None, created_by=None, updated_by=None):
    existing_user = User.query.filter_by(user_id=user_id).first()

    hashed_password = generate_password_hash(password)

    if existing_user:
        existing_user.last_name = last_name
        existing_user.first_name = first_name
        existing_user.email = email
        existing_user.password = hashed_password
        existing_user.grade_id = grade_id
        existing_user.class_id = class_id
        existing_user.is_staff = is_staff
        existing_user.admission_year = admission_year
        existing_user.updated_at = utc_now()
        existing_user.updated_by = updated_by
        print(f"User {user_id} has been updated.")
    else:
        new_user = User(
            user_id=user_id,
            last_name=last_name,
            first_name=first_name,
            email=email,
            password=hashed_password,
            grade_id=grade_id,
            class_id=class_id,
            is_staff=is_staff,
            admission_year=admission_year,
            created_at=utc_now(),
            updated_at=utc_now(),
            created_by=created_by,
            updated_by=updated_by
        )
        db.session.add(new_user)
        print(f"User {user_id} has been created.")
    
    db.session.commit()

if __name__ == "__main__":
    with app.app_context():
        print("SQLAlchemy database URI:", app.config['SQLALCHEMY_DATABASE_URI'])
        create_user(
            user_id="s001",
            last_name="s001",
            email="s001@example.com",
            password="Student001",
            is_staff=False
        )