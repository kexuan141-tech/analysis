import base64
import hashlib
import hmac
import io
import json
import mimetypes
import os
import re
import struct
import time
import urllib.parse
import zipfile
from collections import Counter
from datetime import datetime
from xml.sax.saxutils import escape

import matplotlib.pyplot as plt
from matplotlib import font_manager
from PIL import Image, ImageStat
import requests
import websockets

from utils.ocr import XunfeiOCR, recognize_with_windows_ocr


class XunfeiSpark:
    API_VERSIONS = {
        "Spark Lite": "/v1.1/chat",
        "Spark Pro": "/v2.1/chat",
        "Spark Max": "/v3.5/chat",
        "Spark X2": "/x2/chat/completions",
        "Spark X1.5": "/v2/chat/completions"
    }

    def __init__(self, app_id, api_key, api_secret, version="Spark X2", api_password=None):
        self.app_id = app_id
        self.api_key = api_key
        self.api_secret = api_secret
        self.api_password = api_password
        self.host = "spark-api-open.xf-yun.com"
        self.http_path = self.API_VERSIONS.get(version, "/x2/chat/completions")
        self.http_url = f"https://{self.host}{self.http_path}"
        self.version = version

    def _generate_http_headers(self):
        if self.version in ["Spark X2", "Spark X1.5"]:
            if self.api_password:
                return {
                    "Authorization": f"Bearer {self.api_password}",
                    "Content-Type": "application/json"
                }
            return {
                "Authorization": f"Bearer {self.api_secret}:{self.api_key}",
                "Content-Type": "application/json"
            }
        
        timestamp = str(int(time.time()))
        signature_origin = f"host: {self.host}\ndate: {timestamp}\nPOST {self.http_path} HTTP/1.1"
        signature_sha = hmac.new(
            self.api_secret.encode("utf-8"),
            signature_origin.encode("utf-8"),
            digestmod=hashlib.sha256
        ).digest()
        signature = base64.b64encode(signature_sha).decode("utf-8")
        authorization_origin = (
            f'api_key="{self.api_key}", algorithm="hmac-sha256", '
            f'headers="host date request-line", signature="{signature}"'
        )
        authorization = base64.b64encode(authorization_origin.encode("utf-8")).decode("utf-8")
        return {
            "Authorization": authorization,
            "Content-Type": "application/json",
            "Host": self.host,
            "Date": timestamp
        }

    def image_to_data_url(self, image_path):
        mime_type, _ = mimetypes.guess_type(image_path)
        if mime_type not in {"image/jpeg", "image/png"}:
            mime_type = "image/jpeg"

        with Image.open(image_path) as img:
            buf = io.BytesIO()
            if mime_type == "image/png":
                img.save(buf, format="PNG")
            else:
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")
                img.save(buf, format="JPEG", quality=92)

        base64_str = base64.b64encode(buf.getvalue()).decode("utf-8")
        return f"data:{mime_type};base64,{base64_str}"

    def image_to_base64(self, image_path):
        with open(image_path, "rb") as f:
            base64_str = base64.b64encode(f.read()).decode("utf-8")
        return base64_str

    def analyze_image(self, image_paths, child_info=None):
        image_evidence = self._build_image_evidence(image_paths)
        prompt = f"""
你是一位专业、稳健的儿童心理关怀辅助分析老师，服务乡村支教场景和留守儿童情绪手账分析。

系统已经从上传图片中提取了以下材料。请严格基于这些材料分析，不要声称自己直接看到了未被识别出的具体物体。请输出明确、可直接放进支教成果报告的分析结果。

重要规则：
1. OCR文字如果是明显乱码、键盘字符、随机英文字母/数字片段，视为“文字识别无有效内容”，不要解释它的含义。
2. 对清晰证据给出明确结论，不要反复写“不确定性”“不足以判断”等拖沓表述。
3. 不能替代专业心理诊断，但这句话只在最后风险提示中简短出现一次。
4. 结论要服务支教老师实际使用：能看懂、能行动、能作为成果材料。

【学生信息】
{child_info or "未填写"}

【图片识别材料】
{image_evidence}

请输出以下结构，标题必须完全保留：

【图片内容识别】
- 手写/印刷文字识别结果
- 绘画与版面线索：颜色、明暗、留白、线条/涂画密度
- 综合识别结论

【情绪状态分析】
- 当前主导情绪
- 情绪强度评估（1-10分）
- 情绪表现结论

【性格特征画像】
- 性格类型倾向（内向型/外向型/混合型）
- 主要性格特质（至少3项）
- 潜在心理需求

【行为倾向预测】
- 社交行为倾向
- 学习行为倾向
- 情绪调节能力

【教育建议】
- 针对当前情绪的疏导建议
- 性格培养建议
- 家校沟通建议

【风险评估】
- 风险等级（低/中/高/不足以判断）
- 风险描述（如适用）
- 干预建议

语言要温暖、专业、便于支教老师直接使用。不要输出“当前接口不能识别图片”这类话，因为系统已经完成了 OCR 和图像特征提取。
"""
        return self._send_http_request([{"role": "user", "content": prompt.strip()}])

    def _build_image_evidence(self, image_paths):
        evidence_parts = []
        for index, image_path in enumerate(image_paths, start=1):
            ocr_result = recognize_with_windows_ocr(image_path)
            text = ocr_result.get("text", "").strip() if ocr_result.get("success") else ""
            text = self._clean_ocr_text(text)
            ocr_source = ocr_result.get("source", "Windows OCR")
            ocr_error = ocr_result.get("error", "") if not text else ""

            if not text and os.getenv("ENABLE_XUNFEI_OCR", "").strip() == "1":
                ocr = XunfeiOCR(self.app_id, self.api_key, self.api_secret, ocr_type="手写体识别")
                ocr_result = ocr.recognize(image_path)
                text = ocr_result.get("text", "").strip() if ocr_result.get("success") else ""
                text = self._clean_ocr_text(text)
                ocr_source = "讯飞手写 OCR"
                ocr_error = ocr_result.get("error", "") if not text else ""

            if not text and os.getenv("ENABLE_XUNFEI_OCR", "").strip() == "1":
                general_ocr = XunfeiOCR(self.app_id, self.api_key, self.api_secret, ocr_type="通用印刷体")
                general_result = general_ocr.recognize(image_path)
                text = general_result.get("text", "").strip() if general_result.get("success") else ""
                text = self._clean_ocr_text(text)
                ocr_source = "讯飞通用 OCR"
                ocr_error = general_result.get("error") if not general_result.get("success") else ""

            visual = self._describe_image_features(image_path)
            evidence_parts.append(
                f"""图片{index}：
- OCR文字：{text if text else "未识别到清晰文字"}
- OCR状态：{"成功" if text else ("未识别到文字" + (f"，原因：{ocr_error}" if ocr_error else ""))}（来源：{ocr_source}）
- 图像特征：{visual}
"""
            )

        return "\n".join(evidence_parts).strip()

    def _clean_ocr_text(self, text):
        text = (text or "").strip()
        if not text:
            return ""

        text = re.sub(r"\s+", " ", text)
        chinese_chars = re.findall(r"[\u4e00-\u9fff]", text)
        latin_digits = re.findall(r"[A-Za-z0-9]", text)
        meaningful = re.findall(r"[\u4e00-\u9fffA-Za-z0-9]", text)

        if len(chinese_chars) >= 2:
            return text

        if len(meaningful) < 4:
            return ""

        # Avoid treating keyboard fragments such as "Shift 7 0 ob" as diary content.
        if len(chinese_chars) == 0 and len(latin_digits) >= 4:
            return ""

        return text

    def _describe_image_features(self, image_path):
        with Image.open(image_path) as img:
            img = img.convert("RGB")
            width, height = img.size
            sample = img.copy()
            sample.thumbnail((240, 240))
            pixels = list(sample.getdata())

        total = max(len(pixels), 1)
        stat = ImageStat.Stat(sample)
        brightness = sum(stat.mean) / 3
        non_white = 0
        dark = 0
        warm = 0
        cool = 0
        saturated = 0
        color_names = []

        for r, g, b in pixels:
            mx = max(r, g, b)
            mn = min(r, g, b)
            saturation = (mx - mn) / max(mx, 1)
            if not (r > 238 and g > 238 and b > 238):
                non_white += 1
            if r < 80 and g < 80 and b < 80:
                dark += 1
            if saturation > 0.22:
                saturated += 1
                if r > 160 and g > 110 and b < 120:
                    warm += 1
                    color_names.append("暖色/黄色橙色")
                elif r > 150 and b > 120 and g < 120:
                    color_names.append("粉红/紫色")
                elif b > r + 25 and b > g + 15:
                    cool += 1
                    color_names.append("蓝色/冷色")
                elif g > r + 20 and g > b + 10:
                    color_names.append("绿色")
                elif r > g + 30 and r > b + 30:
                    warm += 1
                    color_names.append("红色")

        used_ratio = non_white / total
        dark_ratio = dark / total
        saturated_ratio = saturated / total
        warm_ratio = warm / total
        cool_ratio = cool / total
        dominant_colors = [name for name, _ in Counter(color_names).most_common(4)]

        brightness_desc = "明亮" if brightness >= 190 else "偏暗" if brightness < 120 else "中等亮度"
        density_desc = "画面/书写内容较多" if used_ratio > 0.35 else "内容密度中等" if used_ratio > 0.12 else "留白较多、内容较少"
        saturation_desc = "色彩较丰富" if saturated_ratio > 0.18 else "色彩较少或以黑白线条为主"
        color_desc = "、".join(dominant_colors) if dominant_colors else "未检测到明显彩色区域"

        possible_cues = []
        if warm_ratio > cool_ratio and warm_ratio > 0.04:
            possible_cues.append("暖色占比较高，通常可作为积极、活跃或需要被关注的线索")
        if cool_ratio > warm_ratio and cool_ratio > 0.04:
            possible_cues.append("冷色占比较高，可能提示平静、克制或低落情绪，需要结合文字判断")
        if dark_ratio > 0.12:
            possible_cues.append("深色区域较多，需关注是否有压抑、紧张或强烈表达")
        if used_ratio < 0.08:
            possible_cues.append("留白较多，可能是表达较少、任务投入不足或拍摄范围较空")
        if saturated_ratio > 0.24:
            possible_cues.append("颜色使用丰富，可能提示表达意愿较强或情绪能量较高")

        cue_text = "；".join(possible_cues) if possible_cues else "未见特别突出的颜色风险线索，需结合文字和现场观察判断"
        return (
            f"尺寸{width}x{height}；整体亮度：{brightness_desc}；版面：{density_desc}；"
            f"色彩：{saturation_desc}，主要色彩为{color_desc}；"
            f"非白内容占比约{used_ratio:.0%}，深色占比约{dark_ratio:.0%}。"
            f"可能线索：{cue_text}"
        )

    def analyze_personality(self, handwritten_text, child_info=None):
        child_desc = ""
        if child_info:
            child_desc = f"，孩子信息：{child_info}"

        prompt = f"""
你是一位专业的儿童心理分析师，正在分析一位留守儿童的情绪手账。

手账内容如下：
{handwritten_text}

请根据以上内容，从以下维度进行专业分析：

1. 【情绪状态分析】
   - 当前主导情绪（如：开心、难过、焦虑、孤独等）
   - 情绪强度评估（1-10分）
   - 情绪变化趋势

2. 【性格特征画像】
   - 性格类型（如：内向型、外向型、混合型）
   - 主要性格特质（至少3项）
   - 潜在的心理需求

3. 【行为倾向预测】
   - 社交行为倾向
   - 学习行为倾向
   - 情绪调节能力

4. 【教育建议】
   - 针对当前情绪的疏导建议
   - 性格培养建议
   - 家校沟通建议

5. 【风险评估】
   - 是否存在心理风险（低/中/高）
   - 风险描述（如适用）
   - 干预建议

请以结构化的方式输出分析结果，语言要温暖、专业，适合支教老师阅读参考。
"""

        messages = [{"role": "user", "content": prompt.strip()}]

        return self._send_http_request(messages)

    def _send_http_request(self, messages):
        headers = self._generate_http_headers()

        if self.version in ["Spark X2", "Spark X1.5"]:
            model_name = "spark-x"
            payload = {
                "model": model_name,
                "messages": messages,
                "temperature": 0.7,
                "max_tokens": 4096
            }
        else:
            payload = {
                "header": {
                    "app_id": self.app_id,
                    "uid": f"user_{int(time.time())}"
                },
                "parameter": {
                    "chat": {
                        "domain": "general",
                        "temperature": 0.7,
                        "max_tokens": 4096
                    }
                },
                "payload": {
                    "message": {
                        "text": messages
                    }
                }
            }

        try:
            response = requests.post(self.http_url, headers=headers, json=payload, verify=False)
            data = response.json()
            
            debug_info = {
                "version": self.version,
                "url": self.http_url,
                "status_code": response.status_code,
                "headers": {k: v for k, v in headers.items() if k != "Authorization"},
                "payload_sample": {
                    "model": payload.get("model"),
                    "message_count": len(payload.get("messages", [])),
                    "temperature": payload.get("temperature"),
                    "max_tokens": payload.get("max_tokens")
                },
                "response": data
            }
            
            log_path = os.path.join(os.getcwd(), "api_debug.log")
            with open(log_path, "w", encoding="utf-8") as f:
                f.write(json.dumps(debug_info, ensure_ascii=False, indent=2))
            
            if response.status_code != 200:
                error_detail = f"HTTP {response.status_code}: {json.dumps(data, ensure_ascii=False)[:500]}"
                return {"success": False, "error": error_detail}

            if self.version in ["Spark X2", "Spark X1.5"]:
                if data.get("error"):
                    error_msg = data["error"].get("message", str(data["error"]))
                    return {"success": False, "error": error_msg}
                
                choices = data.get("choices", [])
                if choices:
                    full_response = choices[0].get("message", {}).get("content", "")
                else:
                    full_response = ""
            else:
                code = data.get("header", {}).get("code", -1)
                if code != 0:
                    return {"success": False, "error": data.get("header", {}).get("message", "Unknown error")}
                
                choices = data.get("payload", {}).get("choices", {})
                text_list = choices.get("text", [])
                full_response = ""
                for item in text_list:
                    full_response += item.get("content", "")
            
            return {"success": True, "content": full_response}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _is_image_not_supported_error(self, result):
        if result.get("success"):
            return False
        error = str(result.get("error", "")).lower()
        return "image type not support" in error or "clientmsgerror" in error


