from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
import os
import uuid
import subprocess
import threading
import time
from werkzeug.utils import secure_filename

app = Flask(__name__)
CORS(app)

UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Auto-delete files after 10 minutes
def schedule_deletion(filepaths, delay=600):
    def delete_files():
        time.sleep(delay)
        for path in filepaths:
            if os.path.exists(path):
                os.remove(path)
    threading.Thread(target=delete_files).start()

@app.route('/')
def home():
    return "PDF Compression API is running."

@app.route('/compress', methods=['POST'])
def compress_pdf():
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400

    file = request.files['file']
    level = request.form.get('level', 'medium')
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    try:
        original_filename = secure_filename(file.filename)
        input_path = os.path.join(UPLOAD_FOLDER, f"{uuid.uuid4()}_{original_filename}")
        output_path = input_path.replace('.pdf', '_compressed.pdf')

        file.save(input_path)

        quality_settings = {
            'low': '/screen',
            'medium': '/ebook',
            'high': '/printer'
        }

        compression_setting = quality_settings.get(level, '/ebook')

        command = [
            'gs',
            '-sDEVICE=pdfwrite',
            '-dCompatibilityLevel=1.4',
            f'-dPDFSETTINGS={compression_setting}',
            '-dNOPAUSE',
            '-dBATCH',
            '-dQUIET',
            f'-sOutputFile={output_path}',
            input_path
        ]

        subprocess.run(command, check=True)
        schedule_deletion([input_path, output_path])

        return send_file(output_path, as_attachment=True, download_name='compressed.pdf')

    except Exception as e:
        return jsonify({'error': str(e)}), 500
