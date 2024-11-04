from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
from flask_wtf import FlaskForm
from wtforms import PasswordField
from ..models import User
from .. import db
import re
import uuid

bp_common = Blueprint('common', __name__)

class PasswordForm(FlaskForm):
    current_password = PasswordField('現在のパスワード')
    new_password = PasswordField('新しいパスワード')
    confirm_new_password = PasswordField('新しいパスワード（確認用）')

@bp_common.route('/change_password', methods=['GET', 'POST'])
def change_password():
    if 'user_id' not in session or 'session_id' not in session:
        session.clear()  # セッションをクリアして再ログインを促す
        flash("セッションが切れました。再度ログインしてください。", "warning")
        return redirect(url_for('login.login'))

    form = PasswordForm()
    if request.method == 'POST' and form.validate_on_submit():
        current_password = request.form['current_password']
        new_password = request.form['new_password']
        confirm_new_password = request.form['confirm_new_password']

        # パスワードのバリデーション
        if len(new_password) < 8:
            flash("パスワードは8文字以上である必要があります。", "error")
            return render_template('change_password.html', form=form, password_changed=False)
        elif not re.search(r'[A-Z]', new_password):
            flash("パスワードには少なくとも1つの大文字が含まれている必要があります。", "error")
            return render_template('change_password.html', form=form, password_changed=False)
        elif not re.search(r'[a-z]', new_password):
            flash("パスワードには少なくとも1つの小文字が含まれている必要があります。", "error")
            return render_template('change_password.html', form=form, password_changed=False)
        elif not re.search(r'\d', new_password):
            flash("パスワードには少なくとも1つの数字が含まれている必要があります。", "error")
            return render_template('change_password.html', form=form, password_changed=False)
        elif new_password != confirm_new_password:
            flash("新しいパスワードと確認用パスワードが一致しません。", "error")
            return render_template('change_password.html', form=form, password_changed=False)
        else:
            user_id = session.get('user_id')
            user = User.query.filter_by(user_id=user_id).first()

            if not user:
                session.clear()  # ユーザーが見つからない場合、セッションをクリア
                flash("ユーザーが見つかりません。再度ログインしてください。", "error")
                return redirect(url_for('login.login'))

            # 現在のパスワードの確認
            if not check_password_hash(user.password, current_password):
                flash("現在のパスワードが間違っています。", "error")
                return render_template('change_password.html', form=form, password_changed=False)
            # 新しいパスワードが現在のパスワードと同じかを確認
            elif check_password_hash(user.password, new_password):
                flash("新しいパスワードは現在のパスワードと異なる必要があります。", "error")
                return render_template('change_password.html', form=form, password_changed=False)
            else:
                # 新しいパスワードを保存
                try:
                    user.password = generate_password_hash(new_password)
                    db.session.commit()
                    flash("パスワードが正常に変更されました。", "success")

                    # セッションIDを再生成
                    session['session_id'] = str(uuid.uuid4())

                    # パスワード変更ページに留まる
                    return render_template('change_password.html', form=form, password_changed=True)
                except Exception as e:
                    db.session.rollback()
                    flash(f"パスワード変更中にエラーが発生しました: {str(e)}", "error")
                    return render_template('change_password.html', form=form, password_changed=False)

    # GETリクエストの場合、またはその他の場合
    return render_template('change_password.html', form=form, password_changed=False)