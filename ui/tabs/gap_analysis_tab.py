"""
标准查漏补缺专区 — 关联标准检索 + 内容缺口分析 + 修订建议
"""

import streamlit as st

from database.operations import list_documents, get_document
from rag.gap_analyzer import analyze_gaps, compare_standards
from utils.logger import get_logger

logger = get_logger(__name__)


def render_gap_analysis_tab():
    with st.container(border=True):
        st.subheader("🔬 标准查漏补缺 & 内容升级优化")

        mode = st.radio(
            "分析模式",
            ["📊 单标准查漏补缺", "🔄 新旧版本差异对比"],
            horizontal=True,
        )

        if mode == "📊 单标准查漏补缺":
            _render_gap_analysis()
        else:
            _render_version_compare()


def _render_gap_analysis():
    st.caption("选取目标标准，自动检索同领域关联配套标准，识别内容缺口并给出增补建议")

    docs = list_documents(is_active=True, limit=100)
    if not docs:
        st.info("📭 暂无已入库文档")
        return

    doc_options = {
        f"[{d.get('standard_number', 'N/A')}] {d.get('standard_name', 'N/A')} (ID:{d['id']})": d["id"]
        for d in docs
    }

    c1, c2, c3 = st.columns([4, 1, 1])
    with c1:
        selected = st.selectbox("目标标准", list(doc_options.keys()), label_visibility="collapsed")
    with c2:
        include_draft = st.checkbox("生成修订初稿")
    with c3:
        st.write("")
        start = st.button("🔬 开始分析", type="primary", use_container_width=True)

    if selected and start:
        doc_id = doc_options[selected]
        doc_info = get_document(doc_id)

        with st.spinner("正在检索关联标准并分析..."):
            result = analyze_gaps(doc_id, include_draft=include_draft)

        if "error" in result:
            st.error(result["error"])
            return

        if result.get("related_standards"):
            st.subheader("📎 关联配套标准")
            cols = st.columns(min(len(result["related_standards"]), 3))
            for i, rs in enumerate(result["related_standards"]):
                with cols[i % 3]:
                    with st.container(border=True):
                        st.markdown(f"**[{rs['standard_number']}]**")
                        st.caption(rs['standard_name'])
                        st.caption(f"状态: {rs['doc_status']} | 相关度: {rs.get('similarity', 0):.2f}")

        st.subheader("📊 查漏补缺分析报告")
        report = result.get("gap_report", "")
        if report:
            with st.container(border=True):
                st.markdown(report)

        if include_draft and result.get("revision_draft"):
            with st.expander("📝 标准修订初稿", expanded=True):
                st.markdown(result["revision_draft"])


def _render_version_compare():
    st.caption("选择两个版本文档进行差异对比分析")

    docs = list_documents(is_active=True, limit=100)
    if len(docs) < 2:
        st.info("📭 需要至少2份已入库文档才能对比")
        return

    doc_options = {
        f"[{d.get('standard_number', 'N/A')}] {d.get('standard_name', 'N/A')} (ID:{d['id']})": d["id"]
        for d in docs
    }
    options_list = list(doc_options.keys())

    c1, c2 = st.columns(2)
    with c1:
        old_doc = st.selectbox("旧版本标准", options_list)
    with c2:
        new_idx = min(1, len(options_list) - 1)
        new_doc = st.selectbox("新版本标准", options_list, index=new_idx)

    if st.button("🔄 开始对比", type="primary", use_container_width=True):
        if old_doc == new_doc:
            st.warning("请选择两个不同的版本")
            return

        with st.spinner("正在对比分析..."):
            result = compare_standards(doc_options[old_doc], doc_options[new_doc])

        if "error" in result:
            st.error(result["error"])
            return

        st.subheader("📊 版本差异对比报告")
        with st.container(border=True):
            st.markdown(result.get("comparison_report", "分析失败"))
