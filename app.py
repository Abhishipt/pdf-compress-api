# app.py — Optimized & Stable Hybrid PDF Compressor
from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename
import os, subprocess, uuid, threading, time, io
import fitz  # PyMuPDF
import pikepdf
from PIL import Image

app = Flask(__name__)
CORS(app)

UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# =====================================================
# Auto delete after 180 seconds
# =====================================================
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

# =====================================================
# Quick PDF analysis (pages & images)
# =====================================================
def analyze_pdf(path):
    try:
        doc = fitz.open(path)
        pages = len(doc)
        images = sum(len(p.get_images(full=True)) for p in doc)
        doc.close()
        return pages, images
    except Exception:
        return 0, 0

# =====================================================
# Ghostscript compression (fast + reliable)
# =====================================================
def run_ghostscript(input_path, output_path, dpi=72, jpegq=40, timeout=180, preset="/screen"):
    cmd = [
        "gs", "-sDEVICE=pdfwrite", "-dCompatibilityLevel=1.4",
        f"-dPDFSETTINGS={preset}",
        "-dNOPAUSE", "-dBATCH", "-dQUIET",
        "-dDetectDuplicateImages=true",
        "-dCompressFonts=true", "-dSubsetFonts=true",
        "-dEmbedAllFonts=true",
        "-dDownsampleColorImages=true", "-dDownsampleGrayImages=true", "-dDownsampleMonoImages=true",
        "-dColorImageDownsampleType=/Average", "-dGrayImageDownsampleType=/Average", "-dMonoImageDownsampleType=/Subsample",
        f"-dColorImageResolution={dpi}", f"-dGrayImageResolution={dpi}", f"-dMonoImageResolution={dpi}",
        f"-dJPEGQ={jpegq}",
        "-dAutoRotatePages=/None", "-dColorConversionStrategy=/sRGB",
        f"-sOutputFile={output_path}", input_path
    ]
    try:
        subprocess.run(cmd, check=True, timeout=timeout,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        print("✅ Ghostscript completed successfully")
        return True
    except subprocess.TimeoutExpired:
        print("⚠️ Ghostscript timed out")
        return False
    except subprocess.CalledProcessError as e:
        print("❌ Ghostscript error:", e)
        return False

# =====================================================
# PikePDF lightweight optimization
# =====================================================
def compress_with_pikepdf(inp, outp):
    try:
        with pikepdf.open(inp) as pdf:
            pdf.save(outp)
        print("⚡ PikePDF completed")
        return True
    except Exception as e:
        print("❌ PikePDF failed:", e)
        return False

# =====================================================
# PyMuPDF image recompression (slow, last resort)
# =====================================================
def compress_with_pymupdf(inp, outp, quality=45):
    try:
        doc = fitz.open(inp)
        for p in doc:
            for img in p.get_images(full=True):
                xref = img[0]
                try:
                    pix = fitz.Pixmap(doc, xref)
                    if pix.n > 4:
                        pix = fitz.Pixmap(fitz.csRGB, pix)
                    data = pix.tobytes("png")
                    im = Image.open(io.BytesIO(data)).convert("RGB")
                    buf = io.BytesIO()
                    im.save(buf, "JPEG", quality=quality, optimize=True)
                    doc.update_image(xref, buf.getvalue())
                except Exception as ie:
                    print(f"⚠️ Skip image {xref}: {ie}")
        doc.save(outp, garbage=4, deflate=True, clean=True)
        doc.close()
        print("✅ PyMuPDF recompression completed")
        return True
    except Exception as e:
        print("❌ PyMuPDF failed:", e)
        return False

# =====================================================
# /compress route (main)
# =====================================================
@app.route("/compress", methods=["POST"])
def compress():
    file = request.files.get("file")
    level = request.form.get("level", "medium").lower()
    if not file:
        return jsonify({"error": "No file uploaded"}), 400

    name = os.path.splitext(secure_filename(file.filename))[0]
    uid = uuid.uuid4().hex
    inp = os.path.join(UPLOAD_FOLDER, f"{uid}_{name}.pdf")
    outp = os.path.join(UPLOAD_FOLDER, f"{name}_tools_subidha.pdf")
    file.save(inp)

    size_mb = os.path.getsize(inp) / 1024 / 1024
    pages, imgs = analyze_pdf(inp)
    print(f"📥 Uploaded {file.filename} — {size_mb:.2f} MB | {pages} pages | {imgs} images")

    # Profiles: dpi, JPEG quality
    profiles = {"high": (60, 35), "medium": (72, 45), "low": (95, 60)}
    dpi, jq = profiles.get(level, (72, 45))

    ok = False
    method = "none"

    # =====================================================
    # Strategy logic
    # =====================================================
    try:
        if size_mb <= 1.2:
            # Small PDFs — quick Ghostscript
            print("🧩 Strategy: Ghostscript fast path")
            ok = run_ghostscript(inp, outp, dpi=dpi, jpegq=jq, timeout=120, preset="/ebook")
            method = "ghostscript"

        elif size_mb <= 2.5:
            # Medium PDFs — aggressive Ghostscript
            print("⚡ Strategy: Ghostscript aggressive")
            ok = run_ghostscript(inp, outp, dpi=60, jpegq=40, timeout=180, preset="/screen")
            method = "ghostscript-aggressive"

        else:
            # Large PDFs — PikePDF first, Ghostscript fallback
            print("🚀 Strategy: PikePDF first, fallback to Ghostscript if no gain")
            ok = compress_with_pikepdf(inp, outp)
            if ok:
                before = os.path.getsize(inp)
                after = os.path.getsize(outp)
                if after >= before * 0.98:  # less than 2% gain
                    print("⚠️ PikePDF gave little gain — trying Ghostscript")
                    ok = run_ghostscript(inp, outp, dpi=50, jpegq=35, timeout=200, preset="/screen")
                    method = "pikepdf+ghostscript"
                else:
                    method = "pikepdf"
            else:
                print("⚠️ PikePDF failed — using Ghostscript directly")
                ok = run_ghostscript(inp, outp, dpi=50, jpegq=35, timeout=200, preset="/screen")
                method = "ghostscript-large"

    except Exception as e:
        print("❌ Compression pipeline error:", e)
        ok = False

    # =====================================================
    # Evaluate and return result
    # =====================================================
    if not ok or not os.path.exists(outp):
        print("❌ Compression failed, sending original file")
        delete_file_later(inp)
        return send_file(inp, as_attachment=True,
                         download_name=f"{name}_tools_subidha.pdf",
                         mimetype="application/pdf")

    orig = os.path.getsize(inp)
    comp = os.path.getsize(outp)
    saved = 100 - (comp / orig * 100)
    print(f"📊 {method}: {orig/1024:.1f} KB → {comp/1024:.1f} KB ({saved:.1f}% smaller)")

    # If compression is ineffective, return original file instead
    if comp >= orig * 0.98:  # less than 2% saved
        print("⚠️ Compression ineffective — returning original")
        try:
            os.remove(outp)
        except Exception:
            pass
        delete_file_later(inp)
        return send_file(inp, as_attachment=True,
                         download_name=f"{name}_tools_subidha.pdf",
                         mimetype="application/pdf")

    delete_file_later(inp)
    delete_file_later(outp)
    return send_file(outp, as_attachment=True,
                     download_name=f"{name}_tools_subidha.pdf",
                     mimetype="application/pdf")

# =====================================================
# /compress_fast — PyMuPDF only
# =====================================================
@app.route("/compress_fast", methods=["POST"])
def compress_fast():
    f = request.files.get("file")
    if not f:
        return jsonify({"error": "No file uploaded"}), 400
    name = os.path.splitext(secure_filename(f.filename))[0]
    inp = os.path.join(UPLOAD_FOLDER, f"{uuid.uuid4()}_{name}.pdf")
    outp = os.path.join(UPLOAD_FOLDER, f"{name}_tools_subidha.pdf")
    f.save(inp)
    ok = compress_with_pymupdf(inp, outp, quality=50)
    delete_file_later(inp)
    delete_file_later(outp)
    if not ok:
        return jsonify({"error": "compress_fast failed"}), 500
    return send_file(outp, as_attachment=True,
                     download_name=f"{name}_tools_subidha.pdf",
                     mimetype="application/pdf")

# =====================================================
# Health check
# =====================================================
@app.route("/")
def home():
    return jsonify({
        "status": "OK",
        "message": "PDF Compressor API (Optimized Hybrid Version)",
        "routes": ["/compress", "/compress_fast"]
    })

@app.route("/ping")
def ping():
    return jsonify({"alive": True})

if __name__ == "__main__":
    print("🚀 Starting Optimized PDF Compressor...")
    app.run(host="0.0.0.0", port=5000, debug=False)
