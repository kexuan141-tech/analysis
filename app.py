import os
import tempfile
from datetime import datetime

import matplotlib.pyplot as plt
import streamlit as st
from dotenv import load_dotenv
from PIL import Image

from utils.analyzer import (
    XunfeiSpark, format_analysis_result, generate_docx_report,
    generate_html_report, generate_emotion_radar_chart, generate_emotion_bar_chart
)

load_dotenv()

APP_ID = os.getenv("XUNFEI_APP_ID")
API_KEY = os.getenv("XUNFEI_API_KEY")
API_SECRET = os.getenv("XUNFEI_API_SECRET")
API_PASSWORD = os.getenv("XUNFEI_API_PASSWORD")

def init_session_state():
    if "analysis_result" not in st.session_state:
        st.session_state.analysis_result = None
    if "child_info" not in st.session_state:
        st.session_state.child_info = None
    if "temp_image_paths" not in st.session_state:
        st.session_state.temp_image_paths = []
    if "manual_description" not in st.session_state:
        st.session_state.manual_description = ""

def get_file_extension(file_name):
    if file_name.lower().endswith('.png'):
        return '.png'
    elif file_name.lower().endswith('.jpeg'):
        return '.jpeg'
    else:
        return '.jpg'

def main():
    init_session_state()

    st.set_page_config(
        page_title="留守儿童情绪手账分析系统",
        page_icon="📒",
        layout="wide"
    )

    st.title("📒 留守儿童情绪手账分析系统")
    st.markdown("---")

    st.sidebar.header("孩子信息")
    child_name = st.sidebar.text_input("姓名", placeholder="请输入孩子姓名")
    child_age = st.sidebar.number_input("年龄", min_value=1, max_value=18, value=10)
    gender_options = ["男", "女", "未知"]
    child_gender = st.sidebar.selectbox("性别", gender_options)
    grade = st.sidebar.text_input("年级", placeholder="如：小学三年级")

    st.sidebar.markdown("---")
    st.sidebar.subheader("分析设置")
    spark_version = st.sidebar.selectbox(
        "星火大模型版本",
        ["Spark X2", "Spark X1.5", "Spark Lite", "Spark Pro", "Spark Max"],
        index=0
    )

    st.sidebar.markdown("---")
    st.sidebar.subheader("上传手账图片")
    uploaded_files = st.sidebar.file_uploader(
        "选择图片（支持绘画和手写文字）",
        type=["jpg", "jpeg", "png"],
        accept_multiple_files=True
    )

    if uploaded_files:
        st.sidebar.success(f"已上传 {len(uploaded_files)} 张图片")

    if not uploaded_files:
        st.sidebar.caption("请先上传至少 1 张手账图片")

    analyze_button = st.sidebar.button("🔍 开始分析", disabled=not uploaded_files)

    manual_text = st.text_area(
        "✏️ 补充描述（可选，如：绘画主题、颜色、孩子的心情等）",
        value=st.session_state.manual_description,
        height=150,
        placeholder="例如：孩子画了一幅彩色的画，画中有太阳、房子和笑脸...\n孩子写到：今天很开心..."
    )

    if st.button("💾 保存描述"):
        st.session_state.manual_description = manual_text
        st.success("描述已保存！")

    if analyze_button:
        st.session_state.analysis_result = None
        st.session_state.temp_image_paths = []

        with st.spinner("正在保存图片并分析..."):
            temp_paths = []
            for file in uploaded_files:
                ext = get_file_extension(file.name)
                with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as temp_file:
                    temp_file.write(file.read())
                    temp_paths.append(temp_file.name)

            st.session_state.temp_image_paths = temp_paths

            display_name = child_name.strip() if child_name.strip() else "未填写"
            display_grade = grade.strip() if grade.strip() else "未填写"

            spark = XunfeiSpark(APP_ID, API_KEY, API_SECRET, version=spark_version, api_password=API_PASSWORD)
            child_info = f"姓名：{display_name}，年龄：{child_age}，性别：{child_gender}，年级：{display_grade}"

            if manual_text.strip():
                child_info += f"\n补充描述：{manual_text}"

            analysis_result = spark.analyze_image(temp_paths, child_info)

            for path in temp_paths:
                os.unlink(path)

            if analysis_result["success"]:
                st.session_state.analysis_result = analysis_result
                st.session_state.child_info = {
                    "name": display_name,
                    "age": child_age,
                    "gender": child_gender,
                    "grade": display_grade
                }
            else:
                st.error(f"分析失败: {analysis_result['error']}")

    if st.session_state.analysis_result and st.session_state.child_info:
        formatted_result = format_analysis_result(st.session_state.analysis_result)
        child_info = st.session_state.child_info

        tabs = st.tabs(["📊 概览", "🧠 性格画像", "📈 情绪分析", "💡 教育建议", "📄 报告下载"])

        with tabs[0]:
            st.subheader("📋 学生基本信息")
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("姓名", child_info["name"])
            col2.metric("年龄", child_info["age"])
            col3.metric("性别", child_info["gender"])
            col4.metric("年级", child_info["grade"] if child_info["grade"] else "未填写")

            st.subheader("📌 图片内容识别")
            image_content_section = ""
            if "【图片内容识别】" in formatted_result:
                image_content_section = formatted_result.split("【图片内容识别】")[1].split("【")[0]
            elif "情绪状态分析" in formatted_result:
                image_content_section = formatted_result.split("【情绪状态分析】")[0]
            st.markdown(image_content_section)

            st.subheader("📌 情绪状态分析")
            emotion_section = formatted_result.split("【情绪状态分析】")[1].split("【")[0] if "【情绪状态分析】" in formatted_result else ""
            st.markdown(emotion_section)

            st.subheader("⚠️ 风险评估")
            risk_section = formatted_result.split("【风险评估】")[1].split("【")[0] if "【风险评估】" in formatted_result else ""
            st.markdown(risk_section)

        with tabs[1]:
            st.subheader("🧠 性格特征画像")
            personality_section = formatted_result.split("【性格特征画像】")[1].split("【")[0] if "【性格特征画像】" in formatted_result else ""
            st.markdown(personality_section)

            st.subheader("🎯 行为倾向预测")
            behavior_section = formatted_result.split("【行为倾向预测】")[1].split("【")[0] if "【行为倾向预测】" in formatted_result else ""
            st.markdown(behavior_section)

        with tabs[2]:
            st.subheader("📊 情绪雷达图")
            radar_chart = generate_emotion_radar_chart(formatted_result)
            st.image(radar_chart)

            st.subheader("📈 情绪分布分析")
            bar_chart = generate_emotion_bar_chart(formatted_result)
            st.image(bar_chart)

        with tabs[3]:
            st.subheader("💡 教育建议")
            advice_section = formatted_result.split("【教育建议】")[1].split("【")[0] if "【教育建议】" in formatted_result else ""
            st.markdown(advice_section)

        with tabs[4]:
            st.subheader("📄 分析报告下载")

            radar_chart = generate_emotion_radar_chart(formatted_result)
            bar_chart = generate_emotion_bar_chart(formatted_result)
            docx_report = generate_docx_report(
                formatted_result,
                child_info["name"],
                child_info["age"],
                child_info["gender"],
                child_info["grade"],
                chart_images=[
                    ("情绪雷达图", radar_chart),
                    ("情绪分布分析图", bar_chart),
                ]
            )

            html_report = generate_html_report(
                formatted_result,
                child_info["name"],
                child_info["age"],
                child_info["gender"],
                child_info["grade"],
                handwritten_text=manual_text if manual_text else formatted_result[:500]
            )

            col1, col2 = st.columns(2)
            with col1:
                st.download_button(
                    "📥 下载Word报告",
                    docx_report,
                    file_name=f"情绪手账分析报告_{child_info['name']}_{datetime.now().strftime('%Y%m%d')}.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                )

            with col2:
                st.download_button(
                    "📄 下载HTML报告",
                    html_report,
                    file_name=f"情绪手账分析报告_{child_info['name']}_{datetime.now().strftime('%Y%m%d')}.html",
                    mime="text/html"
                )

            st.info("💡 提示：Word报告可直接用于整理支教成果材料；HTML报告适合网页预览或打印为PDF。")

            st.markdown("---")
            st.subheader("预览HTML报告")
            st.components.v1.html(html_report, height=800, scrolling=True)

    else:
        st.markdown("---")
        st.info("""
        💡 **使用说明**：
        1. 在左侧栏填写孩子基本信息（姓名、年龄、性别、年级）
        2. 上传手账图片（支持绘画和手写文字）
        3. （可选）在下方输入框补充描述绘画主题、颜色、孩子心情等
        4. 点击「开始分析」按钮，AI会自动识别图片中的文字和绘画内容并生成心理报告
        5. 在「报告下载」Tab中下载分析报告
        
        ⚠️ **注意**：本系统仅用于辅助分析，不能替代专业心理诊断。
        如发现孩子有严重心理问题，请及时联系专业心理咨询师。
        """)

        if uploaded_files:
            st.subheader("🖼️ 上传的图片")
            cols = st.columns(3)
            for i, file in enumerate(uploaded_files):
                img = Image.open(file)
                with cols[i % 3]:
                    st.image(img, caption=f"图片 {i+1}", width='stretch')


if __name__ == "__main__":
    main()
