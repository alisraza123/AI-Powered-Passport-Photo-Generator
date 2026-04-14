import cv2
import numpy as np
import io
import os
import tempfile
import base64
from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
from rembg import remove, new_session
from fpdf import FPDF

app = Flask(__name__)
CORS(app)

session = new_session("isnet-general-use")
BLUE_BG_BGR = (200, 119, 0)
PASSPORT_PX_W, PASSPORT_PX_H = 413, 531
TOP_SPACING_PX = 35


def apply_luminance_contrast(img, luminance, contrast):

    f = float(luminance)
    c = float(contrast)
    img = cv2.convertScaleAbs(img, alpha=f, beta=c)
    return img


def retouch_logic(img, d, sigma):
    try:
        original_f = img.astype(np.float32)
        smooth_f = cv2.bilateralFilter(
            img, d=int(d), sigmaColor=float(sigma), sigmaSpace=100
        ).astype(np.float32)
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        skin_mask = cv2.inRange(
            hsv, np.array([0, 10, 60], np.uint8), np.array([25, 255, 255], np.uint8)
        )
        skin_mask = cv2.GaussianBlur(skin_mask, (55, 55), 0).astype(np.float32) / 255.0
        skin_3ch = cv2.merge([skin_mask] * 3)
        result_f = smooth_f * skin_3ch + original_f * (1.0 - skin_3ch)
        return cv2.convertScaleAbs(
            np.clip(result_f, 0, 255).astype(np.uint8), alpha=1.03, beta=2
        )
    except:
        return img


def compose_passport(person_rgba):
    alpha_ch = person_rgba[:, :, 3]
    mask = (alpha_ch > 10).astype(np.uint8)
    coords = cv2.findNonZero(mask)
    bx, by, bw, bh = (
        cv2.boundingRect(coords)
        if coords is not None
        else (0, 0, person_rgba.shape[1], person_rgba.shape[0])
    )

    person_crop = person_rgba[by : by + bh, bx : bx + bw]
    scale = max(PASSPORT_PX_W / bw, (PASSPORT_PX_H - TOP_SPACING_PX) / bh)
    final_w, final_h = int(bw * scale), int(bh * scale)
    person_res = cv2.resize(
        person_crop, (final_w, final_h), interpolation=cv2.INTER_LANCZOS4
    )

    canvas = np.full((PASSPORT_PX_H, PASSPORT_PX_W, 3), BLUE_BG_BGR, dtype=np.float32)
    x_off, y_off = (PASSPORT_PX_W - final_w) // 2, TOP_SPACING_PX

    fg_rgb = person_res[:, :, :3].astype(np.float32)
    alpha_f = cv2.GaussianBlur(
        person_res[:, :, 3].astype(np.float32) / 255.0, (3, 3), 0
    )
    alpha_3 = cv2.merge([alpha_f] * 3)

    rx, ry = max(0, -x_off), 0
    cx, cy = max(0, x_off), y_off
    dw, dh = min(PASSPORT_PX_W - cx, final_w - rx), min(
        PASSPORT_PX_H - cy, final_h - ry
    )

    roi = canvas[cy : cy + dh, cx : cx + dw]
    canvas[cy : cy + dh, cx : cx + dw] = fg_rgb[ry : ry + dh, rx : rx + dw] * alpha_3[
        ry : ry + dh, rx : rx + dw
    ] + roi * (1.0 - alpha_3[ry : ry + dh, rx : rx + dw])
    return np.clip(canvas, 0, 255).astype(np.uint8)

@app.route("/")
def index():
    return send_file("./web-app/index.html")
@app.route("/preview-passport", methods=["POST"])
def preview():
    try:
        file = request.files.get("image")
        d, sigma = int(request.form.get("d", 20)), int(request.form.get("sigma", 30))
        if not file:
            return jsonify({"error": "No image"}), 400

        img = cv2.imdecode(np.frombuffer(file.read(), np.uint8), cv2.IMREAD_COLOR)
        retouched = retouch_logic(img, d, sigma)
        no_bg = remove(
            retouched,
            session=session,
            alpha_matting=True,
            alpha_matting_foreground_threshold=240,
            alpha_matting_background_threshold=70,
            alpha_matting_erode_size=10,
        )
        final_img = compose_passport(no_bg)

        temp_path = os.path.join(tempfile.gettempdir(), "last_preview.jpg")
        cv2.imwrite(temp_path, final_img)

        _, buf1 = cv2.imencode(".jpg", final_img)
        return jsonify(
            {
                "processed": base64.b64encode(buf1).decode("utf-8"),
                "temp_path": temp_path,
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/generate-pdf", methods=["POST"])
def generate_pdf():
    data = request.json
    temp_path = data.get("temp_path")
    count = int(data.get("count", 8))
    lum = data.get("luminance", 1.0)
    con = data.get("contrast", 0)

    img = cv2.imread(temp_path)
    filtered_img = apply_luminance_contrast(img, lum, con)

    filtered_path = temp_path.replace(".jpg", "_filtered.jpg")
    cv2.imwrite(filtered_path, filtered_img)

    pdf = FPDF(unit="mm", format="A4")
    pdf.add_page()
    for i in range(count):
        col, row = i % 5, i // 5
        pdf.image(filtered_path, x=10 + col * 38, y=20 + row * 48, w=35, h=45)

    return send_file(
        io.BytesIO(pdf.output(dest="S").encode("latin1")), mimetype="application/pdf"
    )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000)
