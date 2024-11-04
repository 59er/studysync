from flask import Blueprint, render_template, request, session, flash, redirect, url_for
from sqlalchemy import func
from .. import db
import pandas as pd
from datetime import datetime, timedelta
from ..models import Log, User
import plotly.express as px
from ..config import Config
import logging
from functools import wraps

prompt_trends_bp = Blueprint('prompt_trends', __name__)

# デフォルト値をグローバルスコープで定義
default_from_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
default_to_date = datetime.now().strftime('%Y-%m-%d')

def generate_plot(data, x, y):
    fig = px.line(data, x=x, y=y)
    fig.update_xaxes(title_text='日付' if x == 'date' else '週' if x == 'week' else '月')
    fig.update_yaxes(title_text='プロンプト数', rangemode='tozero')

    if x == 'date':
        num_days = (pd.to_datetime(data[x]).max() - pd.to_datetime(data[x]).min()).days
        if num_days > 30:
            fig.update_xaxes(nticks=num_days // 3, tickangle=45, tickformat="%Y-%m-%d")
        else:
            fig.update_xaxes(nticks=num_days, tickangle=45, tickformat="%Y-%m-%d")
    elif x == 'week':
        num_weeks = len(data[x].unique())
        if num_weeks > 10:
            fig.update_xaxes(nticks=num_weeks // 2, tickangle=45, tickformat="%Y-%m-%d")
        else:
            fig.update_xaxes(nticks=num_weeks, tickangle=45, tickformat="%Y-%m-%d")
    elif x == 'month':
        num_months = len(data[x].unique())
        if num_months > 6:
            fig.update_xaxes(nticks=num_months, tickformat="%Y-%m")
        else:
            fig.update_xaxes(nticks=num_months, tickformat="%Y-%m")

    return fig


# 教師権限チェック用デコレータ
def teacher_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            flash('ログインが必要です。', 'error')
            return redirect(url_for('login.login'))
        if session.get('is_staff') != 1:
            flash('この機能には教師権限が必要です。', 'error')
            return redirect(url_for('login.login'))
        return f(*args, **kwargs)
    return decorated_function


@prompt_trends_bp.route('/', methods=['GET', 'POST'])
@teacher_required
def prompt_trends_page():
    print("=== Starting prompt_trends_page function ===")  # デバッグ用
    print(f"Session contents: {session}")  # セッション内容を確認
    logging.basicConfig(level=logging.DEBUG)
    logger = logging.getLogger(__name__)

    if not session.get('logged_in'):
        flash('ログインが必要です。', 'error')
        return redirect(url_for('login.login'))

    if session.get('is_staff') != 1:
        flash('この機能にアクセスする権限がありません。', 'error')
        return redirect(url_for('login.login'))

    try:
        print("Trying to get subjects")  # デバッグ用
        # データベースから科目リストを取得
        subjects = db.session.query(Log.subject).distinct().all()
        print(f"Retrieved subjects: {subjects}")  # デバッグ用

        # フィルタの値を取得（デフォルト値を設定）
        grade_filter = request.args.get('grade_filter', '高校1年')
        time_period = request.args.get('time_period', '日次')
        subject_filter = request.args.get('subject_filter', '全科目')
        time_filter = request.args.get('time_filter', '全時間帯')
        user_filter = request.args.get('user_filter', None)
        admission_year_filter = request.args.get('admission_year_filter', str(datetime.now().year))
        
        print(f"Filter values loaded: {grade_filter}, {time_period}, {subject_filter}")  #

        # from_date_str と to_date_str が None の場合、デフォルト日付を設定
        from_date_str = request.args.get('from_date', default_from_date)
        to_date_str = request.args.get('to_date', default_to_date)

        # from_date と to_date の日付変換（その日の00:00:00で統一）
        from_date = datetime.strptime(from_date_str, '%Y-%m-%d')
        to_date = datetime.strptime(to_date_str, '%Y-%m-%d')

        logger.debug(f"From date: {from_date}, To date: {to_date}")

        # データベースからログを取得（JSTで保存されているため、UTC変換は不要）
        # logs = Log.query.filter(Log.prompt_datetime.between(from_date, to_date + timedelta(days=1))).all()
        logs = Log.query.filter(Log.prompt_datetime.between(from_date, to_date)).all()
        

        logger.debug(f"Number of logs retrieved: {len(logs)}")

        # 入学年度のリストを取得（常に設定）
        admission_years = sorted(list(set([str(user.admission_year) for user in User.query.filter(User.admission_year != 9999).all()])), reverse=True)

        if not logs:
            flash('表示するデータはありません。', 'info')
            return render_template('prompt_trends.html',
                                plots=[],
                                admission_year_filter=admission_year_filter,
                                admission_years=admission_years,
                                grade_filter=grade_filter,
                                time_period=time_period,
                                subject_filter=subject_filter,
                                subjects=[subject[0] for subject in subjects],
                                time_filter=time_filter,
                                user_filter=user_filter,
                                from_date=from_date.strftime('%Y-%m-%d'),
                                to_date=to_date.strftime('%Y-%m-%d'))

        # ログデータをDataFrameに変換（JSTのまま）
        log_df = pd.DataFrame([{
            'prompt_datetime': log.prompt_datetime,
            'subject': log.subject,
            'grade': log.grade,
            'class_id': log.class_id,
            'user_id': log.user_id,
            'time_period': log.time_period,
            'prompt': log.prompt,
            'response': log.response,
            'admission_year': log.admission_year
        } for log in logs])

        # 日付を「夜間」の定義に合わせて調整（朝6時を日付の変わり目とする）
        log_df['adjusted_date'] = log_df['prompt_datetime'].apply(lambda x: (x - timedelta(hours=6)).date())
        log_df['hour'] = log_df['prompt_datetime'].dt.hour

        time_mapping = {
            '午前': (6, 12),
            '午後': (12, 17),
            '夕方': (17, 21),
            '夜間': (21, 6),
        }

        # フィルタリング
        if subject_filter != '全科目':
            log_df = log_df[log_df['subject'] == subject_filter]
        if grade_filter != '全学年':
            grade_mapping = {'高校1年': 1, '高校2年': 2, '高校3年': 3}
            log_df = log_df[log_df['grade'] == grade_mapping.get(grade_filter, 1)]  # デフォルトは高校1年
        if time_filter != '全時間帯':
            start_hour, end_hour = time_mapping[time_filter]
            if time_filter == '夜間':
                log_df = log_df[(log_df['hour'] >= start_hour) | (log_df['hour'] < end_hour)]
            else:
                log_df = log_df[(log_df['hour'] >= start_hour) & (log_df['hour'] < end_hour)]
        if admission_year_filter and admission_year_filter != '全学年':
            log_df = log_df[log_df['admission_year'] == int(admission_year_filter)]

        logger.debug(f"Log DataFrame after filtering:\n{log_df}")
        
        # フィルタリング後にデータがない場合のチェック
        if log_df.empty:
            flash('選択された条件に該当するデータはありません。', 'info')
            return render_template('prompt_trends.html',
                                plots=[],
                                admission_year_filter=admission_year_filter,
                                admission_years=admission_years,
                                grade_filter=grade_filter,
                                time_period=time_period,
                                subject_filter=subject_filter,
                                subjects=[subject[0] for subject in subjects],
                                time_filter=time_filter,
                                user_filter=user_filter,
                                from_date=from_date.strftime('%Y-%m-%d'),
                                to_date=to_date.strftime('%Y-%m-%d'))

        # カウントの集計
        count_df = log_df.groupby('adjusted_date').size().reset_index(name='prompt_count')
        count_df['adjusted_date'] = pd.to_datetime(count_df['adjusted_date'])

        # グラフ表示用の日付範囲を作成
        df = pd.DataFrame({'date': pd.date_range(start=from_date, end=to_date, freq='D')})
        df['week'] = df['date'] - pd.to_timedelta(df['date'].dt.dayofweek, unit='D')
        df['month'] = df['date'].dt.to_period('M').astype(str)

        # count_df と df をマージ
        df = pd.merge(df, count_df, left_on='date', right_on='adjusted_date', how='left')
        df['prompt_count'] = df['prompt_count'].fillna(0).astype(int)

        # グラフの作成
        if time_period == '日次':
            plot_data = df[['date', 'prompt_count']]
            fig = generate_plot(plot_data, 'date', 'prompt_count')
        elif time_period == '週次':
            plot_data = df.groupby('week')['prompt_count'].sum().reset_index()
            fig = generate_plot(plot_data, 'week', 'prompt_count')
        elif time_period == '月次':
            plot_data = df.groupby('month')['prompt_count'].sum().reset_index()
            fig = generate_plot(plot_data, 'month', 'prompt_count')

        # figがNoneでない場合にのみレイアウトを更新
        if fig:
            fig.update_layout(height=600, margin=dict(l=50, r=50, t=50, b=50))
            plot_html = fig.to_html(full_html=False)
        else:
            plot_html = None

        return render_template('prompt_trends.html',
                           plots=[plot_html] if plot_html else [],
                           grade_filter=grade_filter,
                           time_period=time_period,
                           subject_filter=subject_filter,
                           subjects=[subject[0] for subject in subjects],
                           time_filter=time_filter,
                           user_filter=user_filter,
                           admission_year_filter=admission_year_filter,
                           admission_years=admission_years if 'admission_years' in locals() else [],
                           from_date=from_date.strftime('%Y-%m-%d'),
                           to_date=to_date.strftime('%Y-%m-%d'))

    except Exception as e:
        print(f"Error occurred: {str(e)}")  # デバッグ用
        print(f"Error type: {type(e)}")  # エラーの型を表示
        import traceback
        print(traceback.format_exc())  # スタックトレースを表示
        flash('データの取得中にエラーが発生しました。', 'error')
        return render_template('prompt_trends.html', plots=[])