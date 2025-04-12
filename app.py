from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename
import os
import subprocess
import uuid
import threading
import time
import fitz  # PyMuPDF

app = Flask(__name__)
CORS(app)

UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# 🔁 Auto-delete any file after 10 minutes
def delete_file_later(path, delay=600):
    def remove():
        time.sleep(delay)
        if os.path.exists(path):
            os.remove(path)
    threading.Thread(target=remove).start()

# ✅ Keep API alive
@app.route('/')
def home():
    return jsonify({'status': 'Smart PDF Compressor API is alive ⚙️'}), 200

# ✅ Detect whether PDF is scanned or text-based
def is_scanned_pdf(pdf_path):
    try:
        doc = fitz.open(pdf_path)
        image_pages = 0
        for page in doc:
            text = page.get_text()
            images = page.get_images(full=True)
            if not text.strip() and images:
                image_pages += 1
        doc.close()
        return image_pages >= len(doc) / 2  # scanned = mostly images
    except Exception as e:
        print("⚠️ Detection error:", e)
        return False  # fallback to text-based

@app.route('/compress', methods=['POST'])
def compress():
    file = request.files.get('file')
    if not file:
        return 'No file uploaded', 400

    filename = secure_filename(file.filename)
    file_id = str(uuid.uuid4())
    input_path = os.path.join(UPLOAD_FOLDER, f"{file_id}_{filename}")
    output_path = os.path.join(UPLOAD_FOLDER, f"compressed_{file_id}.pdf")
    file.save(input_path)

    # 🧠 Smart detection
    scanned = is_scanned_pdf(input_path)
    dpi = 72 if scanned else 100
    print(f"📘 PDF Type Detected: {'Scanned' if scanned else 'Text-based'} — Using DPI {dpi}")

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
        print("❌ Ghostscript command failed.")
        return 'Compression failed: Ghostscript error', 500

    if not os.path.exists(output_path):
        return 'Compression failed: Output file missing', 500

    delete_file_later(input_path)
    delete_file_later(output_path)

    return send_file(output_path, as_attachment=True, download_name='compressed.pdf', mimetype='application/pdf')

if __name__ == '__main__':
    app.run(debug=False)
