from flask import Blueprint, request, jsonify, flash, redirect, url_for, current_app, session, render_template, abort, Response, stream_with_context
import openai
from openai import OpenAI
import tiktoken
import re
import logging
from datetime import datetime, timedelta
import pytz
import uuid
import tiktoken
from ..models import Setting, Log, NGWord, SubjectPrompt, User, NGWord
from .. import db
import logging
logging.basicConfig(level=logging.DEBUG)
import traceback 
from sqlalchemy import and_, func, asc
from sqlalchemy.exc import SQLAlchemyError
from flask_wtf.csrf import CSRFProtect
import json
import html
import logging
logger = logging.getLogger(__name__)
from markupsafe import escape
import markdown
from markupsafe import Markup
import bleach

chatbot = Blueprint('chatbot', __name__)

def initialize_openai():
    openai.api_key = current_app.config['OPENAI_API_KEY']
    
ng_words = []  # グローバル変数としてNGワードをキャッシュ

def load_ng_words():
    global ng_words
    ng_words = [ng_word.ng_word for ng_word in NGWord.query.all()]
    
def contains_ng_word(text):
    """NGワードが含まれているかをチェック"""
    return any(word.lower() in text.lower() for word in ng_words)

@chatbot.route('/get_ng_words', methods=['GET'])
def get_ng_words():
    try:
        ng_words = [ng_word.ng_word for ng_word in NGWord.query.all()]
        return jsonify({'ng_words': ng_words}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
def sanitize_input(text):
    """入力値の一貫したサニタイズ処理"""
    if text is None:
        return ''
    # HTMLエスケープ
    escaped = bleach.clean(str(text), strip=True)
    return escaped    
    

@chatbot.route('/generate_response', methods=['POST'])
def generate_response():
    try:
        client = OpenAI(api_key=current_app.config['OPENAI_API_KEY'])

        data = request.get_json()
        # prompt = data.get('prompt')
        # prompt = escape(data.get('prompt', ''))
        prompt = sanitize_input(data.get('prompt'))
        subject = data.get('subject')
        grade_level = data.get('grade_level')
        current_qa_id = data.get('qa_id')
        conversation_history = data.get('conversation_history', [])

        if not prompt or not subject:
            return jsonify({'error': 'プロンプトまたは科目が指定されていません。'}), 400
            
        if not ng_words:
            load_ng_words()

        if contains_ng_word(prompt):
            return jsonify({'error': 'NGワードが含まれています。入力を修正してください。'}), 400

        latest_subject_prompt = (
            SubjectPrompt.query
            .filter_by(subject=subject)
            .order_by(SubjectPrompt.updated_date.desc())
            .first()
        )
        system_prompt = latest_subject_prompt.prompt_text if latest_subject_prompt else "You are a helpful assistant."

        latest_setting = (
            Setting.query
            .filter_by(subject=subject)
            .order_by(Setting.updated_date.desc())
            .first()
        )

        if not latest_setting:
            raise ValueError(f"No settings found for subject '{subject}' in the database.")

        model = latest_setting.model
        temperature = latest_setting.temperature
        max_tokens = latest_setting.max_response_tokens
        max_question_tokens = latest_setting.max_question_tokens

        # プロンプトのトークン数を計算し、必要に応じてカット
        try:
            encoding = tiktoken.encoding_for_model(model)
            prompt_tokens = encoding.encode(prompt)
            if len(prompt_tokens) > max_question_tokens:
                prompt_tokens = prompt_tokens[:max_question_tokens]
                prompt = encoding.decode(prompt_tokens)
        except Exception as e:
            logging.error(f"Error in token calculation: {str(e)}")

        # 難易度評価
        difficulty_prompt = latest_setting.difficulty_prompt.format(question=prompt)
        difficulty_prompt += "\n難易度を1から5の数字で明示的に示してください。例: '難易度: 2'"

        difficulty_response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are an expert in evaluating the difficulty of academic questions in Japanese."},
                {"role": "user", "content": difficulty_prompt}
            ],
            temperature=temperature,
            max_tokens=max_tokens
        )

        difficulty_text = difficulty_response.choices[0].message.content.strip()
        difficulty_match = re.search(r'難易度[：:は]?\s*(\d)', difficulty_text)
        difficulty = int(difficulty_match.group(1)) if difficulty_match else 3
        difficulty_reason_match = re.search(r'理由[：:]\s*(.*)', difficulty_text)
        difficulty_reason = difficulty_reason_match.group(1).strip() if difficulty_reason_match else "理由は評価されませんでした。"

        # プロンプトの準備
        messages = [
            {"role": "system", "content": system_prompt},
        ]

        # 会話履歴の追加
        for entry in conversation_history:
            messages.append({"role": "user", "content": entry['prompt']})
            messages.append({"role": "assistant", "content": entry['response']})

        # 新しい質問の追加
        messages.append({"role": "user", "content": prompt})

        # OpenAI APIを使用してストリーミングレスポンスを生成
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True  # ストリーミングを有効化
        )

        def generate():
            try:
                full_response = ""
                for chunk in response:
                    if chunk.choices and len(chunk.choices) > 0:
                        delta = chunk.choices[0].delta
                        if hasattr(delta, 'content') and delta.content is not None:
                            chunk_message = delta.content
                            full_response += chunk_message
                            yield f"data: {json.dumps({'content': chunk_message, 'end': False})}\n\n"

                # 最終的な結果を送信
                final_result = {
                    'qa_id': current_qa_id,
                    'difficulty': difficulty,
                    'difficulty_reason': difficulty_reason,
                    'prompt': prompt,
                    'content': full_response,  # フォーマットせずにそのまま送信
                    'end': True
                }
                yield f"data: {json.dumps(final_result)}\n\n"

                # ログを保存
                save_log(prompt, full_response, difficulty, subject, grade_level, current_qa_id)

            except Exception as e:
                logging.error(f"Error in generate function: {e}", exc_info=True)
                yield f"data: {json.dumps({'error': '回答の生成中にエラーが発生しました', 'end': True})}\n\n"

        return Response(stream_with_context(generate()), content_type='text/event-stream')

    except Exception as e:
        logging.error(f"Error in generate_response: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500
        
def format_chunk(chunk):
    # HTMLタグを適用する簡易的な処理
    chunk = chunk.replace('\n', '<br>')
    chunk = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', chunk)
    return chunk


def format_answer(answer):
    formatted_answer = answer.strip()
    math_blocks = []
    
    def save_inline_math(match):
        content = match.group(1).strip()
        return f'\\({content}\\)'

    def save_display_math(match):
        content = match.group(1).strip()
        return f'\\[{content}\\]'

    # 1. まず数式を変換
    formatted_answer = re.sub(r'\$\$(.*?)\$\$', save_display_math, formatted_answer)
    formatted_answer = re.sub(r'\$(.+?)\$', save_inline_math, formatted_answer)

    # 2. 大項目の処理   
    formatted_answer = re.sub(
        r'(?m)^(?:###\s*|(?:\d+)\.\s+)(.+?)(?=\n|$)',
        lambda m: f'<div class="section-block"><h4 class="chat-heading">{m.group(1)}</h4>',
        formatted_answer
    )

    # 3. 太字の見出し処理
    formatted_answer = re.sub(
        r'\*\*(.*?)\*\*[:：]',
        r'<h5 class="chat-subheading">\1：</h5>',
        formatted_answer
    )

    # 4. 通常の太字処理
    formatted_answer = re.sub(
        r'\*\*(.*?)\*\*',
        r'<strong>\1</strong>',
        formatted_answer
    )

    # 5. 箇条書きの処理
    lines = formatted_answer.split('\n')
    processed_lines = []
    in_list = False
    
    for line in lines:
        print(f"\n処理中の行: {line}")
        if line.strip().startswith('-'):
            if not in_list:
                processed_lines.append('<ul class="description-list">')
                in_list = True
            line = re.sub(r'^-\s*(.*?)$', r'<li class="chat-description">\1</li>', line)
        else:
            if in_list:
                processed_lines.append('</ul>')
                in_list = False
        processed_lines.append(line)
    
    if in_list:
        processed_lines.append('</ul>')
    
    formatted_answer = '\n'.join(processed_lines)

    # 6. 段落処理
    paragraphs = formatted_answer.split('\n\n')
    formatted_paragraphs = []
    for p in paragraphs:
        if not p.startswith('<') and not p.endswith('>'):
            p = f'<p>{p}</p>'
        formatted_paragraphs.append(p)
    formatted_answer = '\n'.join(formatted_paragraphs)

    # 7. セクションブロックを閉じる
    if '<div class="section-block">' in formatted_answer:
        formatted_answer = formatted_answer.rstrip() + '</div>'

    # 8. 最後にresponseクラスで全体を囲む
    formatted_answer = f'<div class="response">{formatted_answer}</div>'
    
    return formatted_answer

@chatbot.route('/generate_image', methods=['POST'])
def generate_image():
    try:
        client = OpenAI(api_key=current_app.config['OPENAI_API_KEY'])
        image_prompt = request.form.get("image_prompt")
        
        if not image_prompt:
            return jsonify({'error': 'プロンプトが入力されていません。'}), 400

        if contains_ng_word(image_prompt):
            return jsonify({'error': 'NGワードが含まれています。入力を修正してください。'}), 400

        response = client.images.generate(
            model="dall-e-3",
            prompt=image_prompt,
            size="1024x1024",
            quality="standard",
            n=1
        )
        image_url = response.data[0].url
        return jsonify({'image_url': image_url})
    except Exception as e:
        logging.error(f"Error generating image: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@chatbot.route('/resume_conversation', methods=['POST'])
def resume_conversation():
    try:
        qa_id = request.json.get('qa_id')
        if not qa_id:
            return jsonify({'error': 'QAのIDが提供されていません。'}), 400

        conversation = Log.query.filter_by(qa_id=qa_id).order_by(Log.prompt_datetime).all()
        if not conversation:
            return jsonify({'error': '指定されたQAが見つかりません。'}), 404

        conversation_data = [{
            'prompt': entry.prompt,
            'response': entry.response,
            'difficulty': entry.difficulty,
            'prompt_datetime': entry.prompt_datetime.strftime('%Y-%m-%d %H:%M:%S')
        } for entry in conversation]

        return jsonify({'conversation': conversation_data, 'qa_id': qa_id})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def save_log(prompt, formatted_answer, difficulty, subject, grade_level, current_qa_id):
    jst = pytz.timezone('Asia/Tokyo')
    now = datetime.now(jst)

    user_id = session.get('user_id')
    user = User.query.filter_by(user_id=user_id).first()

    # 教師の場合の特別な設定
    if user and user.is_staff == 1:  # 教師の場合
        school_id = 'default_school_id'
        class_id = '0'
        admission_year = '9999'
        grade_level = 9999
    else:  # 学生の場合
        school_id = 'default_school_id'
        class_id = user.class_id if user and user.class_id else 'Unknown'
        admission_year = user.admission_year if user and user.admission_year else 'Unknown'
        # grade_levelはパラメータとして渡された値をそのまま使用

    session_id = session.get('session_id', str(uuid.uuid4()))
    session['session_id'] = session_id

    response_str = bleach.clean(str(formatted_answer), 
                              tags=['p', 'strong', 'em', 'ul', 'ol', 'li', 'br', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'],
                              strip=True)

    log_data = {
        'session_id': session_id,
        'qa_id': current_qa_id,
        'school_id': school_id,
        'class_id': class_id,
        'user_id': user_id,
        'prompt': prompt,
        'prompt_datetime': now,
        'response': response_str,
        'response_datetime': now,
        'difficulty': difficulty,
        'grade': grade_level,  # 教師の場合は9999、学生の場合は元の値
        'subject': subject,
        'date': now.date(),
        'week': now.isocalendar()[1],
        'month': now.month,
        'year': now.year,
        'hour': now.hour,
        'time_period': get_time_period(now.hour),
        'week_start_date': (now - timedelta(days=now.weekday())).date(),
        'admission_year': admission_year
    }

    try:
        new_log = Log(**log_data)
        db.session.add(new_log)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error saving log: {e}", exc_info=True)
        # エラーログにより詳細な情報を追加
        logging.error(f"Log data that caused error: {log_data}")
        raise

def load_ng_words():
    return [ng_word.ng_word for ng_word in NGWord.query.all()]

def get_time_period(hour):
    if 5 <= hour < 12:
        return 'morning'
    elif 12 <= hour < 17:
        return 'afternoon'
    elif 17 <= hour < 22:
        return 'evening'
    else:
        return 'night'

def get_conversation_history(session_id):
    logs = Log.query.filter_by(session_id=session_id).order_by(Log.prompt_datetime.desc()).limit(10).all()
    conversation_history = []
    for log in reversed(logs):
        conversation_history.append({"role": "user", "content": log.prompt})
        conversation_history.append({"role": "assistant", "content": log.response})
    return conversation_history

@chatbot.route('/get_qa_history', methods=['GET'])
def get_qa_history():
    user_id = session.get('user_id')
    subject = request.args.get('subject')

    # デバッグ用ログ
    # print(f"Debug: user_id={user_id}, subject={subject}")

    if not user_id or not subject:
        # print("Debug: ユーザーIDまたは科目が指定されていません")
        return jsonify({'error': 'ユーザーIDまたは科目が指定されていません。'}), 400

    try:
        # 各 qa_id グループの最新の更新日時と最初の質問を取得
        subquery = db.session.query(
            Log.qa_id,
            func.min(Log.prompt_datetime).label('first_datetime'),
            func.max(Log.prompt_datetime).label('latest_update')
        ).filter(
            Log.user_id == user_id,
            Log.subject == subject
        ).group_by(Log.qa_id).subquery()

        # デバッグ: サブクエリの結果確認
        # print(f"Debug: Subquery result: {subquery}")

        # 最新の更新日時でソートしつつ、各QAセッションの最初の質問を取得
        qa_history = db.session.query(
            Log.qa_id,
            Log.prompt_datetime,
            Log.prompt,
            Log.response,
            subquery.c.latest_update
        ).join(
            subquery,
            and_(
                Log.qa_id == subquery.c.qa_id,
                Log.prompt_datetime == subquery.c.first_datetime
            )
        ).filter(
            Log.user_id == user_id,
            Log.subject == subject
        ).order_by(
            subquery.c.latest_update.desc()
        ).limit(10).all()

        # デバッグ: 取得したQA履歴を表示
        # print(f"Debug: qa_history result: {qa_history}")

        history_data = [{
            'qa_id': str(qa.qa_id),
            'latest_datetime': qa.latest_update.strftime('%Y-%m-%d %H:%M:%S'),
            'latest_prompt': qa.prompt,
            'latest_response': qa.response
        } for qa in qa_history]

        return jsonify(history_data)

    except Exception as e:
        print(f"Error in get_qa_history: {str(e)}")
        return jsonify({'error': 'Q&A履歴の取得中にエラーが発生しました。'}), 500



@chatbot.route('/reset_session', methods=['POST'])
def reset_session():
    session['session_id'] = str(uuid.uuid4())
    return jsonify({'status': 'success'})


@chatbot.route('/clear_session', methods=['POST'])
def clear_session():
    session.clear()  # すべてのセッションデータをクリア
    response = jsonify({'status': 'session cleared'})
    response.set_cookie('session', '', expires=0)  # セッションクッキーも削除
    return response

@chatbot.after_request
def set_csp(response):
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'"
    return response

@chatbot.app_template_filter('markdown')
def markdown_filter(text):
    # MarkdownをHTMLに変換
    html = markdown.markdown(text, extensions=['extra'], output_format='html5')
    
    # 不正なHTMLタグや属性を除去
    clean_html = bleach.clean(
        html,
        tags=['p', 'strong', 'em', 'ul', 'ol', 'li', 'br', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'blockquote', 'code', 'pre', 'img', 'a'],
        attributes={'a': ['href', 'title'], 'img': ['src', 'alt']},
        protocols=['http', 'https', 'mailto'],
        strip=True
    )
    
    return Markup(clean_html)

# 404エラー（ページが見つからない）のハンドラ
@chatbot.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404