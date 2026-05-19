"""
文档总结区 — 长文档智能结构化总结
"""

import streamlit as st

from database.operations import list_documents, get_document
from rag.summarizer import summarize_document
from utils.logger import get_logger

logger = get_logger(__name__)


def render_summary_tab():
    with st.container(border=True):
        st.subheader("📋 长文档智能总结")
        st.caption("自动提炼适用范围、核心技术指标、管理要求、验收规则、禁忌事项")

        docs = list_documents(is_active=True, limit=100)
        if not docs:
            st.info("📭 暂无已入库文档，请先上传标准文档")
            return

        doc_options = {
            f"[{d.get('standard_number', 'N/A')}] {d.get('standard_name', 'N/A')} (ID:{d['id']})": d["id"]
            for d in docs
        }

        c1, c2, c3 = st.columns([4, 1, 1])
        with c1:
            selected = st.selectbox("选择标准文档", list(doc_options.keys()), label_visibility="collapsed")
        with c2:
            detail = st.radio("输出格式", ["精简版", "完整版"], horizontal=True)
        with c3:
            st.write("")
            start = st.button("📋 开始总结", type="primary", use_container_width=True)

        if selected and start:
            doc_id = doc_options[selected]
            doc = get_document(doc_id)
            if doc:
                st.info(
                    f"**{doc.get('standard_number', '')} {doc.get('standard_name', '')}** | "
                    f"状态: {doc.get('doc_status', '')} | 领域: {doc.get('applicable_field', '')}"
                )

            with st.spinner("正在结构化总结..."):
                result = summarize_document(doc_id, detail_level="brief" if detail == "精简版" else "full")

            if "error" in result:
                st.error(result["error"])
                return

            st.success(f"处理了 {result.get('chunks_processed', 0)} 个内容块")

            if detail == "精简版":
                st.markdown(result.get("brief_summary", ""))
            else:
                st.markdown(result.get("full_summary", ""))
