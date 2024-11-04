from flask import Blueprint, render_template, request, session, flash, redirect, url_for, current_app, jsonify
import pandas as pd
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from ..models import User, Log
from .. import db
from datetime import datetime
import logging
from flask_wtf import FlaskForm
from wtforms import HiddenField
from sqlalchemy import func
from ..config import Config
import re
from collections import defaultdict
from janome.tokenizer import Tokenizer


logging.basicConfig(level=logging.INFO)

prompt_analysis_bp = Blueprint('prompt_analysis', __name__)

logger = logging.getLogger(__name__)

class CSRFForm(FlaskForm):
    csrf_token = HiddenField()

def preprocess_japanese_text(text):
    tokenizer = Tokenizer()
    words = []
    for token in tokenizer.tokenize(text):
        pos = token.part_of_speech.split(',')[0]
        if pos in ['名詞', '動詞', '形容詞']:
            words.append(token.surface)
    return ' '.join(words)

def classify_prompts(logs, grade, subject, start_date, end_date, class_id, admission_year):
    return [(log.prompt, preprocess_japanese_text(log.prompt)) for log in logs 
            if log.grade == grade and log.subject == subject and log.class_id == class_id 
            and log.admission_year == admission_year and start_date <= log.prompt_datetime <= end_date]

def group_similar_prompts(prompts, similarity_threshold=0.5):
    vectorizer = TfidfVectorizer()
    X = vectorizer.fit_transform([p[1] for p in prompts])  # preprocessed text
    similarity_matrix = cosine_similarity(X)
    grouped_prompts = {}
    visited = set()
    
    for idx, row in enumerate(similarity_matrix):
        if idx in visited:
            continue
        similar_indices = np.where(row >= similarity_threshold)[0]
        group = [prompts[i][0] for i in similar_indices if i not in visited]  # original prompt
        if group:
            group_key = group[0]  # Use the first prompt as the group key
            grouped_prompts[group_key] = group
            visited.update(similar_indices)
    
    return grouped_prompts

def analyze_prompts(logs, grade, subject, start_date, end_date, class_id, admission_year, similarity_threshold=0.5, num_rows='20'):
    classified_prompts = classify_prompts(logs, grade, subject, start_date, end_date, class_id, admission_year)
    logger.debug(f"Classified prompts: {len(classified_prompts)}")
    if not classified_prompts:
        flash("指定された条件ではデータが見つかりませんでした。", "warning")
        return {}
    grouped_prompts = group_similar_prompts(classified_prompts, similarity_threshold)
    logger.debug(f"Grouped prompts: {len(grouped_prompts)}")
    
    summaries = {key: len(group) for key, group in grouped_prompts.items()}
    
    sorted_summaries = dict(sorted(summaries.items(), key=lambda item: item[1], reverse=True))
    
    logger.debug(f"Summaries: {len(sorted_summaries)}")
    
    if num_rows != 'all':
        num_rows = int(num_rows)
        sorted_summaries = dict(list(sorted_summaries.items())[:num_rows])
    
    return sorted_summaries

def analyze_difficulty(logs, grade, subject, start_date, end_date, class_id, admission_year, num_rows='20'):
    filtered_logs = [log for log in logs if log.grade == grade and log.subject == subject and log.class_id == class_id and log.admission_year == admission_year and start_date <= log.prompt_datetime <= end_date]
    if not filtered_logs:
        flash("指定された条件ではデータが見つかりませんでした。", "warning")
        return {}
    
    difficulty_counts = {}
    for log in filtered_logs:
        difficulty_counts[log.difficulty] = difficulty_counts.get(log.difficulty, 0) + 1
    
    # 難易度でソート
    sorted_difficulty_counts = dict(sorted(difficulty_counts.items()))
    
    # num_rowsのフィルタ適用
    if num_rows != 'all':
        num_rows = int(num_rows)
        sorted_difficulty_counts = dict(list(sorted_difficulty_counts.items())[:num_rows])
    
    return sorted_difficulty_counts

