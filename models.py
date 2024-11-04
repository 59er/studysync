from datetime import datetime
from sqlalchemy.sql import func
from . import db 
import uuid



class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(100), unique=True, nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    first_name = db.Column(db.String(100), nullable=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)  # これが必要です
    grade_id = db.Column(db.Integer, nullable=True)
    class_id = db.Column(db.String(50), nullable=True)
    is_staff = db.Column(db.Boolean, default=False)
    admission_year = db.Column(db.String(4), nullable=True)
    created_at = db.Column(db.DateTime, server_default=func.now(), nullable=False)
    updated_at = db.Column(db.DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by = db.Column(db.String(100), nullable=True)
    updated_by = db.Column(db.String(100), nullable=True)

    
class Log(db.Model):
    __tablename__ = 'logs'
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.String(36), nullable=False)
    qa_id = db.Column(db.String(36), nullable=False, default=lambda: str(uuid.uuid4()))  # デフォルトでUUIDを生成
    school_id = db.Column(db.String(50), nullable=False)
    class_id = db.Column(db.String(50), nullable=False)
    user_id = db.Column(db.String(50), nullable=False)  # user_idで識別
    prompt = db.Column(db.Text, nullable=False)
    prompt_datetime = db.Column(db.DateTime, nullable=False)
    response = db.Column(db.Text, nullable=False)
    response_datetime = db.Column(db.DateTime, nullable=False)
    difficulty = db.Column(db.Integer, nullable=False)
    grade = db.Column(db.Integer, nullable=False)
    subject = db.Column(db.String(50), nullable=False)
    date = db.Column(db.Date, nullable=False)
    week = db.Column(db.Integer, nullable=False)
    month = db.Column(db.Integer, nullable=False)
    year = db.Column(db.Integer, nullable=False)
    hour = db.Column(db.Integer, nullable=False)
    time_period = db.Column(db.String(20), nullable=False)
    week_start_date = db.Column(db.Date, nullable=False)
    admission_year = db.Column(db.Integer, nullable=False)

class NGWord(db.Model):
    __tablename__ = 'ng_words'
    id = db.Column(db.Integer, primary_key=True)
    ng_word = db.Column(db.String(100), nullable=False)

class SubjectPrompt(db.Model):
    __tablename__ = 'subject_prompts'
    id = db.Column(db.Integer, primary_key=True)
    subject = db.Column(db.String(50), nullable=False)  # 科目名
    prompt_text = db.Column(db.Text, nullable=False)  # プロンプトのテキスト
    updated_date = db.Column(db.DateTime, nullable=False, default=db.func.current_timestamp(), onupdate=db.func.current_timestamp())  # 最終更新日時

class Setting(db.Model):
    __tablename__ = 'settings'
    id = db.Column(db.Integer, primary_key=True)
    subject = db.Column(db.String(50), nullable=False)  # 科目名
    model = db.Column(db.String(50), nullable=False)  # モデル名
    temperature = db.Column(db.Float, nullable=False, default=0.7)  # Temperatureの設定
    max_question_tokens = db.Column(db.Integer, nullable=False, default=1000)  # 質問のmax_token (デフォルト1000)
    max_response_tokens = db.Column(db.Integer, nullable=False, default=1000)  # 回答のmax_token (デフォルト1000)
    difficulty_prompt = db.Column(db.Text, nullable=True)  # 難易度評価のプロンプト
    updated_date = db.Column(db.DateTime, nullable=False, default=db.func.current_timestamp(), onupdate=db.func.current_timestamp())  # 最終更新日時

# class TeacherAssignment(db.Model):
#     __tablename__ = 'teacher_assignment'
#     id = db.Column(db.Integer, primary_key=True, autoincrement=True)
#     student_id = db.Column(db.String(50), db.ForeignKey('users.user_id'), nullable=False)  # 生徒のuser_idを参照
#     teacher_id = db.Column(db.String(50), db.ForeignKey('users.user_id'), nullable=True)  # 教師のuser_idを参照
#     role = db.Column(db.String(50), nullable=True)  # 例: 担任, 副担任, 科目担当
#     subject = db.Column(db.String(50), nullable=True)  # 科目担当の場合に科目名を保存
