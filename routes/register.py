from flask import Blueprint, render_template, request, session, flash, redirect, url_for, current_app
import pandas as pd
from ..models import db, User, NGWord
from werkzeug.utils import secure_filename
from datetime import datetime
import os
from werkzeug.security import generate_password_hash
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
import logging
from flask_wtf import FlaskForm
from wtforms import FileField, SubmitField
from wtforms.validators import DataRequired
import pytz

# ロガーの設定
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Flask-WTFフォーム
class UploadForm(FlaskForm):
    user_file = FileField('ユーザー情報のCSVファイル', validators=[DataRequired()])
    submit = SubmitField('アップロード')

class NGWordForm(FlaskForm):
    ng_word_file = FileField('NGワードのCSVファイル', validators=[DataRequired()])
    submit = SubmitField('アップロード')

register_bp = Blueprint('register', __name__)

@register_bp.route('/register', methods=['GET', 'POST'])
def register_page():
    if not session.get('is_staff') == 1:
        flash('この機能にアクセスする権限がありません。', 'error')
        return redirect(url_for('main'))

    user_form = UploadForm()
    ng_word_form = NGWordForm()

    if request.method == 'POST':
        logger.info("POST request received")
        
        # ユーザーファイルのアップロード処理
        if user_form.validate_on_submit() and 'user_file' in request.files:
            user_file = request.files['user_file']
            if user_file.filename == '':
                flash('ファイルが選択されていません。', 'error')
                return redirect(url_for('register.register_page'))

            if allowed_file(user_file.filename):
                try:
                    logger.info("ユーザーファイルのアップロード処理開始")
                    filename = secure_filename(user_file.filename)
                    filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
                    user_file.save(filepath)
                    logger.info(f"ファイルが保存されました: {filepath}")

                    # データベースへの処理を実行
                    new_users, updated_users, skipped_users = process_user_file(filepath)
                    logger.info(f"処理結果 - 新規: {new_users}, 更新: {updated_users}, スキップ: {skipped_users}")

                    success_message = f'ユーザー登録が完了しました。新規: {new_users}名, 更新: {updated_users}名, スキップ: {skipped_users}名'
                    flash(success_message, 'success')
                    logger.info(f"Success message set: {success_message}")

                except ValueError as ve:
                    error_message = f'バリデーションエラー: {str(ve)}'
                    flash(error_message, 'error')
                    logger.error(f'Validation error: {str(ve)}')
                except SQLAlchemyError as se:
                    error_message = f'データベースエラー: {str(se)}'
                    flash(error_message, 'error')
                    logger.error(f'Database error: {str(se)}')
                except Exception as e:
                    error_message = f'予期せぬエラーが発生しました: {str(e)}'
                    flash(error_message, 'error')
                    logger.error(f'Unexpected error: {str(e)}')
                finally:
                    if os.path.exists(filepath):
                        logger.info("一時ファイルの削除")
                        os.remove(filepath)
                
                return redirect(url_for('register.register_page'))

        # NGワードファイルのアップロード処理
        elif ng_word_form.validate_on_submit() and 'ng_word_file' in request.files:
            ng_word_file = request.files['ng_word_file']
            if ng_word_file.filename == '':
                flash('ファイルが選択されていません。', 'error')
                return redirect(url_for('register.register_page'))

            if allowed_file(ng_word_file.filename):
                try:
                    filename = secure_filename(ng_word_file.filename)
                    filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
                    logger.info(f"NGワードファイルの保存先: {filepath}")
                    
                    ng_word_file.save(filepath)
                    logger.info("NGワードファイルの保存完了")

                    new_ng_words, updated_ng_words, skipped_ng_words = process_ng_word_file(filepath)
                    logger.info(f"NGワード処理結果 - 新規: {new_ng_words}, 更新: {updated_ng_words}, スキップ: {skipped_ng_words}")

                    success_message = f'{new_ng_words}個のNGワードが正常に登録されました。'
                    flash(success_message, 'success')
                    logger.info(f"Success message set: {success_message}")

                except Exception as e:
                    error_message = f'NGワードの処理中にエラーが発生しました: {str(e)}'
                    flash(error_message, 'error')
                    logger.error(f"Error in NG word processing: {str(e)}")
                finally:
                    if os.path.exists(filepath):
                        os.remove(filepath)
                        logger.info(f"一時ファイル削除完了: {filepath}")

                return redirect(url_for('register.register_page'))

    return render_template('register.html', user_form=user_form, ng_word_form=ng_word_form)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'csv'}