def format_analysis_result(result):
    if not result.get("success"):
        return f"分析失败：{result.get('error', 'Unknown error')}"

    content = result.get("content", "")
    return content


def configure_chinese_font():
    font_candidates = [
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
        r"C:\Windows\Fonts\simsun.ttc",
    ]
    for font_path in font_candidates:
        if os.path.exists(font_path):
            font_manager.fontManager.addfont(font_path)
            font_prop = font_manager.FontProperties(fname=font_path)
            plt.rcParams["font.family"] = font_prop.get_name()
            plt.rcParams["axes.unicode_minus"] = False
            return font_prop

    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "SimSun", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    return None


def count_keywords(text, keywords):
    return sum(text.count(keyword) for keyword in keywords)


def build_emotion_category_scores(analysis_text):
    categories = {
        "积极情绪": ["开心", "快乐", "高兴", "喜悦", "愉快", "满足", "幸福", "积极", "明亮", "暖色", "乐观"],
        "平静安全": ["平静", "安心", "安全", "稳定", "放松", "温和"],
        "焦虑紧张": ["焦虑", "紧张", "担心", "害怕", "不安", "压力"],
        "孤独低落": ["孤独", "寂寞", "想念", "思念", "想家", "难过", "悲伤", "失落", "沮丧", "低落"],
        "愤怒委屈": ["愤怒", "生气", "烦躁", "不满", "委屈", "攻击", "冲突"],
    }

    raw_counts = {name: count_keywords(analysis_text, words) for name, words in categories.items()}
    scores = {}
    for name, count in raw_counts.items():
        scores[name] = min(10, count * 2) if count else 0
    return scores


