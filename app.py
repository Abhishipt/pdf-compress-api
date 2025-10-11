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
def delete_file_later(path, delay=180):
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
        "medium": {"dpi": 95, "pdfset": "/ebook"},
        "low": {"dpi": 135, "pdfset": "/printer"}
    }
    level = settings.get(compression_type, settings["medium"])

    try:
        subprocess.run([
    'gs',
    '-sDEVICE=pdfwrite',
    '-dCompatibilityLevel=1.4',

    # ✅ Turn off automatic presets to control all settings manually
    '-dNOPAUSE',
    '-dBATCH',
    '-dQUIET',

    # ✅ Downsampling and re-encoding (stronger compression)
    '-dDownsampleColorImages=true',
    '-dDownsampleGrayImages=true',
    '-dDownsampleMonoImages=true',
    '-dEncodeColorImages=true',
    '-dEncodeGrayImages=true',
    '-dEncodeMonoImages=true',

    # ✅ Use "Average" algorithm for smaller and smoother images
    '-dColorImageDownsampleType=/Average',
    '-dGrayImageDownsampleType=/Average',
    '-dMonoImageDownsampleType=/Subsample',

    # ✅ Set consistent output resolution (you can tweak this)
    f'-dColorImageResolution={level["dpi"]}',
    f'-dGrayImageResolution={level["dpi"]}',
    f'-dMonoImageResolution={level["dpi"]}',

    # ✅ Remove metadata, keep fonts compressed
    '-dCompressFonts=true',
    '-dSubsetFonts=true',
    '-dEmbedAllFonts=true',
    '-dDetectDuplicateImages=true',

    # ✅ Force color model for uniform rendering
    '-dColorConversionStrategy=/sRGB',
    '-dProcessColorModel=/DeviceRGB',
    '-sColorConversionStrategy=RGB',
    '-dAutoRotatePages=/None',

    # ✅ Output file
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
    print(f"⚡ Fast compression started for: {file.filename}")

    try:
        pdf = fitz.open(input_path)
        # Fast compression using garbage collection and deflate streams
        pdf.save(output_path, deflate=True, garbage=4, clean=True, incremental=False)
        pdf.close()
    except Exception as e:
        print("❌ PyMuPDF compression failed:", e)
        return jsonify({"error": "Fast compression failed"}), 500

    if not os.path.exists(output_path):
        return jsonify({"error": "Output file missing"}), 500

    original_size = os.path.getsize(input_path)
    compressed_size = os.path.getsize(output_path)
    print(f"📊 Fast compression: {original_size/1024:.1f} KB → {compressed_size/1024:.1f} KB")

    delete_file_later(input_path)
    delete_file_later(output_path)

    # Return smaller file (or original if not effective)
    if compressed_size > original_size * 0.98:
        print("⚠️ Fast compression ineffective, returning original.")
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
#  KEEP-ALIVE + HOME ENDPOINTS
# ==========================================================
@app.route('/', methods=['GET'])
def home():
    return jsonify({
        "status": "OK",
        "message": "PDF Compressor API (Ghostscript + PyMuPDF)",
        "routes": ["/compress", "/compress_fast"]
    }), 200


@app.route('/ping', methods=['GET'])
def ping():
    return jsonify({"alive": True}), 200


if __name__ == '__main__':
    app.run(debug=False, host="0.0.0.0", port=5000)
    
