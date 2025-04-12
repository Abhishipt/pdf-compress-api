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

# Auto-delete after 10 minutes
def delete_file_later(path, delay=600):
    def remove():
        time.sleep(delay)
        if os.path.exists(path):
            os.remove(path)
    threading.Thread(target=remove).start()

@app.route('/')
def home():
    return jsonify({'status': 'PDF Compressor with Levels API is alive 💡'}), 200

@app.route('/compress', methods=['POST'])
def compress():
    file = request.files.get('file')
    compression_type = request.form.get('level', 'medium').lower()

    if not file:
        return 'No file uploaded', 400

    filename = secure_filename(file.filename)
    file_id = str(uuid.uuid4())
    input_path = os.path.join(UPLOAD_FOLDER, f"{file_id}_{filename}")
    output_path = os.path.join(UPLOAD_FOLDER, f"compressed_{file_id}.pdf")
    file.save(input_path)

    # Set DPI based on level
    if compression_type == "high":
        dpi = 72
    elif compression_type == "medium":
        dpi = 100
    else:  # low
        dpi = 150

    try:
        subprocess.run([
            'gs',
            '-sDEVICE=pdfwrite',
            '-dCompatibilityLevel=1.4',
            '-dPDFSETTINGS=/default',
            '-dColorImageDownsampleType=/Bicubic',
            '-dGrayImageDownsampleType=/Bicubic',
            '-dMonoImageDownsampleType=/Subsample',
            '-dDownsampleColorImages=true',
            '-dDownsampleGrayImages=true',
            '-dDownsampleMonoImages=true',
            f'-dColorImageResolution={dpi}',
            f'-dGrayImageResolution={dpi}',
            f'-dMonoImageResolution={dpi}',
            '-dAutoRotatePages=/None',
            '-dDetectDuplicateImages=true',
            '-dCompressFonts=true',
            '-dSubsetFonts=true',
            '-dEmbedAllFonts=true',
            '-dNOPAUSE',
            '-dBATCH',
            '-dQUIET',
            f'-sOutputFile={output_path}',
            input_path
        ], check=True)
    except subprocess.CalledProcessError:
        print("❌ Ghostscript failed.")
        return 'Compression failed: Ghostscript error', 500

    if not os.path.exists(output_path):
        return 'Compression failed: Output file missing', 500

    original_size = os.path.getsize(input_path)
    compressed_size = os.path.getsize(output_path)

    delete_file_later(input_path)
    delete_file_later(output_path)

    # Return original if compressed size not smaller
    if compressed_size > original_size * 0.98:
        print("⚠️ Compression ineffective, returning original.")
        return send_file(input_path, as_attachment=True, download_name='compressed.pdf', mimetype='application/pdf')

    return send_file(output_path, as_attachment=True, download_name='compressed.pdf', mimetype='application/pdf')

if __name__ == '__main__':
    app.run(debug=False)
