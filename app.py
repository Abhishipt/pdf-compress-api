from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename
import os
import subprocess
import uuid
import threading
import time
import fitz  # PyMuPDF for fast compression fallback

app = Flask(__name__)
CORS(app)

UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# ==========================================================
# 🔁 Auto delete files after 180 seconds
# ==========================================================
def delete_file_later(path, delay=180):
    def remove():
        time.sleep(delay)
        if os.path.exists(path):
            try:
                os.remove(path)
                print(f"🗑️ Deleted temporary file: {path}")
            except Exception as e:
                print(f"⚠️ Failed to delete file {path}: {e}")
    threading.Thread(target=remove, daemon=True).start()


# ==========================================================
# 🧠 Helper: PyMuPDF fallback compression
# ==========================================================
def compress_with_pymupdf(input_path, output_path):
    try:
        pdf = fitz.open(input_path)
        pdf.save(output_path, deflate=True, garbage=4, clean=True, incremental=False)
        pdf.close()
        print("⚡ PyMuPDF fallback compression completed.")
        return True
    except Exception as e:
        print(f"❌ PyMuPDF compression failed: {e}")
        return False


# ==========================================================
# 🧩 Route 1: Ghostscript-based compression
# ==========================================================
@app.route('/compress', methods=['POST'])
def compress():
    file = request.files.get('file')
    compression_type = request.form.get('level', 'medium').lower()

    if not file:
        return jsonify({"error": "No file uploaded"}), 400

    original_name = os.path.splitext(secure_filename(file.filename))[0]
    file_ext = ".pdf"
    file_id = str(uuid.uuid4())

    input_path = os.path.join(UPLOAD_FOLDER, f"{file_id}_{original_name}{file_ext}")
    output_path = os.path.join(UPLOAD_FOLDER, f"{original_name}_tools_subidha.pdf")

    file.save(input_path)
    print(f"📥 Uploaded: {file.filename}")

    file_size = os.path.getsize(input_path)
    print(f"📦 Input file size: {file_size/1024/1024:.2f} MB")

    # Auto fallback for large PDFs (>5 MB)
    if file_size > 5 * 1024 * 1024:
        print("⚡ Large file detected → using PyMuPDF fallback")
        success = compress_with_pymupdf(input_path, output_path)
        if not success:
            return jsonify({"error": "Fast compression failed"}), 500
        delete_file_later(input_path)
        delete_file_later(output_path)
        return send_file(
            output_path,
            as_attachment=True,
            download_name=f"{original_name}_tools_subidha.pdf",
            mimetype='application/pdf'
        )

    # Compression settings
    settings = {
        "high": {"dpi": 72, "pdfset": "/screen"},
        "medium": {"dpi": 95, "pdfset": "/ebook"},
        "low": {"dpi": 135, "pdfset": "/printer"}
    }
    level = settings.get(compression_type, settings["medium"])

    # 🔧 Updated Ghostscript compression command
    try:
        subprocess.run([
            'gs',
            '-sDEVICE=pdfwrite',
            '-dCompatibilityLevel=1.4',
            '-dNOPAUSE',
            '-dBATCH',
            '-dQUIET',

            # ✅ Improved image compression and encoding
            '-dDownsampleColorImages=true',
            '-dDownsampleGrayImages=true',
            '-dDownsampleMonoImages=true',
            '-dEncodeColorImages=true',
            '-dEncodeGrayImages=true',
            '-dEncodeMonoImages=true',
            '-dColorImageDownsampleType=/Average',
            '-dGrayImageDownsampleType=/Average',
            '-dMonoImageDownsampleType=/Subsample',
            '-dJPEGQ=60',  # quality 0–100 (lower = smaller size)

            # ✅ Resolution settings
            f'-dColorImageResolution={level["dpi"]}',
            f'-dGrayImageResolution={level["dpi"]}',
            f'-dMonoImageResolution={level["dpi"]}',

            # ✅ Font and metadata compression
            '-dCompressFonts=true',
            '-dSubsetFonts=true',
            '-dEmbedAllFonts=true',
            '-dDetectDuplicateImages=true',

            # ✅ Color handling and optimization
            '-dColorConversionStrategy=/sRGB',
            '-dProcessColorModel=/DeviceRGB',
            '-sColorConversionStrategy=RGB',
            '-dAutoRotatePages=/None',

            # ✅ Output
            f'-sOutputFile={output_path}',
            input_path
        ], check=True)
    except subprocess.CalledProcessError as e:
        print("❌ Ghostscript compression failed:", e)
        return jsonify({"error": "Compression failed"}), 500

    # ✅ Verify result
    if not os.path.exists(output_path):
        return jsonify({"error": "Output file missing"}), 500

    original_size = os.path.getsize(input_path)
    compressed_size = os.path.getsize(output_path)
    print(f"📊 Ghostscript compression: {original_size/1024:.1f} KB → {compressed_size/1024:.1f} KB")

    delete_file_later(input_path)
    delete_file_later(output_path)

    # If compression ineffective, return original file
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


# ==========================================================
# 🧩 Route 2: Manual Fast Compression (PyMuPDF only)
# ==========================================================
@app.route('/compress_fast', methods=['POST'])
def compress_fast():
    file = request.files.get('file')
    if not file:
        return jsonify({"error": "No file uploaded"}), 400

    original_name = os.path.splitext(secure_filename(file.filename))[0]
    file_ext = ".pdf"
    file_id = str(uuid.uuid4())

    input_path = os.path.join(UPLOAD_FOLDER, f"{file_id}_{original_name}{file_ext}")
    output_path = os.path.join(UPLOAD_FOLDER, f"{original_name}_tools_subidha.pdf")

    file.save(input_path)
    print(f"⚡ Fast compression triggered for: {file.filename}")

    success = compress_with_pymupdf(input_path, output_path)
    if not success:
        return jsonify({"error": "Fast compression failed"}), 500

    delete_file_later(input_path)
    delete_file_later(output_path)

    return send_file(
        output_path,
        as_attachment=True,
        download_name=f"{original_name}_tools_subidha.pdf",
        mimetype='application/pdf'
    )


# ==========================================================
# 🩺 Keep Alive & Health Routes
# ==========================================================
@app.route('/', methods=['GET'])
def home():
    return jsonify({
        "status": "OK",
        "message": "PDF Compressor API Active",
        "routes": ["/compress", "/compress_fast"]
    }), 200


@app.route('/ping', methods=['GET'])
def ping():
    return jsonify({"alive": True}), 200


if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5000)
