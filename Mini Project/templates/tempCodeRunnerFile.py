from flask import Flask, render_template, request, redirect, url_for, flash
import os
from compare_logic import create_database, compare_with_database

UPLOAD_FOLDER = "uploaded_videos"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.secret_key = 'your_secret_key'  # Required for flash messages

# 🟢 Initialize DB on first run
create_database()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/compare', methods=['POST'])
def compare():
    if 'video' not in request.files:
        flash("⚠️ No file part in the request.")
        return redirect(url_for('index'))

    video_file = request.files['video']
    if video_file.filename == '':
        flash("⚠️ No file selected.")
        return redirect(url_for('index'))

    # ✅ Save uploaded video
    save_path = os.path.join(app.config['UPLOAD_FOLDER'], video_file.filename)
    video_file.save(save_path)

    # ✅ Run comparison
    print(f"[INFO] Comparing: {save_path}")
    result_list = compare_with_database(save_path)

    if result_list:
        for match in result_list:
            flash(f"✅ Match found in: {match}")