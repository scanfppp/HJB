"""
智能检索区 — 混合检索 + 多维度筛选 + 结果展示
"""

import streamlit as st

from retrieval.hybrid_search import hybrid_search
from retrieval.filter import build_search_filters, get_filter_options
from utils.logger import get_logger

logger = get_logger(__name__)


def render_search_tab():
    with st.container(border=True):
        c1, c2, c3 = st.columns([4, 1, 1])
        with c1:
            query = st.text_input(
                "检索关键词或问题",
                placeholder="例如：舰艇消防系统设计要求、弹药库安全管理规定...",
                label_visibility="collapsed",
            )
        with c2:
            filter_options = get_filter_options()
            doc_status = st.selectbox("状态", filter_options["statuses"], label_visibility="collapsed")
        with c3:
            applicable_field = st.selectbox(
                "领域", ["全部"] + filter_options["fields"], label_visibility="collapsed"
            )

        if st.button("🔍 开始检索", type="primary", use_container_width=True) and query:
            _perform_search(query, doc_status, applicable_field)


def _perform_search(query, doc_status, applicable_field):
    with st.spinner("正在检索..."):
        filters = build_search_filters(
            doc_status=doc_status if doc_status != "全部" else None,
            applicable_field=applicable_field if applicable_field != "全部" else None,
        )
        results = hybrid_search(query=query, top_k=10, filters=filters)

    if not results:
        st.info("📭 未检索到相关内容，请尝试调整检索词或筛选条件")
        return

    st.success(f"共检索到 {len(results)} 条相关结果")

    for i, r in enumerate(results):
        with st.container(border=True):
            c1, c2 = st.columns([4, 1])

            with c1:
                status_color = {"现行有效": "green", "修订中": "orange", "废止": "red"}.get(
                    r.get("doc_status", ""), "gray"
                )
                st.markdown(
                    f"### [{r.get('standard_number', 'N/A')}] {r.get('standard_name', 'N/A')} "
                    f":{status_color}[{r.get('doc_status', '')}]",
                )
                st.caption(
                    f"📍 {r.get('section_title', '')} {r.get('clause_number', '')} "
                    f"| 📌 {r.get('chunk_type', '')} "
                    f"| 🏢 {r.get('responsible_unit', '')}"
                )
                with st.expander("查看内容", expanded=(i == 0)):
                    st.text(r.get("chunk_text", ""))

            with c2:
                st.metric("相似度", f"{r.get('similarity', 0):.1%}")