def generate_emotion_radar_chart(analysis_text):
    font_prop = configure_chinese_font()
    category_scores = build_emotion_category_scores(analysis_text)
    labels = list(category_scores.keys())
    scores = list(category_scores.values())

    angles = [n / len(labels) * 2 * 3.14159 for n in range(len(labels))]
    scores += scores[:1]
    angles += angles[:1]

    fig = plt.figure(figsize=(7, 6.5), dpi=140)
    ax = fig.add_subplot(111, polar=True)
    ax.plot(angles, scores, 'o-', linewidth=2.5, color='#2F80ED')
    ax.fill(angles, scores, alpha=0.18, color='#56CCF2')
    ax.set_thetagrids(
        [angle * 180 / 3.14159 for angle in angles[:-1]],
        labels,
        fontproperties=font_prop,
        fontsize=11,
    )
    ax.set_title('情绪雷达图', y=1.1, fontsize=15, fontproperties=font_prop, color="#1F2937")
    ax.set_ylim(0, 10)
    ax.set_rlabel_position(18)
    ax.grid(color="#D1D5DB", linewidth=0.9)

    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight')
    buf.seek(0)
    img_base64 = base64.b64encode(buf.read()).decode('utf-8')
    plt.close(fig)

    return f"data:image/png;base64,{img_base64}"


