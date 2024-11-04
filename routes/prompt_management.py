from flask import Blueprint, request, jsonify, session, render_template, flash, redirect, url_for
from .. import db
from ..models import SubjectPrompt
from flask_wtf import FlaskForm
from wtforms import HiddenField
from datetime import datetime
import pytz
import os
from ..config import Config 
import json

prompt_bp = Blueprint('prompt_bp', __name__)

# CSRF用のフォームを定義
class CSRFForm(FlaskForm):
    csrf_token = HiddenField()

def get_subjects():
    """JSONファイルから科目リストを取得する"""
    try:
        if os.path.exists(Config.SUBJECTS_FILE):
            with open(Config.SUBJECTS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:
            # デフォルトの教科リストを使用
            return Config.DEFAULT_SUBJECTS
    except Exception as e:
        print(f"Error loading subjects: {e}")
        return Config.DEFAULT_SUBJECTS

@prompt_bp.route('/update_prompt', methods=['GET', 'POST'])
def update_prompt():
    if not session.get('is_staff') == 1:
        flash('この機能にアクセスする権限がありません。ページをリフレッシュすると元へ戻ります。', 'error')
        return redirect(url_for('main'))

    form = CSRFForm()  # フォームを初期化

    if request.method == 'POST' and form.validate_on_submit():
        subject = request.form.get('subject')
        new_prompt = request.form.get('prompt_text')
        
        # JSTでの現在時刻を取得
        jst = pytz.timezone('Asia/Tokyo')
        current_time_jst = datetime.now(jst)

        # updated_date の最新の行を取得する
        subject_entry = SubjectPrompt.query.filter_by(subject=subject).order_by(SubjectPrompt.updated_date.desc()).first()

        if subject_entry:
            subject_entry.prompt_text = new_prompt
            subject_entry.updated_date = current_time_jst
        else:
            new_entry = SubjectPrompt(subject=subject, prompt_text=new_prompt, updated_date=current_time_jst)
            db.session.add(new_entry)

        db.session.commit()
        flash('システムプロンプトが、正常に更新されました。', 'success')
        return redirect(url_for('prompt_bp.update_prompt', subject=subject))  

    # GETリクエストの場合、またはPOST後のリダイレクト
    selected_subject = request.args.get('subject') or request.form.get('subject') or '英語'  # デフォルト値を設定
    
    # 教科リストを取得
    subjects_list = get_subjects()
    
    # データベースに登録されているプロンプト情報を取得
    subjects = SubjectPrompt.query.all()
    subjects_dict = {subject.subject: subject.prompt_text for subject in subjects}
    
    return render_template('edit_prompts.html', 
                         form=form, 
                         subjects=subjects_list, 
                         prompts=subjects_dict, 
                         selected_subject=selected_subject)
