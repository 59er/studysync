from flask import Blueprint, render_template, request, session, flash, redirect, url_for
from ..config import Config
import json
import os
from datetime import datetime
from .teacher_main import teacher_bp
from ..utils import load_subjects


subject_management_bp = Blueprint('subject_management', __name__)
SUBJECTS_FILE = os.path.join(os.path.dirname(__file__), 'data', 'subjects.json')

def load_subjects():
    """JSONファイルから科目リストを読み込む関数"""
    subjects = []
    try:
        with open(Config.SUBJECTS_FILE, 'r', encoding='utf-8') as f:
            subjects = json.load(f)
        print("Subjects loaded successfully:", subjects)  # 確認のため出力
    except Exception as e:
        print("Error reading JSON file in load_subjects:", e)
    return subjects


@subject_management_bp.route('/subject_selection', methods=['GET', 'POST'])
def subject_selection():
    if 'session_id' not in session:
        session.clear()
        flash("セッションが切れました。再度ログインしてください。", "warning")
        return redirect(url_for('login.login'))
    
    # load_subjects が正しくデータを返しているか確認
    subjects = load_subjects()
    print("DEBUG: subjects (in subject_selection function) =", subjects)  # 追加

    if request.method == 'POST':
        selected_subject = request.form.get('subject')
        if selected_subject:
            session['selected_subject'] = selected_subject
            return redirect(url_for('teacher_main.teacher_main'))

    # subjects がテンプレートに渡されるか確認
    return render_template('subject_selection.html', subjects=subjects)

def save_subjects(subjects):
    """教科リストをJSONファイルに保存"""
    try:
        with open(Config.SUBJECTS_FILE, 'w', encoding='utf-8') as f:
            json.dump(subjects, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error saving subjects: {e}")

@subject_management_bp.route('/subject_management', methods=['GET', 'POST'])
def subject_management_page():
    if not session.get('is_staff') == 1:
        flash('この機能にアクセスする権限がありません。', 'error')
        return redirect(url_for('teacher_main.teacher_main'))

    if request.method == 'POST':
        action = request.form.get('action')
        subjects = load_subjects()
        
        try:
            if action == 'add':
                subject_name = request.form.get('subject_name')
                if not subject_name:
                    flash('教科名を入力してください。', 'error')
                elif subject_name in subjects:
                    flash('この教科は既に存在します。', 'error')
                else:
                    subjects.append(subject_name)
                    save_subjects(subjects)
                    flash('教科を追加しました。', 'success')

            elif action == 'update':
                old_name = request.form.get('old_name')
                new_name = request.form.get('new_name')
                if old_name in subjects:
                    idx = subjects.index(old_name)
                    subjects[idx] = new_name
                    save_subjects(subjects)
                    flash('教科名を更新しました。', 'success')
                else:
                    flash('指定された教科が見つかりません。', 'error')

            elif action == 'delete':
                subject_name = request.form.get('subject_name')
                if subject_name in subjects:
                    subjects.remove(subject_name)
                    save_subjects(subjects)
                    flash('教科を削除しました。', 'success')
                else:
                    flash('指定された教科が見つかりません。', 'error')

        except Exception as e:
            flash('エラーが発生しました。', 'error')
            print(f"Error: {str(e)}")

    subjects = load_subjects()
    return render_template('subject_management.html', subjects=subjects)