def generate_emotion_bar_chart(analysis_text):
    font_prop = configure_chinese_font()
    category_scores = build_emotion_category_scores(analysis_text)
    emotions = list(category_scores.keys())
    counts = list(category_scores.values())
    total = sum(counts)
    percentages = [(c / total) * 100 if total > 0 else 0 for c in counts]

    if total == 0:
        percentages = [0 for _ in counts]

    colors = ['#4ADE80', '#60A5FA', '#FBBF24', '#A78BFA', '#F87171']
    fig, ax = plt.subplots(figsize=(8.5, 5), dpi=140)
    bars = ax.bar(emotions, percentages, color=colors, width=0.58)
    ax.set_ylabel('情绪提及比例 (%)')
    ax.set_title('情绪分布分析')
    ax.set_ylim(0, max(100, max(percentages) + 12 if percentages else 100))
    ax.grid(axis="y", color="#E5E7EB", linewidth=0.8)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(axis='x', rotation=0)

    for label in ax.get_xticklabels() + ax.get_yticklabels():
        label.set_fontproperties(font_prop)
    ax.title.set_fontproperties(font_prop)
    ax.yaxis.label.set_fontproperties(font_prop)

    for bar in bars:
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height,
                f'{height:.1f}%', ha='center', va='bottom', fontsize=9, fontproperties=font_prop)

    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight')
    buf.seek(0)
    img_base64 = base64.b64encode(buf.read()).decode('utf-8')
    plt.close(fig)

    return f"data:image/png;base64,{img_base64}"


