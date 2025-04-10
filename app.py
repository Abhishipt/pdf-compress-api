from flask import Flask, request, send_file, jsonify
from werkzeug.utils import secure_filename
import os
import subprocess
import threading
import time
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

UPLOAD_FOLDER = "uploads"
OUTPUT_FOLDER = "compressed"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

def auto_delete_file(path, delay=600):
    def delete():
        time.sleep(delay)
        if os.path.exists(path):
            try:
                os.remove(path)
                print(f"Deleted: {path}")
            except Exception as e:
                print(f"Error deleting {path}: {e}")
    threading.Thread(target=delete).start()

@app.route('/compress', methods=['POST'])
def compress_pdf():
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Empty filename'}), 400

    try:
        level = int(request.form.get("compression", 75))
    except ValueError:
        level = 75

    # Map compression level to image resolution
    resolution = max(50, min(300, int((level / 100) * 300)))

    filename = secure_filename(file.filename)
    input_path = os.path.join(UPLOAD_FOLDER, filename)
    output_path = os.path.join(OUTPUT_FOLDER, f"compressed_{filename}")
    file.save(input_path)

    gs_command = [
        "gs",
        "-sDEVICE=pdfwrite",
        "-dCompatibilityLevel=1.4",
        "-dDownsampleColorImages=true",
        "-dColorImageDownsampleType=/Bicubic",
        f"-dColorImageResolution={resolution}",
        "-dNOPAUSE",
        "-dQUIET",
        "-dBATCH",
        f"-sOutputFile={output_path}",
        input_path
    ]

    try:
        subprocess.run(gs_command, check=True)
    except subprocess.CalledProcessError:
        return jsonify({'error': 'Compression failed'}), 500

    auto_delete_file(input_path, delay=600)
    auto_delete_file(output_path, delay=600)

    return send_file(output_path, as_attachment=True)

@app.route('/ping', methods=['GET'])
def ping():
    return "pong", 200

if __name__ == "__main__":
    app.run(debug=True)