@prompt_analysis_bp.route('/prompt_analysis', methods=['GET', 'POST'])
def prompt_analysis_page():
    if not session.get('is_staff') == 1:
        flash('この機能にアクセスする権限がありません。ページをリフレッシュすると元へ戻ります。', 'error')
        return redirect(url_for('main'))

    form = CSRFForm()

    try:
        logs = Log.query.all()  # すべてのログデータを取得

        if not logs:
            # logs テーブルが空の場合、users テーブルの入学年度を使用
            available_admission_years = sorted(list(set([str(user.admission_year) for user in User.query.filter(User.admission_year != 9999).all()])), reverse=True)

            # logs が空であるメッセージを表示
            flash('ログデータが存在しません。新しいデータが登録されるまで表示できるデータはありません。', 'info')

            # クラスや科目の選択肢をデータベースから取得
            all_classes = db.session.query(User.class_id).distinct().filter(User.class_id != '0').order_by(User.class_id).all()
            all_classes = [cls[0] for cls in all_classes]
            all_subjects = db.session.query(Log.subject).distinct().order_by(Log.subject.desc()).all()
            all_subjects = [subject[0] for subject in all_subjects]

            return render_template(
                'prompt_analysis.html',
                grade=1,
                subject=all_subjects[0] if all_subjects else '英語',
                class_id=all_classes[0] if all_classes else '1A',
                available_classes=all_classes,
                available_subjects=all_subjects,
                admission_year=available_admission_years[0] if available_admission_years else None,
                available_admission_years=available_admission_years,
                start_date=Config.DEFAULT_FROM_DATE,
                end_date=Config.DEFAULT_TO_DATE,
                analysis_results={},
                difficulty_counts={},
                similarity_threshold=0.5,
                num_rows='20',
                form=form
            )

        # logsが存在する場合の処理
        latest_admission_year = db.session.query(func.max(Log.admission_year)).scalar() or 2024

        admission_year = int(request.args.get('admission_year', str(latest_admission_year)))
        grade = int(request.args.get('grade', '1'))

        # クラスや科目の選択肢をデータベースから取得
        all_classes = db.session.query(User.class_id).distinct().filter(User.class_id != '0').order_by(User.class_id).all()
        all_classes = [cls[0] for cls in all_classes]
        all_subjects = db.session.query(Log.subject).distinct().order_by(Log.subject.desc()).all()
        all_subjects = [subject[0] for subject in all_subjects]

        subject = request.args.get('subject', all_subjects[0] if all_subjects else '英語')
        class_id = request.args.get('class_id', all_classes[0] if all_classes else '1A')
        similarity_threshold = float(request.args.get('similarity_threshold', '0.5'))
        num_rows = request.args.get('num_rows', '20')

        start_date_str = request.args.get('start_date', Config.DEFAULT_FROM_DATE)
        end_date_str = request.args.get('end_date', Config.DEFAULT_TO_DATE)

        # from_date と to_date の日付変換
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d')

        if start_date > end_date:
            raise ValueError('開始日が終了日より後です。')

        logs = Log.query.filter(
            Log.prompt_datetime.between(start_date, end_date),
            Log.class_id == class_id,
            Log.admission_year == admission_year,
            Log.grade == grade,
            Log.subject == subject
        ).all()
        logger.debug(f"Retrieved logs: {len(logs)}")

        analysis_results = {}
        difficulty_counts = {}

        if 'analyze_prompts' in request.args:
            analysis_results = analyze_prompts(logs, grade, subject, start_date, end_date, class_id, admission_year, similarity_threshold, num_rows)
        elif 'analyze_difficulty' in request.args:
            difficulty_counts = analyze_difficulty(logs, grade, subject, start_date, end_date, class_id, admission_year, num_rows)

        # 入学年度の選択肢を取得
        available_admission_years = db.session.query(Log.admission_year).distinct().order_by(Log.admission_year.desc()).all()
        available_admission_years = [year[0] for year in available_admission_years if year[0] != 9999]

        return render_template('prompt_analysis.html', 
                               grade=grade, 
                               subject=subject,
                               class_id=class_id,
                               available_classes=all_classes,
                               available_subjects=all_subjects,
                               admission_year=admission_year,
                               available_admission_years=available_admission_years,
                               start_date=start_date.strftime('%Y-%m-%d'), 
                               end_date=end_date.strftime('%Y-%m-%d'),
                               analysis_results=analysis_results,
                               difficulty_counts=difficulty_counts,
                               similarity_threshold=similarity_threshold,
                               num_rows=num_rows,
                               form=form,
                               selected_subject=subject)

    except ValueError as e:
        logger.error(f"Error parsing input: {e}")
        flash(f'入力値が不正です: {str(e)}', 'error')
        return redirect(url_for('prompt_analysis.prompt_analysis_page'))
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        flash('予期せぬエラーが発生しました。', 'error')
        return redirect(url_for('prompt_analysis.prompt_analysis_page'))

@prompt_analysis_bp.route('/get_prompts_by_difficulty', methods=['GET'])
def get_prompts_by_difficulty():
    try:
        difficulty = request.args.get('difficulty', type=int)
        grade = request.args.get('grade', type=int)
        subject = request.args.get('subject')
        class_id = request.args.get('class_id')
        admission_year = request.args.get('admission_year', type=int)
        start_date_str = request.args.get('start_date', Config.DEFAULT_FROM_DATE)
        end_date_str = request.args.get('end_date', Config.DEFAULT_TO_DATE)

        # from_date と to_date の日付変換
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
        num_rows = request.args.get('num_rows', '20')  # ここで num_rows を取得

        logs = Log.query.filter(
            Log.prompt_datetime.between(start_date, end_date),
            Log.grade == grade,
            Log.subject == subject,
            Log.class_id == class_id,
            Log.admission_year == admission_year,
            Log.difficulty == difficulty
        ).order_by(Log.prompt_datetime.desc()).all()

        if not logs:
            return jsonify({'error': 'No data found for selected difficulty'}), 404

        prompts_and_responses = [
            {
                'prompt': log.prompt,
                'response': log.response,
                'prompt_datetime': log.prompt_datetime.strftime('%Y-%m-%d %H:%M:%S')
            } 
            for log in logs
        ]

        # 表示行数の制限を適用
        if num_rows != 'all':
            num_rows = int(num_rows)
            prompts_and_responses = prompts_and_responses[:num_rows]

        return jsonify(prompts_and_responses)

    except Exception as e:
        logger.error(f"Error in get_prompts_by_difficulty: {e}")
        return jsonify({'error': 'An error occurred while retrieving data'}), 500