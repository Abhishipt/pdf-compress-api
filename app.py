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
COMPRESSED_FOLDER = "compressed"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(COMPRESSED_FOLDER, exist_ok=True)

DELETE_AFTER_SECONDS = 600  # 10 minutes


def auto_delete_file(file_path, delay=DELETE_AFTER_SECONDS):
    def delete():
        time.sleep(delay)
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception as e:
            print(f"Auto delete failed: {e}")
    threading.Thread(target=delete).start()


def get_pdfsetting_from_level(level):
    if level <= 25:
        return "/prepress"
    elif level <= 50:
        return "/printer"
    elif level <= 75:
        return "/ebook"
    else:
        return "/screen"


@app.route("/compress", methods=["POST"])
def compress_pdf():
    try:
        file = request.files["file"]
        compression_level = int(request.form.get("compression", 75))

        filename = secure_filename(file.filename)
        input_pdf_path = os.path.join(UPLOAD_FOLDER, filename)
        output_pdf_path = os.path.join(COMPRESSED_FOLDER, f"compressed_{filename}")
        file.save(input_pdf_path)

        pdf_setting = get_pdfsetting_from_level(compression_level)

        gs_command = [
            "gs",
            "-sDEVICE=pdfwrite",
            "-dCompatibilityLevel=1.4",
            f"-dPDFSETTINGS={pdf_setting}",
            "-dNOPAUSE",
            "-dQUIET",
            "-dBATCH",
            f"-sOutputFile={output_pdf_path}",
            input_pdf_path
        ]

        subprocess.run(gs_command, check=True)

        auto_delete_file(input_pdf_path)
        auto_delete_file(output_pdf_path)

        return send_file(output_pdf_path, as_attachment=True)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/ping", methods=["GET"])
def ping():
    return "pong", 200


if __name__ == "__main__":
    app.run(debug=True)