def generate_report(analysis_result, child_name, child_age=None, child_gender=None, grade=None, date=None):
    if date is None:
        date = datetime.now().strftime("%Y年%m月%d日")

    report = f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    留守儿童情绪手账分析报告
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 基本信息
──────────────────────────────────────
姓名：{child_name}
年龄：{child_age if child_age else '未填写'}
性别：{child_gender if child_gender else '未填写'}
年级：{grade if grade else '未填写'}
分析日期：{date}

📊 分析结果
──────────────────────────────────────
{analysis_result}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
分析说明：本报告基于AI模型分析生成，仅供参考。
如发现异常情况，请及时联系专业心理辅导人员。
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
    return report


def _docx_paragraph(text="", bold=False, size=22, color="333333", spacing_after=120, indent=False):
    escaped = escape(str(text))
    bold_xml = "<w:b/>" if bold else ""
    indent_xml = '<w:ind w:left="420" w:hanging="180"/>' if indent else ""
    return f"""
<w:p>
  <w:pPr>{indent_xml}<w:spacing w:after="{spacing_after}"/></w:pPr>
  <w:r>
    <w:rPr>
      <w:rFonts w:ascii="Microsoft YaHei" w:hAnsi="Microsoft YaHei" w:eastAsia="Microsoft YaHei"/>
      {bold_xml}
      <w:color w:val="{color}"/>
      <w:sz w:val="{size}"/>
    </w:rPr>
    <w:t xml:space="preserve">{escaped}</w:t>
  </w:r>
</w:p>"""