def validate_user_data(df):
    required_columns = ['last_name', 'first_name', 'password', 'email', 'grade_id', 'class_id', 'is_staff', 'user_id', 'admission_year']
    for column in required_columns:
        if column not in df.columns:
            raise ValueError(f"必要なカラム '{column}' が見つかりません。")

def validate_user_row(row, index, is_existing_user=False):
    required_fields = ['last_name', 'email', 'user_id', 'grade_id', 'class_id', 'is_staff', 'admission_year']
    
    if not is_existing_user:
        required_fields.append('password')
    
    for field in required_fields:
        if pd.isna(row[field]) or str(row[field]).strip() == '':
            raise ValueError(f"行 {index + 2}: 必須フィールド '{field}' が空です。ユーザーID: {row.get('user_id', '不明')}")

def process_user_file(filepath):
    logger.info("ユーザーファイルの処理開始")
    jst = pytz.timezone('Asia/Tokyo')
    current_time_jst = datetime.now(jst)
    
    users = []
    updated_count = 0
    skipped_count = 0

    try:
        user_df = pd.read_csv(filepath, dtype=str)
        user_df = user_df.fillna('')
        logger.info(f"CSVファイル読み込み完了: {len(user_df)}行")

        validate_user_data(user_df)
        logger.info("カラムバリデーション完了")

        existing_users = {user.user_id: user for user in User.query.all()}
        current_user_id = session.get('user_id')

        for index, row in user_df.iterrows():
            try:
                user_id = row['user_id']
                existing_user = existing_users.get(user_id)

                validate_user_row(row, index, is_existing_user=bool(existing_user))

                if existing_user:
                    logger.info(f"ユーザー更新: {user_id}")
                    existing_user.last_name = row['last_name']
                    existing_user.first_name = row['first_name']
                    existing_user.email = row['email']
                    existing_user.grade_id = int(row['grade_id'])
                    existing_user.class_id = row['class_id']
                    existing_user.is_staff = str(row['is_staff']).lower() == 'true'
                    existing_user.admission_year = int(row['admission_year'])
                    existing_user.updated_at = current_time_jst
                    existing_user.updated_by = current_user_id
                    
                    if row['password'].strip():
                        existing_user.password = generate_password_hash(row['password'])
                    
                    updated_count += 1
                else:
                    logger.info(f"新規ユーザー作成: {user_id}")
                    hashed_password = generate_password_hash(row['password'])
                    new_user = User(
                        user_id=user_id,
                        last_name=row['last_name'],
                        first_name=row['first_name'] if row['first_name'].strip() else None,
                        password=hashed_password,
                        email=row['email'],
                        grade_id=int(row['grade_id']),
                        class_id=row['class_id'],
                        is_staff=str(row['is_staff']).lower() == 'true',
                        admission_year=int(row['admission_year']),
                        created_at=current_time_jst,
                        updated_at=current_time_jst,
                        created_by=current_user_id,
                        updated_by=current_user_id
                    )
                    users.append(new_user)

            except ValueError as ve:
                logger.error(f"行 {index + 2} の処理中にエラー: {str(ve)}")
                raise

        if users:
            db.session.add_all(users)
            logger.info(f"{len(users)}件の新規ユーザーをコミット準備完了")

        db.session.commit()
        logger.info("データベース更新完了")

    except ValueError as ve:
        logger.error(f"バリデーションエラー: {str(ve)}")
        db.session.rollback()
        raise
    except SQLAlchemyError as se:
        logger.error(f"データベースエラー: {str(se)}")
        db.session.rollback()
        raise
    except Exception as e:
        logger.error(f"予期せぬエラー: {str(e)}")
        db.session.rollback()
        raise

    return len(users), updated_count, skipped_count

def process_ng_word_file(filepath):
    logger.info("NGワードファイルの処理開始")
    try:
        existing_count = NGWord.query.count()
        logger.info(f"既存のNGワード数: {existing_count}")

        NGWord.query.delete()
        logger.info("既存のNGワードを削除完了")

        new_ng_words = []
        with open(filepath, 'r', encoding='utf-8') as file:
            for line in file:
                word = line.strip()
                if word:
                    new_ng_words.append(NGWord(ng_word=word))
                    logger.debug(f"NGワード追加: {word}")

        db.session.add_all(new_ng_words)
        db.session.commit()
        logger.info(f"新規NGワード {len(new_ng_words)}件 の登録完了")

        return len(new_ng_words), 0, existing_count
    
    except UnicodeDecodeError as e:
        logger.error(f"ファイルエンコーディングエラー: {str(e)}")
        raise ValueError(f"ファイルの文字コードに問題があります。UTF-8で保存してください。")
    except Exception as e:
        logger.error(f"NGワード処理中の予期せぬエラー: {str(e)}")
        db.session.rollback()
        raise
