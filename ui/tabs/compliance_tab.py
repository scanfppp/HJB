"""
合规自查区 — 提交制度/方案对照现行标准校验
"""

import io
import streamlit as st

from rag.compliance import check_compliance
from retrieval.filter import get_filter_options
from utils.logger import get_logger

logger = get_logger(__name__)


def render_compliance_tab():
    with st.container(border=True):
        st.subheader("✅ 标准合规自查")
        st.caption("提交制度/方案内容，对照现行海军标准进行合规性校验")

    c1, c2 = st.columns([1, 1], gap="large")

    with c1:
        with st.container(border=True):
            st.markdown("**📝 提交制度/方案**")
            submitted_text = st.text_area(
                "内容",
                height=380,
                placeholder="请粘贴需要校验的制度内容、管理方案、操作规程...",
                label_visibility="collapsed",
            )

            uploaded = st.file_uploader("或上传文档", type=["txt", "docx"])
            if uploaded:
                try:
                    if uploaded.name.endswith(".txt"):
                        submitted_text = uploaded.read().decode("utf-8")
                    elif uploaded.name.endswith(".docx"):
                        from docx import Document
                        doc = Document(io.BytesIO(uploaded.read()))
                        submitted_text = "\n".join(p.text for p in doc.paragraphs)
                    if submitted_text:
                        st.success(f"已加载: {uploaded.name}")
                except Exception as e:
                    st.error(f"文件读取失败: {e}")

    with c2:
        with st.container(border=True):
            st.markdown("**📊 合规校验报告**")

    filter_options = get_filter_options()
    applicable_field = st.selectbox(
        "校验领域（可选）",
        ["全部领域"] + filter_options["fields"],
    )

    if st.button("✅ 开始合规校验", type="primary", use_container_width=True):
        text_to_check = submitted_text
        if not text_to_check.strip():
            st.warning("请先输入需要校验的制度/方案内容")
            return

        with st.spinner("正在检索相关标准并进行合规校验..."):
            result = check_compliance(
                submitted_text=text_to_check,
                applicable_field=applicable_field if applicable_field != "全部领域" else None,
            )

        if "error" in result:
            st.error(result["error"])
            return

        with c2:
            with st.container(border=True):
                st.success(f"对照片 {result.get('standards_count', 0)} 条标准条款")
                st.markdown(result.get("report", "报告生成失败"))

                if result.get("sources"):
                    with st.expander("📖 引用标准条款"):
                        for s in result["sources"]:
                            st.caption(
                                f"[{s['standard_number']}] {s['standard_name']} "
                                f"> {s['section_title']} {s['clause_number']}"
                            )

                st.download_button(
                    "📥 下载合规报告",
                    result.get("report", ""),
                    file_name="合规自查报告.txt",
                    mime="text/plain",
                )
