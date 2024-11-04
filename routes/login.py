from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app, jsonify
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired
from werkzeug.security import check_password_hash
from ..models import User
from .. import db
from datetime import timedelta
import uuid

bp = Blueprint('login', __name__)

class LoginForm(FlaskForm):
    user_id = StringField('ユーザーID', validators=[DataRequired()])
    password = PasswordField('パスワード', validators=[DataRequired()])
    submit = SubmitField('ログイン')
    csrf_token = StringField()

@bp.route('/', methods=['GET', 'POST'])
@bp.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('logged_in'):
        if session.get('is_staff') == 1:  # 教師の場合
            return redirect(url_for('teacher_main.subject_selection'))  # url_forを使用
        return redirect(url_for('student_main.subject_selection'))
    
    form = LoginForm()
    if form.validate_on_submit():
        user_id = form.user_id.data
        password = form.password.data

        user = User.query.filter_by(user_id=user_id).first()
        if user and check_password_hash(user.password, password):
            session.clear()
            session.permanent = True
            
            session['logged_in'] = True
            session['user_id'] = user.user_id
            session['first_name'] = user.first_name
            session['last_name'] = user.last_name
            session['grade_id'] = user.grade_id
            session['class_id'] = user.class_id
            session['is_staff'] = user.is_staff
            session['session_id'] = str(uuid.uuid4())

            if user.is_staff == 1:  # 教師の場合
                return redirect(url_for('prompt_trends.prompt_trends_page'))  # url_forを使用
            else:
                return redirect(url_for('student_main.subject_selection'))
        else:
            flash('ユーザIDまたはパスワードが間違っています。', 'error')

    return render_template('login.html', form=form)
