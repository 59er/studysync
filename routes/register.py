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
        flash('この機能にアクセスする権限がありません。ページをリフレッシュすると元へ戻ります。', 'error')
        return redirect(url_for('main'))

    user_form = UploadForm()
    ng_word_form = NGWordForm()

    if request.method == 'POST':
        print("POST request received")
        if user_form.validate_on_submit() and 'user_file' in request.files:
            user_file = request.files['user_file']
            if user_file.filename == '':
                flash('ファイルが選択されていません。', 'error')
                return redirect(url_for('register.register_page'))

            if allowed_file(user_file.filename):
                try:
                    logging.info("ファイルのアップロード処理開始")
                    filename = secure_filename(user_file.filename)
                    filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
                    user_file.save(filepath)
                    logging.info(f"ファイルが保存されました: {filepath}")

                    # データベースへの処理を実行
                    new_users, updated_users, skipped_users = process_user_file(filepath)
                    logging.info(f"新規ユーザー: {new_users}, 更新されたユーザー: {updated_users}, スキップされたユーザー: {skipped_users}")

                    # 成功メッセージを追加
                    # flash(f'{new_users} 人のユーザーが追加され、{updated_users} 人のユーザーが更新されました。', 'success')
                    flash(f'アップロードが完了しました。新規ユーザー: {new_users}, 更新されたユーザー: {updated_users}, スキップされたユーザー: {skipped_users}', 'success')

                    # デバッグ用にセッションのフラッシュメッセージを確認
                    print("Flashed messages:", session.get('_flashes', []))  # 追加

                except ValueError as ve:
                    flash(f'バリデーションエラー: {str(ve)}', 'error')
                    logging.error(f'Validation error: {str(ve)}')
                except SQLAlchemyError as se:
                    flash(f'データベースエラー: {str(se)}', 'error')
                    logging.error(f'Database error: {str(se)}')
                except Exception as e:
                    flash(f'予期せぬエラーが発生しました: {str(e)}', 'error')
                    logging.error(f'Unexpected error: {str(e)}')
                finally:
                    if os.path.exists(filepath):
                        logging.info("一時ファイルの削除")
                        os.remove(filepath)
                
                return redirect(url_for('register.register_page'))  # ここでリダイレクトが起きる

        elif ng_word_form.validate_on_submit() and 'ng_word_file' in request.files:
            ng_word_file = request.files['ng_word_file']
            if ng_word_file.filename == '':
                flash('ファイルが選択されていません。', 'error')
                return redirect(url_for('register.register_page'))

            if allowed_file(ng_word_file.filename):

                try:
                    filename = secure_filename(ng_word_file.filename)
                    filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
                    print(f"Saving file to: {filepath}")  # ファイルパスの確認                    ng_word_file.save(filepath)

                    new_ng_words, updated_ng_words, skipped_ng_words = process_ng_word_file(filepath)

                    flash(f'{new_ng_words} 個のNGワードが追加され、{updated_ng_words} 個のNGワードが更新されました。', 'success')

                except Exception as e:
                    flash(f'NGワードの処理中にエラーが発生しました: {str(e)}', 'error')
                    logging.error(f'Error processing NG words: {str(e)}')
                finally:
                    if os.path.exists(filepath):
                        os.remove(filepath)
            else:
                print("File not allowed:", ng_word_file.filename)
                return redirect(url_for('register.register_page'))

    # GET リクエストに対してフラッシュメッセージを表示
    return render_template('register.html', user_form=user_form, ng_word_form=ng_word_form)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'csv'}

def validate_user_data(df):
    required_columns = ['last_name', 'first_name', 'password', 'email', 'grade_id', 'class_id', 'is_staff', 'user_id', 'admission_year']
    for column in required_columns:
        if column not in df.columns:
            raise ValueError(f"必要なカラム '{column}' が見つかりません。")


