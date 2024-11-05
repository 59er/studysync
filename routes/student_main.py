from flask import Flask, Blueprint, render_template, session, redirect, url_for, flash, request,jsonify, Response
from ..models import User, Log
from datetime import datetime, timedelta
import uuid
from .. import db
from sqlalchemy import func, desc, and_
from sqlalchemy.exc import SQLAlchemyError
from flask_wtf import CSRFProtect
from ..utils import load_subjects

bp = Blueprint('student_main', __name__, url_prefix='/student')

# CSRFProtectの初期化
csrf = CSRFProtect()

def create_app():
    app = Flask(__name__)
    # アプリケーションの設定をここで行います
    csrf.init_app(app)  # CSRFProtectをアプリケーションに登録
    # 他の初期化やBlueprintの登録など
    return app

@bp.route('/student_main', methods=['GET', 'POST'])
def student_main():
    if 'user_id' not in session or 'session_id' not in session:
        return redirect(url_for('login.login'))

    user = User.query.filter_by(user_id=session['user_id']).first()
    if not user:
        session.clear()
        return redirect(url_for('login.login'))

    if 'selected_subject' not in session:
        return redirect(url_for('student_main.subject_selection'))

    if 'session_id' not in session:
        session.clear()
        flash("セッションが切れました。再度ログインしてください。", "warning")
        return redirect(url_for('login.login'))

    chat_history = []
    qa_history_data = []

    # デバッグ用のセッション情報表示
    # print(f"Debug: student_main 関数開始時のセッション情報: {session}")

    if request.method == 'POST' or request.args.get('show_history'):
        try:
            # デバッグ用にフィルタ条件を表示
            # print(f"Debug: クエリ条件 - user_id: {session['user_id']}, subject: {session['selected_subject']}")

            # チャット履歴を取得する際のクエリ
            chat_history = Log.query.filter_by(
                user_id=session['user_id'],
                subject=session['selected_subject'],
            ).order_by(Log.prompt_datetime.desc()).limit(10).all()

            # 取得したチャット履歴のデバッグ情報を表示
            # print(f"Debug: 取得した chat_history: {chat_history}")

            # クエリのサブクエリを設定
            subquery = db.session.query(
                Log.qa_id,
                func.max(Log.prompt_datetime).label('latest_datetime')
            ).filter(
                Log.user_id == session['user_id'],
                Log.subject == session['selected_subject'],
                Log.prompt != "New Chat Started"
            ).group_by(Log.qa_id).subquery()

            # qa_history を取得する際のクエリ
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

            # デバッグ用に取得した qa_history を表示
            # print(f"Debug: 取得した qa_history: {qa_history}")

            qa_history_data = [{
                'qa_id': str(qa.qa_id),
                'latest_datetime': qa.prompt_datetime.isoformat(),
                'latest_prompt': qa.prompt
            } for qa in qa_history]
            # print(f"Debug: 取得した qa_history_data: {qa_history_data}")

        except SQLAlchemyError as e:
            print(f"Database error: {str(e)}")
            flash("データの取得中にエラーが発生しました。", "error")

    # # 取得したデータのデバッグ情報を表示
    # print(f"Debug: render_template 前の chat_history: {chat_history}")
    # print(f"Debug: render_template 前の qa_history_data: {qa_history_data}")
    # print(f"Debug: render_template 前の selected_subject: {session['selected_subject']}")
    # print(f"Debug: render_template 前の user: {user}")

    return render_template('student_main.html',
                           chat_history=chat_history,
                           qa_history=qa_history_data,
                           selected_subject=session['selected_subject'],
                           user=user)


@bp.route('/subject_selection', methods=['GET', 'POST'])
def subject_selection():
    if 'session_id' not in session:
        session.clear()
        flash("セッションが切れました。再度ログインしてください。", "warning")
        return redirect(url_for('login.login'))

    if 'selected_subject' in session:
        del session['selected_subject']

    subjects = load_subjects()  # 教科リストを読み込む

    if request.method == 'POST':
        selected_subject = request.form.get('subject')
        if selected_subject:
            session['selected_subject'] = selected_subject
            return redirect(url_for('student_main.student_main'))
    
    # student_main.subject_selectionをsubmit_urlとして渡す
    return render_template('subject_selection.html', subjects=subjects, 
                         submit_url='student_main.subject_selection')


@bp.route('/new_chat', methods=['POST'])
def new_chat():
    if 'session_id' not in session:
        session.clear()
        flash("セッションが切れました。再度ログインしてください。", "warning")
        return redirect(url_for('login.login'))

    # CSRFトークンの検証はFlask-WTFで自動的に行われます

    # 現在のセッションIDを確認
    session_id = session.get('session_id')

    # 新しいQAセッションを開始するための新しいqa_idを設定
    new_qa_id = str(uuid.uuid4())
    session['current_qa_id'] = new_qa_id

    try:
        # チャット履歴を消去するのではなく、新しい会話セットとしてログを管理する
        new_chat_log = Log(
            qa_id=new_qa_id,
            session_id=session_id,
            user_id=session['user_id'],
            subject=session['selected_subject'],
            prompt="New Chat Started",  # 初期プロンプトを追加
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

    return redirect(url_for('student_main.student_main'))


@bp.route('/clear_chat', methods=['POST'])
def clear_chat():
    try:
        # セッションが有効かどうかをチェック
        if 'user_id' not in session:
            # セッションが無効な場合、ログインページにリダイレクト
            return redirect(url_for('login.login'))

        # CSRFトークンの検証はFlask-WTFで自動的に行われます

        user_id = session.get('user_id')
        selected_subject = session.get('selected_subject')
        current_qa_id = session.get('current_qa_id')

        # print(f"Debug: clear_chat 実行前のセッション情報: {session}")
        # print(f"Debug: clear_chat - 対象の user_id: {user_id}, subject: {selected_subject}, current_qa_id: {current_qa_id}")

        if current_qa_id:
            # `current_qa_id` に基づくデータのみを削除
            Log.query.filter_by(user_id=user_id, subject=selected_subject, qa_id=current_qa_id).delete()
            db.session.commit()
            print(f"Debug: チャット履歴をクリアしました: user_id = {user_id}, subject = {selected_subject}")

            # `current_qa_id` を None に設定
            session['current_qa_id'] = None
        else:
            print("Debug: チャット履歴がありません。")

    except SQLAlchemyError as e:
        print(f"Database error during clear_chat: {str(e)}")
        db.session.rollback()
        flash("チャット履歴のクリア中にエラーが発生しました。", "error")

    return redirect(url_for('student_main.student_main'))


def get_time_period(hour):
    if 5 <= hour < 12:
        return 'morning'
    elif 12 <= hour < 17:
        return 'afternoon'
    elif 17 <= hour < 22:
        return 'evening'
    else:
        return 'night'


