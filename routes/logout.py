from flask import Blueprint, session, flash, redirect, url_for, make_response, current_app
from .. import csrf

# Blueprintを定義
logout_bp = Blueprint('logout', __name__)

# CSRF保護をBlueprintに適用
csrf.init_app(current_app)

@logout_bp.route('/logout', methods=['POST'])
def logout():
    try:
        if session.get('logged_in') and session.get('is_staff') == 1:
            updateQAHistory()  # 教師用の履歴更新を試みる
    except Exception as e:
        current_app.logger.error(f"QA History update error during logout: {str(e)}")
    
    try:
        session.clear()
        flash('ログアウトしました。', 'success')
    except Exception as e:
        current_app.logger.error(f"Logout error: {str(e)}")
        flash('ログアウト中にエラーが発生しました。', 'error')

    response = make_response(redirect(url_for('login.login')))
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


