from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename
import os
import subprocess
import uuid
import threading
import time

app = Flask(__name__)
CORS(app)

UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Auto-delete file after 10 minutes
def delete_file_later(path, delay=600):
    def remove():
        time.sleep(delay)
        if os.path.exists(path):
            os.remove(path)
    threading.Thread(target=remove).start()

# Keep-alive route for Render/UptimeRobot
@app.route('/')
def home():
    return jsonify({'status': 'PDF Compression API is alive 🔥'}), 200

# Compress using Ghostscript
def compress_pdf_ghostscript(input_path, output_path, quality='screen'):
    try:
        subprocess.run([
            'gs',
            '-sDEVICE=pdfwrite',
            f'-dPDFSETTINGS=/{quality}',
            '-dNOPAUSE',
            '-dBATCH',
            '-dQUIET',
            f'-sOutputFile={output_path}',
            input_path
        ], check=True)
        return True
    except subprocess.CalledProcessError:
        return False

@app.route('/compress', methods=['POST'])
def compress():
    file = request.files.get('file')
    quality_level = int(request.form.get('level', 60))

    if not file:
        return 'No file uploaded', 400

    filename = secure_filename(file.filename)
    file_id = str(uuid.uuid4())
    input_path = os.path.join(UPLOAD_FOLDER, f"{file_id}_{filename}")
    output_path = os.path.join(UPLOAD_FOLDER, f"compressed_{file_id}.pdf")
    file.save(input_path)

    if quality_level >= 80:
        quality = 'ebook'
    elif quality_level >= 50:
        quality = 'screen'
    else:
        quality = 'default'

    success = compress_pdf_ghostscript(input_path, output_path, quality)

    if not success:
        print("❌ Ghostscript command failed.")
        return 'Compression failed: Ghostscript error', 500

    if not os.path.exists(output_path):
        print("❌ Output file not found.")
        return 'Compression failed: Output file missing', 500

    delete_file_later(input_path)
    delete_file_later(output_path)

    return send_file(output_path, as_attachment=True, download_name='compressed.pdf', mimetype='application/pdf')

if __name__ == '__main__':
    app.run(debug=False)
