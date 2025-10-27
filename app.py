# app.py — improved hybrid compressor with PDF analysis and safe fallbacks
from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename
import os
import subprocess
import uuid
import threading
import time
import fitz  # PyMuPDF
import pikepdf
import tempfile
import shutil
import io
from PIL import Image

app = Flask(__name__)
CORS(app)

UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# -------------------------
# Auto-delete helper
# -------------------------
def delete_file_later(path, delay=180):
    def remove():
        time.sleep(delay)
        try:
            if os.path.exists(path):
                os.remove(path)
                print(f"🗑️ Deleted: {path}")
        except Exception as e:
            print(f"⚠️ Delete failed for {path}: {e}")
    threading.Thread(target=remove, daemon=True).start()

# -------------------------
# PDF analyzer (pages, images, largest image pixels)
# -------------------------
def analyze_pdf(path, max_images_sample=100):
    try:
        doc = fitz.open(path)
        page_count = len(doc)
        total_images = 0
        largest_pixels = 0
        # iterate pages, count images and track largest image dimension
        for p in doc:
            imgs = p.get_images(full=True)
            total_images += len(imgs)
            # sample a few images to estimate sizes
            for img in imgs[:max_images_sample]:
                xref = img[0]
                try:
                    pix = fitz.Pixmap(doc, xref)
                    w, h = pix.width, pix.height
                    pixels = w * h
                    if pixels > largest_pixels:
                        largest_pixels = pixels
                    pix = None
                except Exception:
                    # ignore problematic images
                    pass
        doc.close()
        return {"pages": page_count, "images": total_images, "largest_img_pixels": largest_pixels}
    except Exception as e:
        print("⚠️ analyze_pdf failed:", e)
        return {"pages": 0, "images": 0, "largest_img_pixels": 0}

# -------------------------
# PyMuPDF based image re-encode (memory conscious)
# -------------------------
def compress_with_pymupdf(input_path, output_path, quality=50):
    """
    Re-encode images inside PDF using PyMuPDF + Pillow.
    This is fairly slow for many images but generally safe.
    """
    try:
        doc = fitz.open(input_path)
        try:
            for page_index in range(len(doc)):
                page = doc[page_index]
                images = page.get_images(full=True)
                for img in images:
                    xref = img[0]
                    try:
                        pix = fitz.Pixmap(doc, xref)
                        # convert to RGB if necessary
                        if pix.n > 4:
                            pix = fitz.Pixmap(fitz.csRGB, pix)
                        png_bytes = pix.tobytes("png")
                        pix = None
                        pil = Image.open(io.BytesIO(png_bytes))
                        if pil.mode != "RGB":
                            pil = pil.convert("RGB")
                        buf = io.BytesIO()
                        pil.save(buf, format="JPEG", quality=int(quality), optimize=True)
                        buf.seek(0)
                        new_bytes = buf.read()
                        buf.close()
                        doc.update_image(xref, new_bytes)
                    except Exception as ie:
                        print(f"⚠️ PyMuPDF image conversion skip xref {xref}: {ie}")
            # save
            doc.save(output_path, garbage=4, deflate=True, clean=True)
            print("✅ PyMuPDF recompression completed.")
            return True
        finally:
            doc.close()
    except Exception as e:
        print("❌ PyMuPDF top-level failed:", e)
        return False

# -------------------------
# PikePDF lightweight pass (compatible)
# -------------------------
def compress_with_pikepdf(input_path, output_path):
    try:
        with pikepdf.open(input_path) as pdf:
            # Basic save is compatible across pikepdf versions
            pdf.save(output_path)
        print("⚡ PikePDF basic save completed.")
        return True
    except Exception as e:
        print("❌ PikePDF failed:", e)
        return False

