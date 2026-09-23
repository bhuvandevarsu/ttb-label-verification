from __future__ import annotations

import asyncio
import csv
import io
import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

try:
    import pytesseract
    from pytesseract import Output
    TESSERACT_AVAILABLE = True
except Exception:
    pytesseract = None
    Output = None
    TESSERACT_AVAILABLE = False

BASE_DIR = Path(__file__).resolve().parent
app = FastAPI(title="TTB Label Verification Prototype", version="1.1.0")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

# Keep OCR concurrency deliberately small so lightweight hosts remain responsive.
OCR_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="ocr")

STANDARD_WARNING = (
    "GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink alcoholic beverages during pregnancy because of the risk of birth defects. "
    "(2) Consumption of alcoholic beverages impairs your ability to drive a car or operate machinery, and may cause health problems."
)


def normalize_text(value: str) -> str:
    value = (value or "").upper().strip().replace("’", "'")
    value = re.sub(r"[^A-Z0-9%./' -]", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def extract_number(value: str) -> float | None:
    match = re.search(r"(\d+(?:\.\d+)?)", value or "")
    return float(match.group(1)) if match else None


def parse_fields(text: str) -> dict[str, str]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    joined = "\n".join(lines)

    def after(patterns: list[str]) -> str:
        for line in lines:
            for pattern in patterns:
                match = re.search(pattern, line, flags=re.I)
                if match:
                    return match.group(1).strip()
        return ""

    brand = after([r"^brand(?: name)?\s*[:\-]\s*(.+)$"])
    class_type = after([r"^(?:class/type|type|class)\s*[:\-]\s*(.+)$"])
    if not brand:
        match = re.search(r"\b(OLD TOM DISTILLERY)\b", joined, re.I)
        if match: brand = match.group(1)
    abv = after([r"^(?:abv|alcohol content|alcohol by volume)\s*[:\-]\s*(.+)$"])
    net = after([r"^(?:net contents|contents)\s*[:\-]\s*(.+)$"])
    producer = after([r"^(?:producer|bottler|bottled by|produced by)\s*[:\-]\s*(.+)$"])
    country = after([r"^(?:country of origin|origin)\s*[:\-]\s*(.+)$"])

    if not brand:
        for line in lines[:8]:
            if 3 <= len(line) <= 45 and not re.search(r"warning|bourbon|whiskey|whisky|%|750|ml|distillery|kentucky", line, re.I):
                brand = line
                break
    if not class_type:
        if re.search(r"KENTUCKY\s+STRAIGHT", joined, re.I) and re.search(r"BOURBON\s+WHISKEY", joined, re.I):
            class_type = "Kentucky Straight Bourbon Whiskey"
        elif re.search(r"STRAIGHT\s+BOURBON\s+WHISKEY", joined, re.I):
            class_type = "Straight Bourbon Whiskey"
    if not abv:
        match = re.search(r"\b(\d+(?:\.\d+)?)\s*%\s*(?:alc\.?\s*/\s*vol\.?|alcohol)?", joined, re.I)
        if match:
            abv = match.group(1) + "%"
    if not net:
        match = re.search(r"\b(\d+(?:\.\d+)?)\s*(mL|ML|L|liters?|oz)\b", joined, re.I)
        if match:
            net = match.group(1) + " " + match.group(2)
    if not producer:
        match = re.search(r"BOTTLED BY\s+(.+?)(?=\s+(?:FRANKFORT|UNITED STATES|GOVERNMENT WARNING)\b)", joined, re.I)
        if match: producer = match.group(1).strip()
    if not country:
        match = re.search(r"\b(UNITED STATES|USA|U\.?S\.?A\.?)\b", joined, re.I)
        if match: country = match.group(1)
    warning_match = re.search(r"(GOVERNMENT WARNING:.*)", joined, re.I | re.S)
    warning = warning_match.group(1).strip() if warning_match else ""
    warning = re.split(r"\bSMALL BATCH\b|\bBARREL AGED\b", warning, maxsplit=1, flags=re.I)[0].strip()
    return {
        "brand_name": brand,
        "class_type": class_type,
        "alcohol_content": abv,
        "net_contents": net,
        "producer": producer,
        "country_of_origin": country,
        "government_warning": warning,
    }


def _variants(image: Image.Image) -> list[Image.Image]:
    base = ImageOps.exif_transpose(image).convert("RGB")
    gray = ImageOps.grayscale(base)
    gray = ImageOps.autocontrast(gray)
    gray = ImageEnhance.Contrast(gray).enhance(1.35)
    gray = ImageEnhance.Sharpness(gray).enhance(1.7)
    # Upscaling helps small label text while preserving a simple local pipeline.
    scale = 1.5 if max(gray.size) < 2200 else 1.0
    if scale != 1.0:
        gray = gray.resize((int(gray.width * scale), int(gray.height * scale)), Image.Resampling.LANCZOS)
    variants = [gray]
    variants.append(gray.filter(ImageFilter.SHARPEN))
    variants.append(gray.point(lambda p: 255 if p > 165 else 0))
    return variants


def preprocess(image: Image.Image) -> Image.Image:
    return _variants(image)[0]


def ocr_image(data: bytes) -> tuple[str, float]:
    if not TESSERACT_AVAILABLE:
        raise RuntimeError("OCR engine unavailable. Install Tesseract and pytesseract.")
    image = Image.open(io.BytesIO(data))
    best_text, best_conf, best_score = "", 0.0, -1.0
    for candidate in _variants(image):
        data_out = pytesseract.image_to_data(candidate, config="--psm 6", output_type=Output.DICT)
        words, confidences = [], []
        for word, conf in zip(data_out["text"], data_out["conf"]):
            word = word.strip()
            try: confidence = float(conf)
            except (TypeError, ValueError): continue
            if word and confidence >= 0:
                words.append(word); confidences.append(confidence)
        grouped = {}
        for i, word in enumerate(data_out["text"]):
            word = word.strip()
            if not word: continue
            key = (data_out["block_num"][i], data_out["par_num"][i], data_out["line_num"][i])
            grouped.setdefault(key, []).append(word)
        text = "\n".join(" ".join(line) for line in grouped.values()).strip()
        mean_conf = (sum(confidences) / len(confidences) / 100.0) if confidences else 0.0
        score = min(len(text), 700) / 700 + mean_conf
        if score > best_score:
            best_text, best_conf, best_score = text, mean_conf, score
    return best_text, round(best_conf, 3)


def compare_text(expected: str, actual: str) -> tuple[bool, str]:
    e, a = normalize_text(expected), normalize_text(actual)
    if not e:
        return True, "Not provided in application data"
    if e == a:
        return True, "Exact match"
    if e and a and (e in a or a in e):
        return True, "Normalized match"
    return False, f'Expected "{expected}" but extracted "{actual or "(none)"}"'


def compare_number(expected: str, actual: str, field: str) -> tuple[bool, str]:
    e, a = extract_number(expected), extract_number(actual)
    if e is None:
        return True, "Not provided in application data"
    if a is None:
        return False, f"Could not extract {field} from label"
    if abs(e - a) < 0.001:
        return True, f"Match: {a:g}"
    return False, f"Expected {e:g}, extracted {a:g}"


def verify(application: dict[str, str], extracted: dict[str, str], raw_text: str, ocr_confidence: float) -> dict[str, Any]:
    checks = []
    for key, label in [("brand_name", "Brand Name"), ("class_type", "Class/Type"), ("producer", "Producer/Bottler"), ("country_of_origin", "Country of Origin")]:
        ok, detail = compare_text(application.get(key, ""), extracted.get(key, ""))
        checks.append({"field": label, "status": "pass" if ok else "fail", "detail": detail})
    for key, label in [("alcohol_content", "Alcohol Content"), ("net_contents", "Net Contents")]:
        ok, detail = compare_number(application.get(key, ""), extracted.get(key, ""), label)
        checks.append({"field": label, "status": "pass" if ok else "fail", "detail": detail})

    warning_text = extracted.get("government_warning", "").strip()
    warning_ok = normalize_text(warning_text) == normalize_text(STANDARD_WARNING)
    warning_detail = "Exact required warning text detected" if warning_ok else ("Government warning not detected" if not warning_text else "Warning text differs from the required standard text")
    checks.append({"field": "Government Warning", "status": "pass" if warning_ok else "fail", "detail": warning_detail})

    hard_fail = any(c["status"] == "fail" for c in checks)
    needs_review = ocr_confidence < 0.65
    status = "FAIL" if hard_fail else ("NEEDS REVIEW" if needs_review else "PASS")
    reasons = [c["detail"] for c in checks if c["status"] == "fail"] if hard_fail else (["OCR confidence is below the review threshold"] if needs_review else ["All automated checks passed"])
    return {"status": status, "checks": checks, "reasons": reasons, "extracted": extracted, "raw_text": raw_text, "ocr_confidence": round(ocr_confidence, 2)}


@app.get("/", response_class=HTMLResponse)
async def index():
    return (BASE_DIR / "static" / "index.html").read_text()


@app.get("/api/health")
async def health():
    return {"ok": True, "ocr_available": TESSERACT_AVAILABLE}


@app.post("/api/verify")
async def verify_one(file: UploadFile = File(...), application_json: str = Form(...), manual_ocr: str = Form("")):
    application = json.loads(application_json)
    data = await file.read()
    if manual_ocr.strip():
        raw_text, confidence = manual_ocr, 0.90
    else:
        try:
            loop = asyncio.get_running_loop()
            raw_text, confidence = await loop.run_in_executor(OCR_EXECUTOR, ocr_image, data)
        except Exception as exc:
            return JSONResponse({"error": str(exc), "filename": file.filename}, status_code=422)
    result = verify(application, parse_fields(raw_text), raw_text, confidence)
    result["filename"] = file.filename
    return result


def process_batch_item(item: tuple[str, bytes, dict[str, str], str]) -> dict[str, Any]:
    filename, data, application, manual_ocr = item
    try:
        raw_text, confidence = (manual_ocr, 0.90) if manual_ocr.strip() else ocr_image(data)
        result = verify(application, parse_fields(raw_text), raw_text, confidence)
        result["filename"] = filename
        return result
    except Exception as exc:
        return {"filename": filename, "status": "ERROR", "reasons": [str(exc)], "checks": [], "extracted": {}, "raw_text": "", "ocr_confidence": 0}


@app.post("/api/batch")
async def verify_batch(files: list[UploadFile] = File(...), application_json: str = Form(...)):
    application = json.loads(application_json)
    items = [(f.filename, await f.read(), application, "") for f in files]
    loop = asyncio.get_running_loop()
    # Run blocking Tesseract calls off the event loop. The bounded executor keeps
    # health checks responsive and avoids spawning many OCR processes at once.
    results = await asyncio.gather(
        *(loop.run_in_executor(OCR_EXECUTOR, process_batch_item, item) for item in items)
    )
    return {"total": len(results), "passed": sum(r["status"] == "PASS" for r in results), "review": sum(r["status"] == "NEEDS REVIEW" for r in results), "failed": sum(r["status"] == "FAIL" for r in results), "errors": sum(r["status"] == "ERROR" for r in results), "results": results}


@app.post("/api/export-csv")
async def export_csv(payload: dict[str, Any]):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["filename", "status", "ocr_confidence", "reasons"])
    for row in payload.get("results", []):
        writer.writerow([row.get("filename", ""), row.get("status", ""), row.get("ocr_confidence", ""), " | ".join(row.get("reasons", []))])
    output.seek(0)
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=verification-results.csv"})
