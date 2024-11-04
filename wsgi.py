import sys
import os
from flask import render_template

# プロジェクトディレクトリをsys.pathに追加
project_home = '/home/59er/mysite'
if project_home not in sys.path:
    sys.path = [project_home] + sys.path

# Flaskアプリケーションをインポート
from app import app as flask_app

# エラーハンドリング関数
def handle_error(e):
    try:
        return flask_app.errorhandler(e.code)(e)
    except Exception:
        # アプリケーションのエラーハンドラーが機能しない場合のフォールバック
        return render_template('500.html'), 500

# WSGIアプリケーション関数
def application(environ, start_response):
    try:
        return flask_app(environ, start_response)
    except Exception as e:
        # すべての例外をキャッチし、エラーハンドリング関数に渡す
        return handle_error(e)(environ, start_response)