def validate_user_row(row, index, is_existing_user=False):
    """ 必須フィールドが空でないかを確認する関数 """
    required_fields = ['last_name', 'email', 'user_id', 'grade_id', 'class_id', 'is_staff', 'admission_year']
    
    # 新規ユーザーの場合はパスワードも必須
    if not is_existing_user:
        required_fields.append('password')
    
    for field in required_fields:
        if not row[field].strip():
            raise ValueError(f"行 {index + 2}: 必須フィールド '{field}' が空です。ユーザーID: {row.get('user_id', '不明')}")

def process_user_file(filepath):
    # JSTタイムゾーンを指定
    jst = pytz.timezone('Asia/Tokyo')
    current_time_jst = datetime.now(jst)
    
    users = []
    updated_count = 0
    skipped_count = 0

    try:
        user_df = pd.read_csv(filepath, dtype=str)
        user_df = user_df.fillna('')  # 空の値を空文字列に置換

        existing_users = {user.user_id: user for user in User.query.all()}
        current_user_id = session.get('user_id')  # 現在の管理者のIDを取得

        for index, row in user_df.iterrows():
            user_id = row['user_id']
            existing_user = existing_users.get(user_id)

            # 必須フィールドのバリデーション
            validate_user_row(row, index, is_existing_user=bool(existing_user))

            if existing_user:
                # 更新処理
                existing_user.last_name = row['last_name']
                existing_user.first_name = row['first_name']
                existing_user.email = row['email']
                existing_user.grade_id = int(row['grade_id'])
                existing_user.class_id = row['class_id']
                existing_user.is_staff = row['is_staff'].lower() == 'true'
                existing_user.admission_year = int(row['admission_year'])
                existing_user.updated_at = current_time_jst  # JSTで更新日時を設定
                existing_user.updated_by = current_user_id
                if row['password'].strip():  # パスワードが提供されている場合のみ更新
                    existing_user.password = generate_password_hash(row['password'])
                updated_count += 1
            else:
                # 新規登録処理
                hashed_password = generate_password_hash(row['password'])
                new_user = User(
                    user_id=user_id,
                    last_name=row['last_name'],
                    first_name=row['first_name'] if row['first_name'].strip() else None,
                    password=hashed_password,
                    email=row['email'],
                    grade_id=int(row['grade_id']),
                    class_id=row['class_id'],
                    is_staff=row['is_staff'].lower() == 'true',
                    admission_year=int(row['admission_year']),
                    created_at=current_time_jst,  # JSTで作成日時を設定
                    updated_at=current_time_jst,
                    created_by=current_user_id,
                    updated_by=current_user_id
                )
                users.append(new_user)

        if users:
            db.session.add_all(users)
        db.session.commit()

    except ValueError as ve:
        logging.error(f"Validation error in user file: {str(ve)}")
        db.session.rollback()
        raise ve  # ValueErrorの場合は再度例外を投げる
    except SQLAlchemyError as se:
        logging.error(f"Database error: {str(se)}")
        db.session.rollback()
        raise se
    except Exception as e:
        logging.error(f"Unexpected error processing user file: {str(e)}")
        db.session.rollback()
        raise

    return len(users), updated_count, skipped_count


def process_ng_word_file(filepath):
    try:
        # 既存のNGワードを全て削除
        NGWord.query.delete()

        # 新しいNGワードを追加
        new_ng_words = []
        with open(filepath, 'r', encoding='utf-8') as file:  # UTF-8エンコーディングを指定
            for line in file:
                word = line.strip()
                new_ng_words.append(NGWord(ng_word=word))

        db.session.add_all(new_ng_words)
        db.session.commit()

        return len(new_ng_words), 0, 0  # 新規追加、更新、スキップの数
    
    except UnicodeDecodeError as e:
        logging.error(f"Encoding error: {str(e)}")
        raise ValueError(f"ファイルの文字コードに問題があります。ファイルはUTF-8で保存してください。エラー: {str(e)}")
    except Exception as e:
        logging.error(f"Unexpected error processing NG word file: {str(e)}")
        db.session.rollback()  # コミット前に例外が発生した場合、ロールバックを行う
        raise


