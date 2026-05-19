"""
智能问答对话区 — RAG问答 + 多轮对话 + 引用来源
"""

import streamlit as st

from rag.qa_chain import rag_qa
from retrieval.filter import build_search_filters, get_filter_options
from database.operations import get_recent_logs
from utils.logger import get_logger

logger = get_logger(__name__)


def render_qa_tab():
    col_main, col_side = st.columns([3, 1])

    with col_side:
        with st.container(border=True):
            st.subheader("🎯 检索设置")
            filter_options = get_filter_options()
            doc_status = st.selectbox("文档状态", filter_options["statuses"])
            applicable_field = st.selectbox("适用领域", ["全部"] + filter_options["fields"])
            top_k = st.slider("检索数量", 3, 20, 10)

            if st.button("🗑️ 清空对话", use_container_width=True):
                st.session_state.chat_history = []
                st.rerun()

        with st.container(border=True):
            st.subheader("📜 最近查询")
            logs = get_recent_logs(10)
            if logs:
                for log in logs[:10]:
                    st.caption(f"[{str(log.get('timestamp', ''))[5:16]}] {log.get('query_text', '')[:30]}...")
            else:
                st.caption("暂无查询记录")

    with col_main:
        with st.container(border=True):
            st.subheader("💬 海军标准智能问答")
            st.caption("严格依托入库标准作答，强制标注引用来源")

            for msg in st.session_state.chat_history:
                if msg["role"] == "user":
                    with st.chat_message("user"):
                        st.markdown(msg["content"])
                else:
                    with st.chat_message("assistant"):
                        st.markdown(msg["content"])
                        if msg.get("sources"):
                            with st.expander("📖 引用来源"):
                                for s in msg["sources"]:
                                    st.markdown(
                                        f"- **[{s['standard_number']}]** {s['standard_name']} "
                                        f"> {s['section_title']} {s['clause_number']} "
                                        f"({s['chunk_type']}, {s.get('similarity', 0):.2f})"
                                    )

            question = st.chat_input("请输入问题，我将严格依托入库标准作答...")

            if question:
                st.session_state.chat_history.append({"role": "user", "content": question})

                with st.chat_message("user"):
                    st.markdown(question)

                with st.chat_message("assistant"):
                    with st.spinner("正在检索相关标准..."):
                        filters = build_search_filters(
                            doc_status=doc_status if doc_status != "全部" else None,
                            applicable_field=applicable_field if applicable_field != "全部" else None,
                        )
                        response, sources = rag_qa(
                            question=question,
                            chat_history=st.session_state.chat_history[:-1],
                            filters=filters,
                            top_k=top_k,
                            username=st.session_state.user.get("username", ""),
                        )

                    st.markdown(response)
                    if sources:
                        with st.expander(f"📖 引用来源 ({len(sources)}条)"):
                            for s in sources:
                                st.markdown(
                                    f"**[{s['standard_number']}]** {s['standard_name']}  \n"
                                    f"> {s['section_title']} {s['clause_number']} | "
                                    f"{s['chunk_type']} | {s.get('similarity', 0):.2f}"
                                )
                                st.divider()

                st.session_state.chat_history.append({
                    "role": "assistant", "content": response, "sources": sources,
                })
                st.rerun()