def _docx_heading(text, level=1):
    size = 32 if level == 1 else 26
    color = "1F4E79" if level == 1 else "2F5597"
    return _docx_paragraph(text, bold=True, size=size, color=color, spacing_after=160)


def _png_dimensions(image_bytes):
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n") and len(image_bytes) >= 24:
        return struct.unpack(">II", image_bytes[16:24])
    return 800, 500


def _docx_image(rid, image_bytes, title, image_id, max_width_emu=5200000):
    width_px, height_px = _png_dimensions(image_bytes)
    ratio = height_px / max(width_px, 1)
    width_emu = max_width_emu
    height_emu = int(width_emu * ratio)
    escaped_title = escape(title)
    return f"""
<w:p>
  <w:pPr><w:jc w:val="center"/><w:spacing w:before="120" w:after="80"/></w:pPr>
  <w:r>
    <w:drawing>
      <wp:inline xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" distT="0" distB="0" distL="0" distR="0">
        <wp:extent cx="{width_emu}" cy="{height_emu}"/>
        <wp:effectExtent l="0" t="0" r="0" b="0"/>
        <wp:docPr id="{image_id}" name="{escaped_title}"/>
        <wp:cNvGraphicFramePr>
          <a:graphicFrameLocks xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" noChangeAspect="1"/>
        </wp:cNvGraphicFramePr>
        <a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
          <a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">
            <pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">
              <pic:nvPicPr>
                <pic:cNvPr id="{image_id}" name="{escaped_title}"/>
                <pic:cNvPicPr/>
              </pic:nvPicPr>
              <pic:blipFill>
                <a:blip xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" r:embed="{rid}"/>
                <a:stretch><a:fillRect/></a:stretch>
              </pic:blipFill>
              <pic:spPr>
                <a:xfrm><a:off x="0" y="0"/><a:ext cx="{width_emu}" cy="{height_emu}"/></a:xfrm>
                <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
              </pic:spPr>
            </pic:pic>
          </a:graphicData>
        </a:graphic>
      </wp:inline>
    </w:drawing>
  </w:r>
</w:p>
{_docx_paragraph(title, size=18, color="666666", spacing_after=160)}"""


def _data_url_to_png_bytes(data_url):
    if not data_url:
        return None
    if "," in data_url:
        data_url = data_url.split(",", 1)[1]
    try:
        return base64.b64decode(data_url)
    except Exception:
        return None