# -------------------------
# Safe Ghostscript runner
# -------------------------
def run_ghostscript(input_path, output_path, dpi=95, jpeg_quality=55, timeout_sec=240, preset="/default"):
    """
    Runs Ghostscript with controlled settings. Use lower dpi & jpeg_quality for aggressive compression.
    """
    gs_cmd = [
        "gs",
        "-sDEVICE=pdfwrite",
        "-dCompatibilityLevel=1.4",
        f"-dPDFSETTINGS={preset}",
        "-dNOPAUSE",
        "-dBATCH",
        "-dQUIET",
        "-dDetectDuplicateImages=true",
        "-dCompressFonts=true",
        "-dSubsetFonts=true",
        "-dEmbedAllFonts=true",
        "-dDownsampleColorImages=true",
        "-dDownsampleGrayImages=true",
        "-dDownsampleMonoImages=true",
        "-dColorImageDownsampleType=/Average",
        "-dGrayImageDownsampleType=/Average",
        "-dMonoImageDownsampleType=/Subsample",
        f"-dColorImageResolution={int(dpi)}",
        f"-dGrayImageResolution={int(dpi)}",
        f"-dMonoImageResolution={int(dpi)}",
        f"-dJPEGQ={int(jpeg_quality)}",
        "-dAutoRotatePages=/None",
        "-dColorConversionStrategy=/sRGB",
        "-dProcessColorModel=/DeviceRGB",
        f"-sOutputFile={output_path}",
        input_path
    ]
    try:
        proc = subprocess.run(gs_cmd, check=True, timeout=timeout_sec, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        print("✅ Ghostscript finished without error.")
        return True, None
    except subprocess.TimeoutExpired:
        print("⚠️ Ghostscript timed out")
        return False, "timeout"
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode(errors="ignore") if getattr(e, "stderr", None) else str(e)
        print("❌ Ghostscript error:", stderr[:1000])
        return False, stderr
    except Exception as e:
        print("❌ Ghostscript unexpected error:", e)
        return False, str(e)

# -------------------------
# Main hybrid endpoint
# -------------------------
@app.route("/compress", methods=["POST"])
def compress():
    file = request.files.get("file")
    compression_type = request.form.get("level", "medium").lower()
    if not file:
        return jsonify({"error": "No file uploaded"}), 400

    original_filename = secure_filename(file.filename)
    name_only = os.path.splitext(original_filename)[0]
    uid = str(uuid.uuid4())
    input_path = os.path.join(UPLOAD_FOLDER, f"{uid}_{name_only}.pdf")
    output_path = os.path.join(UPLOAD_FOLDER, f"{name_only}_tools_subidha.pdf")
    file.save(input_path)

    file_size_bytes = os.path.getsize(input_path)
    file_size_mb = file_size_bytes / 1024 / 1024
    print(f"📥 Uploaded: {original_filename} ({file_size_mb:.2f} MB)")

    # quick analyze
    info = analyze_pdf(input_path)
    pages = int(info.get("pages", 0))
    images = int(info.get("images", 0))
    largest_img_pixels = int(info.get("largest_img_pixels", 0))
    print(f"🔎 PDF analysis → pages: {pages}, images: {images}, largest_img_px: {largest_img_pixels}")

    # protect very large files: suggest background worker instead of killing web worker
    if file_size_mb > 12.0:
        delete_file_later(input_path)
        return jsonify({"error": "File too large for web processing. Use background processing or try smaller file."}), 413

    # compression profile
    profiles = {
        "high": {"dpi": 72, "quality": 40},
        "medium": {"dpi": 95, "quality": 55},
        "low": {"dpi": 135, "quality": 70}
    }
    prof = profiles.get(compression_type, profiles["medium"])

    method_used = "none"
    ok = False

    # Strategy rules (conservative for Render web worker)
    # If document is image-heavy or > 1.4 MB -> start with PikePDF (low memory)
    image_heavy = (images >= 6) or (largest_img_pixels > (2000 * 2000))  # heuristic
    try:
        if file_size_mb > 1.4 or image_heavy:
            print("⚡ Strategy: pikepdf-first (image-heavy or >1.4MB)")
            ok = compress_with_pikepdf(input_path, output_path)
            method_used = "pikepdf"
            if ok:
                # if pikepdf produced file, check size reduction
                cs = os.path.getsize(output_path)
                if cs >= file_size_bytes:
                    print("⚠️ PikePDF did not reduce size; try Ghostscript (aggressive) if safe")
                    # attempt aggressive Ghostscript only if file small-ish or images moderate
                    if file_size_mb <= 6.0:
                        print("🔁 Trying Ghostscript aggressive fallback")
                        gs_ok, gs_err = run_ghostscript(input_path, output_path,
                                                       dpi=max(50, prof["dpi"]-30),
                                                       jpeg_quality=max(30, prof["quality"]-20),
                                                       timeout_sec=240,
                                                       preset="/screen")
                        if gs_ok:
                            method_used = "pikepdf+ghostscript"
                            ok = True
                    # otherwise try PyMuPDF fallback
                    if not ok:
                        print("🔁 Trying PyMuPDF fallback")
                        ok = compress_with_pymupdf(input_path, output_path, quality=max(30, prof["quality"]-10))
                        method_used = "pikepdf+pymupdf"
            else:
                print("⚠️ PikePDF failed, trying PyMuPDF fallback")
                ok = compress_with_pymupdf(input_path, output_path, quality=prof["quality"])
                method_used = "pymupdf-fallback"
        else:
            # non-image small documents — Ghostscript primary
            print("🧩 Strategy: Ghostscript primary (small document)")
            preset = "/ebook" if file_size_mb > 0.8 else "/screen"
            # for moderate images use slightly lower dpi to speed up
            dpi = prof["dpi"]
            jpegq = prof["quality"]
            # lower dpi for documents with many images to reduce memory/time
            if images > 8:
                dpi = max(60, int(prof["dpi"] * 0.6))
                jpegq = max(30, int(prof["quality"] * 0.6))
            gs_ok, gs_err = run_ghostscript(input_path, output_path,
                                            dpi=dpi,
                                            jpeg_quality=jpegq,
                                            timeout_sec=240,
                                            preset=preset)
            method_used = "ghostscript"
            if not gs_ok:
                print("⚠️ Ghostscript failed/timeout. Attempting PikePDF (light) then PyMuPDF.")
                ok = compress_with_pikepdf(input_path, output_path)
                method_used = "ghostscript-failed->pikepdf"
                if not ok:
                    ok = compress_with_pymupdf(input_path, output_path, quality=prof["quality"])
                    method_used = "ghostscript-failed->pymupdf"
            else:
                ok = True
    except Exception as e:
        print("❌ Unexpected compression pipeline error:", e)
        ok = False
        method_used = "error"

    # Evaluate output existence and size
    if not os.path.exists(output_path):
        print("❌ Output missing after attempts")
        delete_file_later(input_path)
        return jsonify({"error": "Compression failed"}), 500

    original_size = file_size_bytes
    compressed_size = os.path.getsize(output_path)
    saved = 100 - (compressed_size / original_size * 100)
    print(f"📊 Result: method={method_used} → {original_size/1024:.1f}KB -> {compressed_size/1024:.1f}KB ({saved:.1f}% smaller)")

    # if not smaller, try one last PyMuPDF aggressive pass (low quality)
    if compressed_size >= original_size:
        print("⚠️ Compressed not smaller — attempting final PyMuPDF aggressive pass")
        alt_ok = compress_with_pymupdf(input_path, output_path, quality=30)
        if alt_ok:
            compressed_size = os.path.getsize(output_path)
            saved = 100 - (compressed_size / original_size * 100)
            print(f"📊 After alt: {original_size/1024:.1f}KB -> {compressed_size/1024:.1f}KB ({saved:.1f}% smaller)")

    # schedule cleanup
    delete_file_later(input_path)
    delete_file_later(output_path)

    # if still not smaller, return original with message
    if compressed_size >= original_size:
        print("🔁 Returning original (compression ineffective)")
        return send_file(input_path, as_attachment=True,
                         download_name=f"{name_only}_tools_subidha.pdf",
                         mimetype="application/pdf")

    return send_file(output_path, as_attachment=True,
                     download_name=f"{name_only}_tools_subidha.pdf",
                     mimetype="application/pdf")


# -------------------------
# Fast route (PyMuPDF only)
# -------------------------
@app.route("/compress_fast", methods=["POST"])
def compress_fast():
    file = request.files.get("file")
    if not file:
        return jsonify({"error": "No file uploaded"}), 400
    original_filename = secure_filename(file.filename)
    name_only = os.path.splitext(original_filename)[0]
    input_path = os.path.join(UPLOAD_FOLDER, f"{uuid.uuid4()}_{name_only}.pdf")
    output_path = os.path.join(UPLOAD_FOLDER, f"{name_only}_tools_subidha.pdf")
    file.save(input_path)
    ok = compress_with_pymupdf(input_path, output_path, quality=50)
    delete_file_later(input_path)
    delete_file_later(output_path)
    if not ok:
        return jsonify({"error": "compress_fast failed"}), 500
    return send_file(output_path, as_attachment=True,
                     download_name=f"{name_only}_tools_subidha.pdf", mimetype="application/pdf")

# -------------------------
# Health endpoints
# -------------------------
@app.route("/")
def home():
    return jsonify({"status": "OK", "message": "PDF Compressor API", "routes": ["/compress", "/compress_fast"]})

@app.route("/ping")
def ping():
    return jsonify({"alive": True})

if __name__ == "__main__":
    print("🚀 Starting improved PDF compressor...")
    app.run(host="0.0.0.0", port=5000, debug=False)
