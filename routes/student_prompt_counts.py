from flask import Blueprint, render_template, request, session, flash, redirect, url_for
from sqlalchemy import func, extract
from .. import db
import pandas as pd
from datetime import datetime, time
from ..models import Log, User
import plotly.express as px
from ..config import Config

student_prompt_counts_bp = Blueprint('student_prompt_counts', __name__)

def generate_plot(data, x, y):
    if data.empty:
        return None
    fig = px.bar(data, x=x, y=y)
    fig.update_layout(
        xaxis_title="学生",
        yaxis_title="プロンプト数",
        xaxis={'categoryorder':'total descending'}
    )
    return fig

def get_filtered_logs(user_id, subject_filter, time_filter, from_date, to_date):
    query = Log.query.filter(Log.user_id == user_id)

    if subject_filter:
        query = query.filter(Log.subject == subject_filter)

    if time_filter != '全時間帯':
        time_mapping = {
            '午前: 06:00 - 11:59': (time(6, 0), time(11, 59)),
            '午後: 12:00 - 16:59': (time(12, 0), time(16, 59)),
            '夕方: 17:00 - 20:59': (time(17, 0), time(20, 59)),
            '夜間: 21:00 - 05:59': (time(21, 0), time(5, 59))
        }
        start_time, end_time = time_mapping.get(time_filter)
        
        if start_time > end_time:  # 夜間の場合
            query = query.filter(
                ((extract('hour', Log.prompt_datetime) == start_time.hour) & (extract('minute', Log.prompt_datetime) >= start_time.minute)) |
                ((extract('hour', Log.prompt_datetime) > start_time.hour) & (extract('hour', Log.prompt_datetime) <= 23)) |
                ((extract('hour', Log.prompt_datetime) >= 0) & (extract('hour', Log.prompt_datetime) < end_time.hour)) |
                ((extract('hour', Log.prompt_datetime) == end_time.hour) & (extract('minute', Log.prompt_datetime) <= end_time.minute))
            )
        else:
            query = query.filter(
                ((extract('hour', Log.prompt_datetime) == start_time.hour) & (extract('minute', Log.prompt_datetime) >= start_time.minute)) |
                ((extract('hour', Log.prompt_datetime) > start_time.hour) & (extract('hour', Log.prompt_datetime) < end_time.hour)) |
                ((extract('hour', Log.prompt_datetime) == end_time.hour) & (extract('minute', Log.prompt_datetime) <= end_time.minute))
            )

    query = query.filter(Log.prompt_datetime.between(from_date, to_date))
    
    return query.order_by(Log.prompt_datetime.desc()).all()

@student_prompt_counts_bp.route('/student_prompt_counts', methods=['GET'])
def student_prompt_counts_page():
    # 教師権限（is_staff == 1）でない場合
    if session.get('is_staff') != 1:
        flash('この機能にアクセスする権限がありません。', 'error')
        # 学生の場合は学生用メイン画面へリダイレクト
        return redirect(url_for('student_main.student_main'))

    # フィルタの値を取得
    grade_filter = request.args.get('grade_filter', '高校1年')
    subject_filter = request.args.get('subject_filter', request.args.get('subject_filter', '英語'))  # ここを修正
    time_filter = request.args.get('time_filter', '全時間帯')
    class_filter = request.args.get('class_filter', '1A')
    from_date_str = request.args.get('from_date', Config.DEFAULT_FROM_DATE)
    to_date_str = request.args.get('to_date', Config.DEFAULT_TO_DATE)

    # from_date = datetime.strptime(from_date_str, '%Y-%m-%d')
    # to_date = datetime.strptime(to_date_str, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
    
    # from_date と to_date の日付変換（その日の00:00:00で統一）
    from_date = datetime.strptime(from_date_str, '%Y-%m-%d')
    to_date = datetime.strptime(to_date_str, '%Y-%m-%d')

    # 入学年度を取得し、9999を除外
    admission_years = sorted(list(set([str(log.admission_year) for log in Log.query.with_entities(Log.admission_year).distinct() if log.admission_year != 9999])), reverse=True)

    # 入学年度フィルタを適用
    admission_year_filter = request.args.get('admission_year_filter', admission_years[0] if admission_years else None)

    # クラス情報を取得
    all_classes = db.session.query(User.class_id).distinct().filter(User.class_id != '0').order_by(User.class_id).all()
    all_classes = [cls[0] for cls in all_classes if cls[0] != '0']  # クラス0を除外


    # データベースから科目リストを取得
    # subjects = [subject[0] for subject in db.session.query(Log.subject).distinct().order_by(Log.subject.asc()).all()]
    subjects = [subject[0] for subject in db.session.query(Log.subject).distinct().order_by(Log.subject.desc()).all()]

    # フィルタリングされた学生情報を取得
    user_query = User.query.filter(User.is_staff == False)
    
    # 学年フィルタの適用
    if grade_filter:
        grade_mapping = {'高校1年': 1, '高校2年': 2, '高校3年': 3}
        selected_grade = grade_mapping.get(grade_filter)
        if selected_grade:
            user_query = user_query.filter(User.grade_id == selected_grade)

    # クラスフィルタの適用
    if class_filter and class_filter != '全クラス':
        user_query = user_query.filter(User.class_id == class_filter)

    # フィルタ適用後の学生情報を取得
    filtered_users = user_query.all()
    filtered_user_ids = [user.user_id for user in filtered_users]

    # ログデータのフィルタリング
    filtered_logs = []
    for user_id in filtered_user_ids:
        filtered_logs.extend(get_filtered_logs(user_id, subject_filter, time_filter, from_date, to_date))

    # グラフデータの生成
    if filtered_logs:
        log_df = pd.DataFrame([{
            'user_id': log.user_id,
            'last_name': User.query.filter_by(user_id=log.user_id).first().last_name,
            'student_id': log.user_id,
            'prompt_count': 1
        } for log in filtered_logs])

        log_df = log_df.groupby(['user_id', 'last_name', 'student_id']).sum().reset_index()
    else:
        log_df = pd.DataFrame(columns=['user_id', 'last_name', 'student_id','prompt_count'])

    # グラフの生成
    plot_html = None
    if not log_df.empty:
        fig = generate_plot(log_df, 'last_name', 'prompt_count')
        plot_html = fig.to_html(full_html=False) if fig else None

    # 選択された学生のプロンプトの取得
    selected_user = request.args.get('selected_student')
    student_prompts = []
    student_name = None
    if selected_user:
        student = User.query.filter_by(user_id=selected_user).first()
        if student:
            student_name = student.last_name
            student_logs = get_filtered_logs(selected_user, subject_filter, time_filter, from_date, to_date)
            student_prompts = [{
                'prompt': log.prompt,
                'response': log.response,
                'prompt_datetime': log.prompt_datetime.strftime('%Y-%m-%d %H:%M:%S')
            } for log in student_logs]

    return render_template(
            'student_prompt_counts.html',
            plot_html=plot_html,
            grade_filter=grade_filter,
            subjects=subjects,
            subject_filter=subject_filter,  
            time_filter=time_filter,
            class_filter=class_filter,
            from_date=from_date_str,
            to_date=to_date_str,
            admission_years=admission_years,
            admission_year_filter=admission_year_filter,
            all_classes=all_classes,
            all_students=filtered_users,
            selected_student=selected_user,
            student_prompts=student_prompts,
            student_name=student_name,
            has_data=bool(log_df.shape[0] > 0),
            has_student_data=bool(student_prompts)
        )