def generate_docx_report(analysis_result, child_name, child_age=None, child_gender=None, grade=None, date=None, chart_images=None):
    if date is None:
        date = datetime.now().strftime("%Y年%m月%d日")

    body_parts = [
        _docx_heading("留守儿童情绪手账分析报告", level=1),
        _docx_paragraph("专业儿童心理分析 · 助力乡村支教工作", size=20, color="666666", spacing_after=260),
        _docx_heading("一、学生基本信息", level=2),
        _docx_paragraph(f"姓名：{child_name or '未填写'}"),
        _docx_paragraph(f"年龄：{child_age if child_age else '未填写'}"),
        _docx_paragraph(f"性别：{child_gender or '未填写'}"),
        _docx_paragraph(f"年级：{grade or '未填写'}"),
        _docx_paragraph(f"分析日期：{date}", spacing_after=240),
        _docx_heading("二、分析结果", level=2),
    ]

    for raw_line in analysis_result.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("【") and line.endswith("】"):
            body_parts.append(_docx_heading(line.strip("【】"), level=2))
        elif line.startswith("- "):
            body_parts.append(_docx_paragraph("• " + line[2:], size=21, indent=True))
        else:
            body_parts.append(_docx_paragraph(line, size=21))

    image_files = []
    if chart_images:
        body_parts.append(_docx_heading("三、情绪可视化分析", level=2))
        for image_index, (title, data_url) in enumerate(chart_images, start=1):
            image_bytes = _data_url_to_png_bytes(data_url)
            if not image_bytes:
                continue
            rid = f"rId{image_index}"
            image_name = f"chart{image_index}.png"
            image_files.append((rid, image_name, image_bytes, title))
            body_parts.append(_docx_image(rid, image_bytes, title, image_index))

    body_parts.extend([
        _docx_heading("四、使用说明" if image_files else "三、使用说明", level=2),
        _docx_paragraph(
            "本报告由AI辅助生成，用于支教老师日常观察、沟通和心理健康关怀参考。"
            "如发现孩子持续低落、明显攻击、自伤言论或其他高风险表现，请及时联系专业心理辅导人员。",
            size=20,
            color="666666",
        ),
    ])

    document_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    {''.join(body_parts)}
    <w:sectPr>
      <w:pgSz w:w="12240" w:h="15840"/>
      <w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" w:header="720" w:footer="720" w:gutter="0"/>
    </w:sectPr>
  </w:body>
</w:document>"""

    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Default Extension="png" ContentType="image/png"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""

    package_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""

    image_rels = "\n".join(
        f'  <Relationship Id="{rid}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/{image_name}"/>'
        for rid, image_name, _, _ in image_files
    )
    document_rels = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
{image_rels}
</Relationships>"""

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as docx:
        docx.writestr("[Content_Types].xml", content_types)
        docx.writestr("_rels/.rels", package_rels)
        docx.writestr("word/document.xml", document_xml)
        docx.writestr("word/_rels/document.xml.rels", document_rels)
        for _, image_name, image_bytes, _ in image_files:
            docx.writestr(f"word/media/{image_name}", image_bytes)

    buffer.seek(0)
    return buffer.getvalue()


