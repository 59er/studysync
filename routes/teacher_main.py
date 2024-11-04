from flask import Blueprint, render_template, session, redirect, url_for, flash, request, jsonify, Response, current_app
from ..models import User, Log
from datetime import datetime, timedelta
import uuid
import os
import json
from .. import db
from sqlalchemy import func, desc, and_
from sqlalchemy.exc import SQLAlchemyError
from flask_wtf import CSRFProtect
from functools import wraps  # functools.wrapsを追加
from ..utils import load_subjects


teacher_bp = Blueprint('teacher_main', __name__, url_prefix='/teacher')

# CSRFProtectの初期化
csrf = CSRFProtect()

@teacher_bp.before_request
def check_teacher_session():
    # AJAXリクエストの判定
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    
    if 'user_id' not in session or 'session_id' not in session:
        if is_ajax:
            return jsonify({
                'error': 'セッションが切れました',
                'redirect': url_for('login.login')
            }), 401
        else:
            session.clear()
            flash("セッションが切れました。再度ログインしてください。", "warning")
            return redirect(url_for('login.login'))

def teacher_required(f):
    @wraps(f)
    def decorated_view(*args, **kwargs):
        # セッションチェック
        if not session.get('user_id') or not session.get('session_id'):
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({
                    'error': 'セッションが切れました',
                    'redirect': url_for('login.login')
                }), 401
            session.clear()  # セッションをクリア
            flash('セッションが切れました。再度ログインしてください。', 'warning')
            return redirect(url_for('login.login'))
            
        # 教師権限チェック
        if session.get('is_staff') != 1:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({
                    'error': '教師権限が必要です',
                    'redirect': url_for('login.login')
                }), 403
            session.clear()  # セッションをクリア
            flash('この機能には教師権限が必要です。', 'error')
            return redirect(url_for('login.login'))
            
        return f(*args, **kwargs)
    return decorated_view

@teacher_bp.route('/teacher_main', methods=['GET', 'POST'])
@teacher_required
def teacher_main():
    
    user = User.query.filter_by(user_id=session['user_id']).first()
    if not user:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'error': 'ユーザーが見つかりません',
                'redirect': url_for('login.login')
            }), 401
        session.clear()
        return redirect(url_for('login.login'))

    if 'selected_subject' not in session:
        return redirect(url_for('teacher_main.subject_selection'))
    
    
    if 'session_id' not in session:
        session.clear()
        flash("セッションが切れました。再度ログインしてください。", "warning")
        return redirect(url_for('login.login'))

    user = User.query.filter_by(user_id=session['user_id']).first()
    if not user:
        session.clear()
        return redirect(url_for('login.login'))

    if 'selected_subject' not in session:
        return redirect(url_for('teacher_main.subject_selection'))

    chat_history = []
    qa_history_data = []

    if request.method == 'POST' or request.args.get('show_history'):
        try:
            chat_history = Log.query.filter_by(
                user_id=session['user_id'],
                subject=session['selected_subject'],
                qa_id=session.get('current_qa_id')  # 現在のQA IDでフィルタ
            ).order_by(Log.prompt_datetime.desc()).all()

            # QA履歴の取得処理を修正
            subquery = db.session.query(
                Log.qa_id,
                func.max(Log.prompt_datetime).label('latest_datetime')
            ).filter(
                Log.user_id == session['user_id'],
                Log.subject == session['selected_subject'],
                Log.prompt != "New Chat Started"  # New Chatエントリを除外
            ).group_by(Log.qa_id).subquery()

            qa_history = db.session.query(
                Log.qa_id,
                Log.prompt_datetime,
                Log.prompt
            ).join(
                subquery,
                and_(
                    Log.qa_id == subquery.c.qa_id,
                    Log.prompt_datetime == subquery.c.latest_datetime
                )
            ).filter(
                Log.user_id == session['user_id'],
                Log.subject == session['selected_subject']
            ).order_by(desc(Log.prompt_datetime)).limit(10).all()

            qa_history_data = [{
                'qa_id': str(qa.qa_id),
                'latest_datetime': qa.prompt_datetime.isoformat(),
                'latest_prompt': qa.prompt
            } for qa in qa_history if qa.prompt != "New Chat Started"]  # New Chatエントリを除外

        except SQLAlchemyError as e:
            print(f"Database error: {str(e)}")
            flash("データの取得中にエラーが発生しました。", "error")

    return render_template('teacher_main.html',
                         chat_history=chat_history,
                         qa_history=qa_history_data,
                         selected_subject=session['selected_subject'],
                         user=user)

