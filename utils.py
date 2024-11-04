import os
import json
from flask import current_app

def load_subjects():
    subjects_file = os.path.join(current_app.config['BASE_DIR'], 'data', 'subjects.json')
    try:
        with open(subjects_file, 'r', encoding='utf-8') as f:
            subjects = json.load(f)
        return subjects
    except Exception as e:
        print("Error loading subjects:", e)
        return []
