from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app, make_response
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired
from werkzeug.security import check_password_hash
from ..models import User, Log
import pandas as pd
from .. import db
from datetime import timedelta, datetime
import uuid
import os
import pytz

export_bp = Blueprint('export_bp', __name__)

@export_bp.route('/export_logs', methods=['GET', 'POST'])
def export_logs():
    if not session.get('is_staff') == 1:
        flash('この機能にアクセスする権限がありません。', 'error')
        return redirect(url_for('teacher_main.teacher_main'))

    if request.method == 'POST':
        # データベース内のデータ存在確認（デバッグ用）
        total_records = Log.query.count()
        print(f"Total records in database: {total_records}")
        
        sample_data = Log.query.limit(1).all()
        if sample_data:
            print("Sample record:", {
                'grade': sample_data[0].grade,
                'subject': sample_data[0].subject,
                'admission_year': sample_data[0].admission_year,
                'prompt_datetime': sample_data[0].prompt_datetime
            })

        # フォームデータの取得とデバッグ出力
        form_data = request.form.to_dict()
        print("Form data:", form_data)

        grade_filter = request.form.get('grade_filter', '1')
        subject_filter = request.form.get('subject_filter', '全科目')
        class_filter = request.form.get('class_filter', '全クラス')
        from_date = request.form.get('from_date')
        to_date = request.form.get('to_date')
        admission_year_filter = request.form.get('admission_year_filter')

        print(f"Filters: grade={grade_filter}, subject={subject_filter}, class={class_filter}")
        print(f"Dates: from={from_date}, to={to_date}, admission_year={admission_year_filter}")

        try:
            from_date = datetime.strptime(from_date, '%Y-%m-%d')
            to_date = datetime.strptime(to_date, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
            
            if from_date > to_date:
                flash('開始日は終了日より前の日付を指定してください。', 'error')
                return redirect(url_for('export_bp.export_logs'))
        except (ValueError, TypeError) as e:
            print(f"Date parsing error: {e}")
            flash('日付形式が不正です。正しい日付形式（YYYY-MM-DD）を指定してください。', 'error')
            return redirect(url_for('export_bp.export_logs'))

        # クエリの構築
        query = Log.query

        if grade_filter:
            query = query.filter(Log.grade == int(grade_filter))
        if subject_filter and subject_filter != '全科目':
            query = query.filter(Log.subject == subject_filter)
        if class_filter and class_filter != '全クラス':
            query = query.filter(Log.class_id == class_filter)
        if admission_year_filter:
            query = query.filter(Log.admission_year == int(admission_year_filter))

        query = query.filter(Log.prompt_datetime.between(from_date, to_date))

        # クエリのデバッグ出力
        print("SQL Query:", str(query))
        
        try:
            logs = query.all()
            print(f"Found {len(logs)} records")

            if not logs:
                flash(f'指定された条件に合致するデータが見つかりません。', 'warning')
                return redirect(url_for('export_bp.export_logs'))

            # データの処理とExcelファイルの生成
            log_data = []
            for log in logs:
                log_dict = {
                    'class_id': log.class_id,
                    'user_id': log.user_id,
                    'prompt': log.prompt,
                    'prompt_datetime': log.prompt_datetime.strftime('%Y-%m-%d %H:%M:%S'),
                    'response': log.response,
                    'response_datetime': log.response_datetime.strftime('%Y-%m-%d %H:%M:%S'),
                    'difficulty': log.difficulty,
                    'grade': log.grade,
                    'subject': log.subject,
                    'date': log.date.strftime('%Y-%m-%d'),
                    'week': log.week,
                    'month': log.month,
                    'year': log.year,
                    'hour': log.hour,
                    'time_period': log.time_period,
                    'week_start_date': log.week_start_date.strftime('%Y-%m-%d')
                }
                log_data.append(log_dict)

            df = pd.DataFrame(log_data)
            
            # BytesIOを使用してメモリ上でExcelファイルを作成
            from io import BytesIO
            excel_buffer = BytesIO()
            
            # ExcelWriterを使用してxlsxファイルを作成
            with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name='ログデータ')
                
                # ワークシートを取得
                worksheet = writer.sheets['ログデータ']
                
                # 列幅の自動調整
                for idx, col in enumerate(df.columns):
                    max_length = max(
                        df[col].astype(str).apply(len).max(),
                        len(col)
                    )
                    worksheet.column_dimensions[chr(65 + idx)].width = min(max_length + 2, 50)
                
                # ヘッダー行のスタイル設定
                from openpyxl.styles import Font, PatternFill
                header_font = Font(bold=True)
                header_fill = PatternFill(start_color='CCCCCC', end_color='CCCCCC', fill_type='solid')
                
                for cell in worksheet[1]:
                    cell.font = header_font
                    cell.fill = header_fill
            
            # バッファの位置を先頭に戻す
            excel_buffer.seek(0)
            
            # ファイル名を生成
            filename = f'log_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
            
            # レスポンスの作成
            response = make_response(excel_buffer.getvalue())
            response.headers["Content-Disposition"] = f"attachment; filename={filename}"
            response.headers["Content-Type"] = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            
            return response

        except Exception as e:
            print(f"Error processing data: {e}")  # デバッグ用
            flash('データのエクスポート中にエラーが発生しました。', 'error')
            return redirect(url_for('export_bp.export_logs'))

    # GETリクエスト時の処理
    try:
        available_classes = [c[0] for c in db.session.query(Log.class_id).distinct().all() if c[0] != '0']
        available_classes.sort()

        admission_years = sorted(
            list(set([str(log.admission_year) for log in Log.query.with_entities(Log.admission_year).distinct() 
                     if log.admission_year != 9999])),
            reverse=True
        )

        subjects = [subject[0] for subject in db.session.query(Log.subject).distinct().order_by(Log.subject.desc()).all()]

        # 現在の日付を取得
        today = datetime.now()
        # デフォルトの日付範囲を1ヶ月前から今日までに設定
        default_from_date = (today - timedelta(days=30)).strftime('%Y-%m-%d')
        default_to_date = today.strftime('%Y-%m-%d')

        return render_template('export_logs.html',
                             available_classes=available_classes,
                             admission_years=admission_years,
                             admission_year_filter=admission_years[0] if admission_years else None,
                             subjects=subjects,
                             grade_filter='1',
                             from_date=default_from_date,
                             to_date=default_to_date)

    except Exception as e:
        print(f"Error loading page: {e}")
        flash('ページの読み込み中にエラーが発生しました。', 'error')
        return redirect(url_for('teacher_main.teacher_main'))