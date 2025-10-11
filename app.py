from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename
import os
import subprocess
import uuid
import threading
import time
import fitz  # PyMuPDF
import pikepdf  # for fast compression

app = Flask(__name__)
CORS(app)

UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ==========================================================
# Auto delete after 180 seconds
# ==========================================================
def delete_file_later(path, delay=180):
    def remove():
        time.sleep(delay)
        if os.path.exists(path):
            try:
                os.remove(path)
                print(f"🗑️ Deleted: {path}")
            except Exception as e:
                print(f"⚠️ Delete failed: {e}")
    threading.Thread(target=remove, daemon=True).start()


# ==========================================================
# PyMuPDF recompression (real re-encoding)
# ==========================================================
def compress_with_pymupdf(input_path, output_path, quality=50):
    try:
        pdf = fitz.open(input_path)
        for page in pdf:
            images = page.get_images(full=True)
            for img_index, img in enumerate(images):
                xref = img[0]
                pix = fitz.Pixmap(pdf, xref)
                if pix.n > 4:
                    pix = fitz.Pixmap(fitz.csRGB, pix)
                pix.save(f"temp_img_{xref}.jpg", quality=quality)
                pdf.update_image(xref, f"temp_img_{xref}.jpg")
                os.remove(f"temp_img_{xref}.jpg")
        pdf.save(output_path, garbage=4, deflate=True, clean=True)
        pdf.close()
        print("✅ PyMuPDF recompression completed.")
        return True
    except Exception as e:
        print(f"❌ PyMuPDF failed: {e}")
        return False


# ==========================================================
# PikePDF - Lightweight Fast Compression
# ==========================================================
def compress_with_pikepdf(input_path, output_path):
    try:
        pdf = pikepdf.open(input_path)
        pdf.save(output_path, optimize_streams=True, recompress_flate=True)
        pdf.close()
        print("⚡ PikePDF compression completed.")
        return True
    except Exception as e:
        print(f"❌ PikePDF failed: {e}")
        return False


# ==========================================================
# Hybrid Compression Route (Ghostscript + PikePDF)
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

    file_size = os.path.getsize(input_path) / 1024 / 1024
    print(f"📥 Uploaded: {file.filename} ({file_size:.2f} MB)")

    # Compression settings
    settings = {
        "high": {"dpi": 72, "quality": 40},
        "medium": {"dpi": 95, "quality": 55},
        "low": {"dpi": 135, "quality": 70}
    }
    level = settings.get(compression_type, settings["medium"])

    # ==========================================================
    # Hybrid logic: big files → PikePDF, small → Ghostscript
    # ==========================================================
    if file_size > 4:
        print("⚡ Using PikePDF fast compression for large file")
        success = compress_with_pikepdf(input_path, output_path)
        if not success:
            print("⚠️ PikePDF failed, falling back to PyMuPDF")
            compress_with_pymupdf(input_path, output_path, quality=50)
    else:
        print("🧩 Using Ghostscript for small/medium file")
        gs_cmd = [
            'gs',
            '-sDEVICE=pdfwrite',
            '-dCompatibilityLevel=1.4',
            '-dPDFSETTINGS=/default',
            '-dNOPAUSE',
            '-dQUIET',
            '-dBATCH',
            '-dDetectDuplicateImages=true',
            '-dCompressFonts=true',
            '-dSubsetFonts=true',
            '-dEmbedAllFonts=true',
            '-dColorImageDownsampleType=/Bicubic',
            '-dGrayImageDownsampleType=/Bicubic',
            '-dMonoImageDownsampleType=/Subsample',
            '-dDownsampleColorImages=true',
            '-dDownsampleGrayImages=true',
            '-dDownsampleMonoImages=true',
            f'-dColorImageResolution={level["dpi"]}',
            f'-dGrayImageResolution={level["dpi"]}',
            f'-dMonoImageResolution={level["dpi"]}',
            f'-dJPEGQ={level["quality"]}',
            '-dAutoRotatePages=/None',
            '-dColorConversionStrategy=/sRGB',
            f'-sOutputFile={output_path}',
            input_path
        ]

        try:
            subprocess.run(gs_cmd, check=True)
        except subprocess.CalledProcessError as e:
            print("❌ Ghostscript failed:", e)
            compress_with_pymupdf(input_path, output_path, quality=50)

    if not os.path.exists(output_path):
        return jsonify({"error": "Output file missing"}), 500

    # Compare sizes
    original_size = os.path.getsize(input_path)
    compressed_size = os.path.getsize(output_path)
    saved = 100 - (compressed_size / original_size * 100)
    print(f"📊 Original: {original_size/1024:.1f} KB → Compressed: {compressed_size/1024:.1f} KB ({saved:.1f}% smaller)")

    delete_file_later(input_path)
    delete_file_later(output_path)

    return send_file(
        output_path,
        as_attachment=True,
        download_name=f"{original_name}_tools_subidha.pdf",
        mimetype='application/pdf'
    )


# ==========================================================
# Fast Route — PyMuPDF only
# ==========================================================
@app.route('/compress_fast', methods=['POST'])
def compress_fast():
    file = request.files.get('file')
    if not file:
        return jsonify({"error": "No file uploaded"}), 400

    original_name = os.path.splitext(secure_filename(file.filename))[0]
    input_path = os.path.join(UPLOAD_FOLDER, f"{uuid.uuid4()}_{original_name}.pdf")
    output_path = os.path.join(UPLOAD_FOLDER, f"{original_name}_tools_subidha.pdf")

    file.save(input_path)
    compress_with_pymupdf(input_path, output_path, quality=50)

    delete_file_later(input_path)
    delete_file_later(output_path)

    return send_file(
        output_path,
        as_attachment=True,
        download_name=f"{original_name}_tools_subidha.pdf",
        mimetype='application/pdf'
    )


# ==========================================================
# Health Check
# ==========================================================
@app.route('/')
def home():
    return jsonify({
        "status": "OK",
        "message": "PDF Compressor API running (Hybrid Mode)",
        "routes": ["/compress", "/compress_fast"]
    })

@app.route('/ping')
def ping():
    return jsonify({"alive": True})


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=5000)
