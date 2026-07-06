import base64
import hashlib
import json
import re
import ssl
import subprocess
import tempfile
import time
from pathlib import Path
import urllib3

from PIL import Image, ImageEnhance, ImageFilter, ImageOps
import requests

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def normalize_ocr_text(text):
    text = (text or "").strip()
    # Windows OCR often inserts spaces between Chinese characters.
    text = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", text)
    return text


def _run_windows_ocr_script(image_path, timeout=30):
    script_path = Path(__file__).with_name("windows_ocr.ps1")
    if not script_path.exists():
        return {"success": False, "text": "", "error": "Windows OCR脚本不存在", "source": "Windows OCR"}

    try:
        completed = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script_path),
                str(Path(image_path).resolve()),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
            check=False,
        )
    except Exception as e:
        return {"success": False, "text": "", "error": str(e), "source": "Windows OCR"}

    output = (completed.stdout or "").strip()
    if not output:
        return {
            "success": False,
            "text": "",
            "error": (completed.stderr or "Windows OCR无输出").strip(),
            "source": "Windows OCR",
        }

    try:
        result = json.loads(output)
    except json.JSONDecodeError:
        return {"success": False, "text": "", "error": output[:300], "source": "Windows OCR"}

    result["text"] = normalize_ocr_text(result.get("text", ""))
    return result


def _make_ocr_variants(image_path):
    variants = [Path(image_path).resolve()]
    temp_paths = []

    try:
        with Image.open(image_path) as img:
            img = ImageOps.exif_transpose(img).convert("RGB")
            max_side = max(img.size)
            if max_side < 1600:
                scale = 1600 / max_side
                new_size = (int(img.width * scale), int(img.height * scale))
                img = img.resize(new_size, Image.Resampling.LANCZOS)

            gray = ImageOps.grayscale(img)
            enhanced = ImageEnhance.Contrast(gray).enhance(2.2)
            sharpened = enhanced.filter(ImageFilter.SHARPEN)
            binary = sharpened.point(lambda p: 255 if p > 165 else 0)

            processed_images = [
                ("ocr_gray", enhanced),
                ("ocr_sharp", sharpened),
                ("ocr_binary", binary),
            ]

            for prefix, variant in processed_images:
                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=f"_{prefix}.png")
                temp_file.close()
                variant.save(temp_file.name)
                temp_paths.append(Path(temp_file.name))
                variants.append(Path(temp_file.name))
    except Exception:
        return variants, temp_paths

    return variants, temp_paths


def _ocr_text_score(text):
    text = normalize_ocr_text(text)
    chinese_chars = re.findall(r"[\u4e00-\u9fff]", text)
    meaningful_chars = re.findall(r"[\u4e00-\u9fffA-Za-z0-9]", text)
    return len(chinese_chars) * 2 + len(meaningful_chars)


def recognize_with_windows_ocr(image_path, timeout=30):
    variants, temp_paths = _make_ocr_variants(image_path)
    results = []

    try:
        for variant_path in variants:
            result = _run_windows_ocr_script(variant_path, timeout=timeout)
            result["variant"] = str(variant_path)
            results.append(result)
    finally:
        for temp_path in temp_paths:
            try:
                temp_path.unlink(missing_ok=True)
            except Exception:
                pass

    successful = [r for r in results if r.get("success")]
    if successful:
        best = max(successful, key=lambda r: _ocr_text_score(r.get("text", "")))
        best_text = normalize_ocr_text(best.get("text", ""))
        if best_text:
            best["text"] = best_text
            best["source"] = "Windows OCR（本地增强识别）"
            return best

    errors = [r.get("error", "") for r in results if r.get("error")]
    return {
        "success": False,
        "text": "",
        "error": "；".join(dict.fromkeys(errors)) or "本地OCR未识别到清晰文字",
        "source": "Windows OCR（本地增强识别）",
    }


class XunfeiOCR:
    ENDPOINTS = {
        "通用印刷体": "/v1/service/v1/ocr/general",
        "手写体识别": "/v1/service/v1/ocr/handwriting"
    }

    def __init__(self, app_id, api_key, api_secret, ocr_type="手写体识别"):
        self.app_id = app_id
        self.api_key = api_key
        self.api_secret = api_secret
        self.host = "webapi.xfyun.cn"
        self.endpoint = self.ENDPOINTS.get(ocr_type, "/v1/service/v1/ocr/handwriting")

    def image_to_base64(self, image_path):
        with open(image_path, "rb") as f:
            base64_str = base64.b64encode(f.read()).decode("utf-8")
        return base64_str

    def _extract_text(self, value):
        texts = []
        if isinstance(value, dict):
            for key, item in value.items():
                if key in {"text", "content"} and isinstance(item, str) and item.strip():
                    texts.append(item.strip())
                else:
                    texts.extend(self._extract_text(item))
        elif isinstance(value, list):
            for item in value:
                texts.extend(self._extract_text(item))
        return texts

    def recognize(self, image_path):
        base64_str = self.image_to_base64(image_path)

        x_cur_time = str(int(time.time()))
        x_param = base64.b64encode(
            json.dumps({"language": "zh", "location": "true"}).encode("utf-8")
        ).decode("utf-8")

        x_checksum = hashlib.md5(
            (self.api_key + x_cur_time + x_param).encode("utf-8")
        ).hexdigest()

        headers = {
            "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
            "X-Appid": self.app_id,
            "X-CurTime": x_cur_time,
            "X-Param": x_param,
            "X-CheckSum": x_checksum
        }

        data = {
            "image": base64_str
        }

        url = f"https://{self.host}{self.endpoint}"
        try:
            ctx = ssl.create_default_context()
            ctx.set_ciphers('DEFAULT@SECLEVEL=1')
            response = requests.post(url, headers=headers, data=data, verify=False)
            response.raise_for_status()
            result = response.json()
        except requests.exceptions.SSLError as e:
            return {"success": False, "error": f"SSL连接错误: {str(e)}", "raw": None}
        except requests.exceptions.RequestException as e:
            return {"success": False, "error": f"网络请求错误: {str(e)}", "raw": None}

        if result.get("code") == "0":
            words_result = result.get("data", {}).get("block", [])
            text_items = self._extract_text(words_result)
            text = "\n".join(dict.fromkeys(text_items))
            return {"success": True, "text": text, "raw": result}
        else:
            return {"success": False, "error": result.get("desc", "Unknown error"), "raw": result}
