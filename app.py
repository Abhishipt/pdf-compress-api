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
import tempfile
import shutil

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
                print(f"⚠️ Failed deleting {path}: {e}")
    threading.Thread(target=remove, daemon=True).start()


# ==========================================================
# PyMuPDF recompression (real re-encoding)
# ==========================================================
def compress_with_pymupdf(input_path, output_path, quality=50):
    try:
        pdf = fitz.open(input_path)
        # Save temp images into tempdir to avoid collisions
        tmpdir = tempfile.mkdtemp(prefix="pmupdf_")
        try:
            for page in pdf:
                images = page.get_images(full=True)
                for img in images:
                    xref = img[0]
                    try:
                        pix = fitz.Pixmap(pdf, xref)
                        if pix.n > 4:
                            pix = fitz.Pixmap(fitz.csRGB, pix)
                        tmp_img_path = os.path.join(tmpdir, f"img_{xref}.jpg")
                        pix.save(tmp_img_path, quality=quality)
                        pdf.update_image(xref, tmp_img_path)
                        pix = None
                        if os.path.exists(tmp_img_path):
                            os.remove(tmp_img_path)
                    except Exception as ie:
                        print(f"⚠️ PyMuPDF image conversion failed for xref {xref}: {ie}")
            pdf.save(output_path, garbage=4, deflate=True, clean=True)
        finally:
            pdf.close()
            shutil.rmtree(tmpdir, ignore_errors=True)
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
        with pikepdf.open(input_path) as pdf:
            pdf.save(output_path, optimize_streams=True, recompress_flate=True)
        print("⚡ PikePDF compression completed.")
        return True
    except Exception as e:
        print(f"❌ PikePDF failed: {e}")
        return False


# ==========================================================
# Helper: run Ghostscript with timeout and fallback logic
# ==========================================================
def run_ghostscript(input_path, output_path, dpi=95, jpeg_quality=55, timeout_sec=240):
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
        '-dDownsampleColorImages=true',
        '-dDownsampleGrayImages=true',
        '-dDownsampleMonoImages=true',
        '-dColorImageDownsampleType=/Average',
        '-dGrayImageDownsampleType=/Average',
        '-dMonoImageDownsampleType=/Subsample',
        f'-dColorImageResolution={dpi}',
        f'-dGrayImageResolution={dpi}',
        f'-dMonoImageResolution={dpi}',
        f'-dJPEGQ={jpeg_quality}',
        '-dAutoRotatePages=/None',
        '-dColorConversionStrategy=/sRGB',
        '-dProcessColorModel=/DeviceRGB',
        '-dNumRenderingThreads=2',
        f'-sOutputFile={output_path}',
        input_path
    ]

    try:
        subprocess.run(gs_cmd, check=True, timeout=timeout_sec)
        print("✅ Ghostscript finished without error.")
        return True, None
    except subprocess.TimeoutExpired:
        msg = "Ghostscript timed out"
        print("⚠️", msg)
        return False, msg
    except subprocess.CalledProcessError as e:
        msg = f"Ghostscript error: {e}"
        print("❌", msg)
        return False, msg
    except Exception as e:
        msg = f"Ghostscript unexpected error: {e}"
        print("❌", msg)
        return False, msg


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

    file_size_bytes = os.path.getsize(input_path)
    file_size_mb = file_size_bytes / 1024 / 1024
    print(f"📥 Uploaded: {file.filename} ({file_size_mb:.2f} MB)")

    # Compression settings
    settings = {
        "high": {"dpi": 72, "quality": 40},
        "medium": {"dpi": 95, "quality": 55},
        "low": {"dpi": 135, "quality": 70}
    }
    level = settings.get(compression_type, settings["medium"])

    # Hybrid logic: large files -> pikepdf, else ghostscript.
    # Lower threshold to 2 MB to reduce Render CPU/memory issues.
    try:
        if file_size_mb > 2.0:
            print("⚡ Using PikePDF fast compression for large file")
            ok = compress_with_pikepdf(input_path, output_path)
            if not ok:
                print("⚠️ PikePDF failed, falling back to PyMuPDF")
                ok = compress_with_pymupdf(input_path, output_path, quality=level["quality"])
            method_used = "pikepdf" if ok else "pymupdf-fallback"
        else:
            print("🧩 Using Ghostscript for small/medium file")
            ok, err = run_ghostscript(
                input_path,
                output_path,
                dpi=level["dpi"],
                jpeg_quality=level["quality"],
                timeout_sec=240
            )
            method_used = "ghostscript"
            if not ok:
                print("⚠️ Ghostscript failed/timeout, trying PyMuPDF fallback")
                ok = compress_with_pymupdf(input_path, output_path, quality=level["quality"])
                method_used = "pymupdf-fallback"
    except Exception as e:
        print("❌ Unexpected error during compression:", e)
        return jsonify({"error": "Server error during compression"}), 500

    if not os.path.exists(output_path):
        print("❌ Output missing after compression attempts, returning error.")
        delete_file_later(input_path)
        return jsonify({"error": "Output file missing"}), 500

    # Compare sizes and optionally try alternative if no reduction
    original_size = file_size_bytes
    compressed_size = os.path.getsize(output_path)
    saved_pct = 100 - (compressed_size / original_size * 100)
    print(f"📊 Method: {method_used} → {original_size/1024:.1f} KB → {compressed_size/1024:.1f} KB ({saved_pct:.1f}% smaller)")

    # If compressed is not smaller, try alternate algorithm before returning original
    if compressed_size >= original_size:
        print("⚠️ Compression ineffective, trying alternative method (PyMuPDF)")
        alt_ok = compress_with_pymupdf(input_path, output_path, quality=50)
        if alt_ok:
            compressed_size = os.path.getsize(output_path)
            saved_pct = 100 - (compressed_size / original_size * 100)
            print(f"📊 After alt: {original_size/1024:.1f} KB → {compressed_size/1024:.1f} KB ({saved_pct:.1f}% smaller)")
        else:
            print("⚠️ Alternative also ineffective, will return original file.")

    # Ensure cleanup scheduled
    delete_file_later(input_path)
    delete_file_later(output_path)

    # If alt failed and compressed is >= original, return original
    if compressed_size >= original_size:
        print("🔁 Returning original because compression didn't help.")
        return send_file(
            input_path,
            as_attachment=True,
            download_name=f"{original_name}_tools_subidha.pdf",
            mimetype='application/pdf'
        )

    # Successful compressed output
    # (You can also return JSON metadata if you want; for now keep same behavior)
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
    print("🚀 Starting PDF Compressor API (Hybrid Mode)...")
    app.run(debug=False, host="0.0.0.0", port=5000)
