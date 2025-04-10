from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename
import os
import uuid
import subprocess
import threading

app = Flask(__name__)
CORS(app)

UPLOAD_FOLDER = 'uploads'
OUTPUT_FOLDER = 'compressed'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

def schedule_file_deletion(file_paths, delay=600):
    def delete_files():
        for path in file_paths:
            try:
                if os.path.exists(path):
                    os.remove(path)
                    print(f"🗑️ Deleted: {path}")
            except Exception as e:
                print(f"Error deleting {path}: {e}")
    threading.Timer(delay, delete_files).start()

@app.route('/')
def index():
    return "Compress PDF API is running."

@app.route('/compress', methods=['POST'])
def compress_pdf():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part in the request'}), 400

    file = request.files['file']
    level = request.form.get('level', 'medium')  # low, medium, high

    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    try:
        uid = str(uuid.uuid4())
        input_path = os.path.join(UPLOAD_FOLDER, secure_filename(f"{uid}.pdf"))
        output_path = os.path.join(OUTPUT_FOLDER, secure_filename(f"{uid}_compressed.pdf"))
        file.save(input_path)

        quality = {
            'low': '/screen',
            'medium': '/ebook',
            'high': '/printer'
        }.get(level, '/ebook')

        cmd = [
            'gs',
            '-sDEVICE=pdfwrite',
            '-dCompatibilityLevel=1.4',
            '-dPDFSETTINGS=' + quality,
            '-dNOPAUSE',
            '-dQUIET',
            '-dBATCH',
            f'-sOutputFile={output_path}',
            input_path
        ]

        subprocess.run(cmd, check=True)
        schedule_file_deletion([input_path, output_path], delay=600)

        return send_file(output_path, as_attachment=True, download_name="compressed.pdf")
    except Exception as e:
        return jsonify({'error': str(e)}), 500