def generate_html_report(analysis_result, child_name, child_age=None, child_gender=None, grade=None, date=None, handwritten_text=None):
    if date is None:
        date = datetime.now().strftime("%Y年%m月%d日")

    radar_chart = generate_emotion_radar_chart(analysis_result)
    bar_chart = generate_emotion_bar_chart(analysis_result)

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>留守儿童情绪手账分析报告 - {child_name}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: 'Microsoft YaHei', 'SimHei', sans-serif; line-height: 1.8; color: #333; background: #f5f7fa; }}
        .report-container {{ max-width: 900px; margin: 30px auto; background: white; box-shadow: 0 4px 20px rgba(0,0,0,0.1); padding: 40px; }}
        .header {{ text-align: center; padding-bottom: 30px; border-bottom: 3px solid #4A90D9; }}
        .header h1 {{ color: #2C3E50; font-size: 28px; margin-bottom: 10px; }}
        .header .subtitle {{ color: #7F8C8D; font-size: 14px; }}
        .info-section {{ margin: 30px 0; padding: 20px; background: #E8F4FD; border-radius: 8px; }}
        .info-section h2 {{ color: #2980B9; font-size: 18px; margin-bottom: 15px; }}
        .info-grid {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 15px; }}
        .info-item {{ display: flex; }}
        .info-label {{ font-weight: bold; color: #5D6D7E; min-width: 80px; }}
        .info-value {{ color: #2C3E50; }}
        .analysis-section {{ margin: 30px 0; }}
        .analysis-section h2 {{ color: #2980B9; font-size: 20px; margin-bottom: 20px; padding-bottom: 10px; border-bottom: 2px solid #E8F4FD; }}
        .analysis-content {{ white-space: pre-wrap; font-size: 15px; color: #444; }}
        .chart-section {{ margin: 30px 0; text-align: center; }}
        .chart-section h3 {{ color: #3498DB; font-size: 16px; margin-bottom: 15px; }}
        .chart-section img {{ max-width: 100%; height: auto; border-radius: 8px; }}
        .footer {{ margin-top: 40px; padding-top: 20px; border-top: 1px solid #EEE; text-align: center; color: #95A5A6; font-size: 13px; }}
        .warning {{ background: #FFF3CD; border-left: 4px solid #FFC107; padding: 15px; margin: 20px 0; color: #856404; font-size: 14px; }}
        .handwritten-section {{ margin: 30px 0; }}
        .handwritten-section h2 {{ color: #2980B9; font-size: 18px; margin-bottom: 15px; }}
        .handwritten-content {{ background: #FAFAFA; padding: 20px; border-radius: 8px; border: 1px solid #EEE; font-family: 'KaiTi', serif; font-size: 15px; color: #555; white-space: pre-wrap; }}
    </style>
</head>
<body>
    <div class="report-container">
        <div class="header">
            <h1>📒 留守儿童情绪手账分析报告</h1>
            <div class="subtitle">专业儿童心理分析 · 助力支教工作</div>
        </div>
        
        <div class="info-section">
            <h2>📋 学生基本信息</h2>
            <div class="info-grid">
                <div class="info-item"><span class="info-label">姓名：</span><span class="info-value">{child_name}</span></div>
                <div class="info-item"><span class="info-label">年龄：</span><span class="info-value">{child_age if child_age else '未填写'}</span></div>
                <div class="info-item"><span class="info-label">性别：</span><span class="info-value">{child_gender if child_gender else '未填写'}</span></div>
                <div class="info-item"><span class="info-label">年级：</span><span class="info-value">{grade if grade else '未填写'}</span></div>
                <div class="info-item"><span class="info-label">分析日期：</span><span class="info-value">{date}</span></div>
            </div>
        </div>

        {f'''
        <div class="handwritten-section">
            <h2>📝 手账原始内容</h2>
            <div class="handwritten-content">{handwritten_text if handwritten_text else '暂无内容'}</div>
        </div>
        ''' if handwritten_text else ''}

        <div class="chart-section">
            <h3>📊 情绪雷达图</h3>
            <img src="{radar_chart}" alt="情绪雷达图">
        </div>

        <div class="chart-section">
            <h3>📈 情绪分布分析</h3>
            <img src="{bar_chart}" alt="情绪分布柱状图">
        </div>

        <div class="analysis-section">
            <h2>🧠 性格画像分析结果</h2>
            <div class="analysis-content">{analysis_result}</div>
        </div>

        <div class="warning">
            ⚠️ 分析说明：本报告基于AI模型分析生成，仅供支教老师参考。如发现孩子有严重心理问题，请及时联系专业心理咨询师进行干预。
        </div>

        <div class="footer">
            留守儿童情绪手账分析系统 · 关爱每一个孩子的成长
        </div>
    </div>
</body>
</html>"""
    return html