@teacher_bp.route('/subject_selection', methods=['GET', 'POST'])
@teacher_required
def subject_selection():
    if 'session_id' not in session:
        session.clear()
        flash("セッションが切れました。再度ログインしてください。", "warning")
        return redirect(url_for('login.login'))

    subjects = load_subjects()  # 科目データを取得
    
    if request.method == 'POST':
        selected_subject = request.form.get('subject')
        if selected_subject:
            session['selected_subject'] = selected_subject
            return redirect(url_for('teacher_main.teacher_main'))
    
    return render_template('subject_selection.html', subjects=subjects)

@teacher_bp.route('/new_chat', methods=['POST'])
@teacher_required
def new_chat():
    if 'session_id' not in session:
        session.clear()
        flash("セッションが切れました。再度ログインしてください。", "warning")
        return redirect(url_for('login.login'))

    session_id = session.get('session_id')
    new_qa_id = str(uuid.uuid4())
    session['current_qa_id'] = new_qa_id

    try:
        new_chat_log = Log(
            qa_id=new_qa_id,
            session_id=session_id,
            user_id=session['user_id'],
            subject=session['selected_subject'],
            prompt="New Chat Started",
            prompt_datetime=datetime.utcnow(),
            response="",
            response_datetime=datetime.utcnow(),
            difficulty=0,
            grade=session.get('grade_id', 0),
            date=datetime.utcnow().date(),
            week=datetime.utcnow().isocalendar()[1],
            month=datetime.utcnow().month,
            year=datetime.utcnow().year,
            hour=datetime.utcnow().hour,
            time_period=get_time_period(datetime.utcnow().hour),
            week_start_date=(datetime.utcnow() - timedelta(days=datetime.utcnow().weekday())).date(),
            admission_year=session.get('admission_year', 0)
        )
        db.session.add(new_chat_log)
        db.session.commit()
    except SQLAlchemyError as e:
        print(f"Database error: {str(e)}")
        db.session.rollback()
        flash("新しいチャットの開始中にエラーが発生しました。", "error")

    return redirect(url_for('teacher_main.teacher_main'))

@teacher_bp.route('/clear_chat', methods=['POST'])
@teacher_required
def clear_chat():
    try:
        if 'user_id' not in session:
            return redirect(url_for('login.login'))

        user_id = session.get('user_id')
        selected_subject = session.get('selected_subject')
        current_qa_id = session.get('current_qa_id')

        if current_qa_id:
            Log.query.filter_by(user_id=user_id, subject=selected_subject, qa_id=current_qa_id).delete()
            db.session.commit()
            session['current_qa_id'] = None
            
            # QA履歴の更新フラグを設定
            session['update_qa'] = True

        # 新しいQA IDを生成
        new_qa_id = str(uuid.uuid4())
        session['current_qa_id'] = new_qa_id
        
        # 新しいチャットの開始をログに記録
        try:
            new_chat_log = Log(
                qa_id=new_qa_id,
                session_id=session.get('session_id'),
                user_id=session['user_id'],
                subject=session['selected_subject'],
                prompt="New Chat Started",
                prompt_datetime=datetime.utcnow(),
                response="",
                response_datetime=datetime.utcnow(),
                difficulty=0,
                grade=session.get('grade_id', 0),
                date=datetime.utcnow().date(),
                week=datetime.utcnow().isocalendar()[1],
                month=datetime.utcnow().month,
                year=datetime.utcnow().year,
                hour=datetime.utcnow().hour,
                time_period=get_time_period(datetime.utcnow().hour),
                week_start_date=(datetime.utcnow() - timedelta(days=datetime.utcnow().weekday())).date(),
                admission_year=session.get('admission_year', 0)
            )
            db.session.add(new_chat_log)
            db.session.commit()
        except SQLAlchemyError as e:
            print(f"Database error: {str(e)}")
            db.session.rollback()
        
    except SQLAlchemyError as e:
        print(f"Database error during clear_chat: {str(e)}")
        db.session.rollback()
        flash("チャット履歴のクリア中にエラーが発生しました。", "error")

    return redirect(url_for('teacher_main.teacher_main'))

@teacher_bp.route('/reset_update_flag', methods=['POST'])
@teacher_required
def reset_update_flag():
    if 'update_qa' in session:
        session.pop('update_qa')
    return jsonify({'status': 'success'})

@teacher_bp.errorhandler(SQLAlchemyError)
def handle_db_error(e):
    db.session.rollback()
    app.logger.error(f"Database error: {str(e)}")
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'error': 'データベースエラーが発生しました'}), 500
    flash("データベースエラーが発生しました。", "error")
    return redirect(url_for('teacher_main.teacher_main'))

@teacher_bp.before_request
def refresh_session():
    if 'user_id' in session:
        session.modified = True  # セッションを更新
        
def get_time_period(hour):
    if 5 <= hour < 12:
        return 'morning'
    elif 12 <= hour < 17:
        return 'afternoon'
    elif 17 <= hour < 22:
        return 'evening'
    else:
        return 'night'