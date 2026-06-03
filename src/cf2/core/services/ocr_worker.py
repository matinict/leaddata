"""
ocr_worker.py — Isolated OCR subprocess worker (Tesseract backend)
Output: JSON to stdout, errors to stderr.
"""
import os
import sys
import json
import re
import warnings
from pathlib import Path
from typing import List

# Suppress all warnings
warnings.filterwarnings("ignore")

from PIL import Image
import pytesseract

# OEM 3 = Default, PSM 6 = Uniform block of text
TESSERACT_CONFIG = "--oem 3 --psm 6"

_IDE_NOISE_PATTERNS = [
    re.compile(r"^new \*$", re.I),
    re.compile(r"^\d+ usages?(\s+new \*)?$", re.I),
    re.compile(r"^Next Tip$", re.I),
    re.compile(r"^Press Ctrl", re.I),
    re.compile(r"^Ctrl\+", re.I),
    re.compile(r"^Current File", re.I),
    re.compile(r"^\w+\.py(\s*×)?$", re.I),
]

_TERMINAL_PATTERNS = [
    re.compile(r"traceback|error:|exception|command not found|pip install", re.I)
]

_CODE_PATTERNS = [
    re.compile(r"\bdef\s|\bclass\s|import\s|return\s|\bself\.|print\("),
    re.compile(r"__init__\s*\(|^\s*#|^\s*//")
]

def _classify(text: str) -> str:
    t = text.lower().strip()
    if t.startswith(("$", ">>>", "ps1>")): return "terminal"
    for pat in _TERMINAL_PATTERNS:
        if pat.search(t): return "terminal"
    for pat in _CODE_PATTERNS:
        if pat.search(t): return "code"
    return "ui"

def _run_tesseract(img: Image.Image) -> List[dict]:
    try:
        data = pytesseract.image_to_data(img, config=TESSERACT_CONFIG, output_type=pytesseract.Output.DICT)
    except Exception as e:
        print(f"[OCR_WORKER_ERROR] Tesseract failed: {e}", file=sys.stderr)
        return []

    lines = {}
    for i in range(len(data["text"])):
        word = data["text"][i].strip()
        if not word or float(data["conf"][i]) < 0: continue
        key = (data["block_num"][i], data["line_num"][i])
        if key not in lines: lines[key] = {"words": [], "confs": [], "y": data["top"][i]}
        lines[key]["words"].append(word)
        lines[key]["confs"].append(float(data["conf"][i]))

    results = []
    for line in lines.values():
        text = " ".join(line["words"]).strip()
        if len(text) < 3: continue
        results.append({
            "text": text,
            "confidence": round(sum(line["confs"]) / len(line["confs"]) / 100.0, 3),
            "y": line["y"],
            "type": _classify(text)
        })
    return results

if __name__ == "__main__":
    if len(sys.argv) != 2: sys.exit(1)
    try:
        args = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
        with Image.open(args["image_path"]) as raw:
            img = raw.convert("RGB")
            if args.get("crop_region"):
                x, y, w, h = [int(v) for v in args["crop_region"]]
                img = img.crop((x, y, x + w, y + h))
        
        blocks = _run_tesseract(img)
        # Filter blocks based on threshold
        blocks = [b for b in blocks if b["confidence"] >= args.get("confidence_threshold", 0.7)]
        # Sort and clean
        blocks.sort(key=lambda b: b["y"])
        final = [{"text": b["text"], "confidence": b["confidence"], "type": b["type"]} for b in blocks]
        sys.stdout.write(json.dumps(final, ensure_ascii=False))
    except Exception as e:
        print(f"[OCR_WORKER_ERROR] {e}", file=sys.stderr)
        sys.stdout.write("[]")
    sys.stdout.flush()
