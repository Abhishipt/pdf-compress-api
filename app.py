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
def delete_file_later(path, delay=60):
    def remove():
        time.sleep(delay)
        if os.path.exists(path):
            os.remove(path)
    threading.Thread(target=remove).start()

@app.route('/compress', methods=['POST'])
def compress():
    file = request.files.get('file')
    compression_type = request.form.get('level', 'medium').lower()

    if not file:
        return 'No file uploaded', 400

    # Secure filename
    original_name = os.path.splitext(secure_filename(file.filename))[0]
    file_ext = ".pdf"
    file_id = str(uuid.uuid4())

    input_path = os.path.join(UPLOAD_FOLDER, f"{file_id}_{original_name}{file_ext}")
    output_path = os.path.join(UPLOAD_FOLDER, f"{original_name}_tools_subidha.pdf")

    file.save(input_path)

    # 🔧 Set compression DPI dynamically
    settings = {
        "high": {"dpi": 72, "pdfset": "/screen"},
        "medium": {"dpi": 100, "pdfset": "/ebook"},
        "low": {"dpi": 150, "pdfset": "/printer"}
    }
    level = settings.get(compression_type, settings["medium"])

    try:
        subprocess.run([
            'gs',
            '-sDEVICE=pdfwrite',
            '-dCompatibilityLevel=1.4',
            f'-dPDFSETTINGS={level["pdfset"]}',
            '-dColorImageDownsampleType=/Bicubic',
            '-dGrayImageDownsampleType=/Bicubic',
            '-dMonoImageDownsampleType=/Subsample',
            '-dDownsampleColorImages=true',
            '-dDownsampleGrayImages=true',
            '-dDownsampleMonoImages=true',
            f'-dColorImageResolution={level["dpi"]}',
            f'-dGrayImageResolution={level["dpi"]}',
            f'-dMonoImageResolution={level["dpi"]}',
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
    except subprocess.CalledProcessError as e:
        print("❌ Ghostscript failed:", e)
        return 'Compression failed: Ghostscript error', 500

    if not os.path.exists(output_path):
        return 'Compression failed: Output file missing', 500

    original_size = os.path.getsize(input_path)
    compressed_size = os.path.getsize(output_path)

    # Auto-delete after 10 minutes
    delete_file_later(input_path)
    delete_file_later(output_path)

    # If compression not effective, return original
    if compressed_size > original_size * 0.98:
        print("⚠️ Compression ineffective, returning original file.")
        return send_file(
            input_path,
            as_attachment=True,
            download_name=f"{original_name}_tools_subidha.pdf",
            mimetype='application/pdf'
        )

    return send_file(
        output_path,
        as_attachment=True,
        download_name=f"{original_name}_tools_subidha.pdf",
        mimetype='application/pdf'
    )

if __name__ == '__main__':
    app.run(debug=False)
