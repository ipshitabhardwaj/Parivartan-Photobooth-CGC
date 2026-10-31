import os
import sys

# Ensure local directory is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, request, jsonify, send_from_directory, abort

import ai_painter
import ollama_client
from ai_generator import reimagine_image, prepare_look
import drive_storage
from recipes import THEMES

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Only these files are ever served. The folder also holds credentials.json,
# token.json and service_account.json, which must never be reachable by URL.
STATIC_FILES = {
    "index.html", "app.js", "svgfx.js", "style.css", "favicon.svg",
    "bg-scifi.svg", "bg-anime.svg", "bg-cats.svg", "bg-vintage.svg",   # theme wallpapers
}

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024  # photos are small; refuse anything huge


def _data_url_ok(value, kinds=("image/jpeg", "image/png")):
    return isinstance(value, str) and any(value.startswith(f"data:{kind};base64,") for kind in kinds)


@app.route('/')
def serve_index():
    return send_from_directory(BASE_DIR, 'index.html')


@app.route('/<path:path>')
def serve_static(path):
    if path not in STATIC_FILES:
        abort(404)
    return send_from_directory(BASE_DIR, path)


@app.after_request
def no_stale_files(response):
    """Always re-check the page files, so an updated kiosk never runs an old cached script."""
    if request.path == '/' or request.path in ('/' + name for name in STATIC_FILES):
        response.headers['Cache-Control'] = 'no-cache'
    return response


@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy", "service": "CGC SQUARE Kiosk"})


@app.route('/api/status', methods=['GET'])
def status():
    """Lets the page show whether Ollama is ready. ?refresh=1 forces a re-check."""
    ollama = ollama_client.get_status(force=request.args.get("refresh") == "1")
    return jsonify({
        "server": "ok",
        "ollama": {
            "available": ollama["available"],
            "model": ollama["model"],
            "reason": ollama["reason"],
        },
        "drive": {"connected": drive_storage.DRIVE.folder_id is not None, "pending": drive_storage.DRIVE.pending(), "error": drive_storage.DRIVE.error},
        "ai": {"available": ai_painter.available(), "model": ai_painter.MODEL_ID, "reason": ai_painter.why_not()},
    })


@app.route('/api/prepare', methods=['POST'])
def handle_prepare():
    """Called when the shutter is pressed: starts the Ollama step so it overlaps the countdown."""
    try:
        data = request.get_json(silent=True) or {}
        image_data = data.get('image')
        if not _data_url_ok(image_data):
            return jsonify({"success": False, "error": "No valid image data received"}), 400
        theme = data.get('theme')
        if theme not in THEMES:
            theme = "Sci-Fi"
        return jsonify({"success": True, "id": prepare_look(image_data, theme)})
    except Exception as e:
        print(f"[Prepare Error]: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/reimagine', methods=['POST'])
def handle_reimagine():
    try:
        data = request.get_json(silent=True) or {}
        image_data = data.get('image')
        if not _data_url_ok(image_data):
            return jsonify({"success": False, "error": "No valid image data received"}), 400

        theme = data.get('theme')
        if theme not in THEMES:
            theme = "Sci-Fi"

        prepare_id = data.get('prepareId') if isinstance(data.get('prepareId'), str) else None
        result = reimagine_image(image_data, theme, prepare_id)
        return jsonify({
            "success": True,
            "theme": theme,
            "imageUrl": result["image"],
            "recipe": result["recipe"],
            "cutout": result.get("cutout", False),
            "method": result["method"],
            "model": result["model"],
            "note": result["note"],
        })
    except Exception as e:
        print(f"[Server Error]: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/save', methods=['POST'])
def handle_save():
    """Save the finished picture as the next numbered photo (1.png, 2.png, ...) and queue its Google Drive upload."""
    try:
        data = request.get_json(silent=True) or {}
        png = drive_storage.decode_png_data_url(data.get('image'))
        if png is None:
            return jsonify({"success": False, "error": "No valid PNG image received"}), 400
        number, path = drive_storage.save_photo(png)
        print(f"[Photo] saved #{number} -> {path}")
        return jsonify({"success": True, "number": number})
    except Exception as e:
        print(f"[Save Error]: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/qr.svg', methods=['GET'])
def qr_code():
    """QR code of the Google Drive folder link. 404 until Drive is connected."""
    svg = drive_storage.qr_svg()
    if svg is None:
        abort(404)
    response = app.response_class(svg, mimetype='image/svg+xml')
    response.headers['Cache-Control'] = 'no-store'
    return response


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    # 127.0.0.1 keeps the kiosk private to this computer (and browsers only allow the
    # camera on localhost anyway). Set HOST=0.0.0.0 only if you really need LAN access.
    host = os.environ.get("HOST", "127.0.0.1")
    print("=================================================")
    print(f"CGC SQUARE Kiosk Server running on http://127.0.0.1:{port}")
    print("=================================================")
    drive_storage.DRIVE.start()
    if ai_painter.available():
        print(f"[AI] repainting with {ai_painter.MODEL_ID} for: {', '.join(ai_painter.AI_THEMES)}")
        ai_painter.warm_up_async()
    else:
        print(f"[AI] repainting off ({ai_painter.why_not()}); using the quick filter looks. See README to enable it.")
        ollama_client.warm_up()
    app.run(host=host, port=port, debug=False)
