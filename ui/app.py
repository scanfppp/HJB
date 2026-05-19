"""
海军标准 RAG 智能体 — DeepSeek/豆包风格极简前端
"""

import sys, os, io, time, hashlib
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import streamlit.components.v1 as components

from config.settings import APP_TITLE, SUPPORTED_FORMATS
from config.prompts import RAG_QA_SYSTEM_PROMPT
from database.operations import (
    list_documents, get_document, insert_document, update_document, delete_document,
    insert_vectors_batch, get_recent_logs, log_query,
)
from document.parser import parse_file, save_uploaded_file
from document.cleaner import clean_text
from document.chunker import chunk_text
from document.metadata import extract_metadata_from_text, VALID_STATUSES
from embeddings.embedder import embed_texts
from retrieval.hybrid_search import hybrid_search
from retrieval.filter import build_search_filters, get_filter_options
from rag.qa_chain import rag_qa
from rag.summarizer import summarize_document
from rag.optimizer import optimize_text
from rag.gap_analyzer import analyze_gaps, compare_standards
from rag.compliance import check_compliance
from llm.client import chat_with_prompt
from utils.logger import get_logger

logger = get_logger(__name__)

# ==================== 页面配置 ====================
st.set_page_config(page_title=APP_TITLE, page_icon="⚓", layout="wide",
                   initial_sidebar_state="expanded")

# ==================== 自定义 CSS ====================
st.markdown("""
<style>
    /* 全局 */
    .stApp { background: #f8f9fb; }
    section[data-testid="stSidebar"] { background: #ffffff; border-right: 1px solid #e8eaed; }
    section[data-testid="stSidebar"] .stMarkdown h2 { font-size: 1.1rem; color: #1a1a2e; }

    /* 侧边栏按钮 */
    .stButton button {
        border-radius: 8px; border: none; background: #f1f3f6; color: #333;
        text-align: left; padding: 10px 14px; font-size: 0.9rem; transition: all 0.2s;
    }
    .stButton button:hover { background: #e3e8ef; }
    .stButton button[kind="primary"] { background: #165DFF; color: #fff; }
    .stButton button[kind="primary"]:hover { background: #0e42d6; }

    /* 聊天消息 */
    .chat-bubble { padding: 14px 18px; border-radius: 12px; margin: 8px 0; font-size: 0.95rem; line-height: 1.7; }
    .chat-user { background: #165DFF; color: #fff; margin-left: 60px; }
    .chat-assistant { background: #fff; border: 1px solid #e8eaed; margin-right: 60px; }

    /* 输入框 */
    .stChatInput input { border-radius: 12px !important; border: 1px solid #d0d5dd !important; padding: 12px 16px !important; }

    /* 侧边栏历史项 */
    .history-item {
        padding: 8px 12px; border-radius: 6px; cursor: pointer; font-size: 0.85rem;
        color: #555; margin: 2px 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    }
    .history-item:hover { background: #f1f3f6; }

    /* 功能面板 */
    .func-card {
        background: #fff; border-radius: 12px; padding: 20px; margin: 10px 0;
        border: 1px solid #e8eaed; box-shadow: 0 1px 3px rgba(0,0,0,0.04);
    }

    /* 提示卡片 */
    .suggest-card {
        background: #fff; border-radius: 10px; padding: 12px 16px; border: 1px solid #e8eaed;
        cursor: pointer; transition: all 0.2s; font-size: 0.88rem;
    }
    .suggest-card:hover { border-color: #165DFF; box-shadow: 0 2px 8px rgba(22,93,255,0.1); }

    /* 隐藏默认元素 */
    div[data-testid="stToolbar"] { display: none; }
    .stDeployButton { display: none; }
    #MainMenu { display: none; }
    footer { display: none; }

    /* 滚动条 */
    ::-webkit-scrollbar { width: 6px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb { background: #c1c5cd; border-radius: 3px; }
</style>
""", unsafe_allow_html=True)

# ==================== 会话初始化 ====================
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "messages" not in st.session_state:
    st.session_state.messages = []  # [{role, content, sources, type}]
if "side_mode" not in st.session_state:
    st.session_state.side_mode = "chat"  # chat | upload | optimize | gap | compliance
if "conversations" not in st.session_state:
    st.session_state.conversations = {}  # {id: {title, messages}}
if "current_conv" not in st.session_state:
    st.session_state.current_conv = None
if "pending_files" not in st.session_state:
    st.session_state.pending_files = []

# ==================== 侧边栏 ====================
def render_sidebar():
    with st.sidebar:
        # 顶部品牌
        st.markdown("<h2 style='margin-bottom:4px;'>⚓ 海军标准智能助手</h2>", unsafe_allow_html=True)
        st.caption("标准检索 · 智能问答 · 文本优化 · 查漏补缺")

        st.divider()

        # 新建对话
        if st.button("＋ 新建对话", use_container_width=True, key="new_chat"):
            _save_current_conversation()
            st.session_state.messages = []
            st.session_state.current_conv = None
            st.session_state.side_mode = "chat"
            st.rerun()

        st.divider()

        # 功能快捷入口
        st.caption("🔧 功能")
        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("📄 上传", use_container_width=True, key="btn_upload",
                         help="上传标准文档"):
                st.session_state.side_mode = "upload"
        with col_b:
            if st.button("✏️ 优化", use_container_width=True, key="btn_optimize",
                         help="公文文本优化"):
                st.session_state.side_mode = "optimize"

        col_c, col_d = st.columns(2)
        with col_c:
            if st.button("🔬 查漏", use_container_width=True, key="btn_gap",
                         help="标准查漏补缺"):
                st.session_state.side_mode = "gap"
        with col_d:
            if st.button("✅ 合规", use_container_width=True, key="btn_comply",
                         help="合规自查"):
                st.session_state.side_mode = "compliance"

        st.divider()

        # 历史对话
        st.caption("📜 历史对话")
        if st.session_state.conversations:
            convs = sorted(st.session_state.conversations.items(),
                          key=lambda x: x[1].get("time", ""), reverse=True)
            for cid, cdata in convs[:20]:
                title = cdata.get("title", "对话")[:25]
                if st.button(f"💬 {title}", key=f"hist_{cid}", use_container_width=True,
                            help=title):
                    _save_current_conversation()
                    st.session_state.messages = cdata["messages"]
                    st.session_state.current_conv = cid
                    st.rerun()

            if st.button("🗑️ 清空历史", use_container_width=True):
                st.session_state.conversations = {}
                st.session_state.messages = []
                st.session_state.current_conv = None
                st.rerun()
        else:
            st.caption("暂无历史对话")

        st.divider()

        # 底部数据库状态
        try:
            from database.connection import check_connection
            db_ok = check_connection()
            st.caption(f"{'🟢' if db_ok else '🔴'} 数据库{'已连接' if db_ok else '未连接'}")
        except Exception:
            st.caption("🟡 数据库状态未知")


def _save_current_conversation():
    if not st.session_state.messages:
        return
    cid = st.session_state.current_conv or hashlib.md5(str(time.time()).encode()).hexdigest()[:10]
    title = ""
    for m in st.session_state.messages:
        if m["role"] == "user":
            title = m["content"][:30]
            break
    st.session_state.conversations[cid] = {
        "title": title or "对话",
        "messages": st.session_state.messages.copy(),
        "time": time.strftime("%Y-%m-%d %H:%M"),
    }


# ==================== 主区域 ====================
def render_main():
    if st.session_state.side_mode == "upload":
        render_upload_panel()
    elif st.session_state.side_mode == "optimize":
        render_optimize_panel()
    elif st.session_state.side_mode == "gap":
        render_gap_panel()
    elif st.session_state.side_mode == "compliance":
        render_compliance_panel()
    else:
        render_chat_panel()


def render_chat_panel():
    """主对话界面"""
    # 欢迎页
    if not st.session_state.messages:
        st.markdown("<div style='height:60px;'></div>", unsafe_allow_html=True)
        st.markdown(
            "<h1 style='text-align:center;font-size:2rem;color:#1a1a2e;'>"
            "您好，我是海军标准智能助手 ⚓</h1>",
            unsafe_allow_html=True,
        )
        st.markdown(
            "<p style='text-align:center;color:#86909C;margin-bottom:40px;'>"
            "严格依托入库标准作答，杜绝编造，强制溯源</p>",
            unsafe_allow_html=True,
        )

        # 建议问题卡片
        st.markdown("<p style='text-align:center;color:#86909C;'>💡 试试问我</p>", unsafe_allow_html=True)
        suggestions = [
            ("🔍", "舰艇消防系统的设计要求和验收标准是什么？"),
            ("📋", "弹药库安全管理有哪些强制性规定？"),
            ("📝", "帮我总结一下已入库标准的主要内容"),
            ("🔬", "分析当前某标准是否存在内容缺口"),
        ]
        cols = st.columns(2)
        for i, (icon, text) in enumerate(suggestions):
            with cols[i % 2]:
                if st.button(f"{icon} {text}", key=f"suggest_{i}", use_container_width=True):
                    st.session_state.messages.append({"role": "user", "content": text})
                    st.rerun()

    # 消息列表
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg.get("sources"):
                with st.expander("📖 引用来源"):
                    for s in msg["sources"]:
                        st.caption(
                            f"[{s.get('standard_number','')}] {s.get('standard_name','')} "
                            f"> {s.get('section_title','')} {s.get('clause_number','')}"
                        )

    # 输入框
    prompt = st.chat_input("输入问题，按 Enter 发送...")
    if prompt:
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("思考中..."):
                response, sources = rag_qa(
                    question=prompt,
                    chat_history=[m for m in st.session_state.messages[:-1]
                                  if m["role"] in ("user", "assistant")],
                    top_k=10,
                )
            st.markdown(response)
            if sources:
                with st.expander(f"📖 引用来源 ({len(sources)}条)"):
                    for s in sources:
                        st.caption(
                            f"[{s['standard_number']}] {s['standard_name']} "
                            f"> {s['section_title']} {s['clause_number']} "
                            f"({s['chunk_type']})"
                        )

        st.session_state.messages.append({
            "role": "assistant", "content": response, "sources": sources,
        })
        _save_current_conversation()
        st.rerun()


def render_upload_panel():
    """文档上传面板"""
    st.markdown("## 📄 上传标准文档")
    st.caption("支持 PDF、DOCX、TXT 格式，系统自动解析、清洗、分块、入库")

    with st.container(border=True):
        uploaded_files = st.file_uploader(
            "选择文件", type=SUPPORTED_FORMATS, accept_multiple_files=True,
            label_visibility="collapsed",
        )

        if uploaded_files:
            for f in uploaded_files:
                if f.name not in [pf["name"] for pf in st.session_state.pending_files]:
                    with st.spinner(f"解析 {f.name}..."):
                        try:
                            file_path = save_uploaded_file(f)
                            raw = parse_file(file_path)
                            cleaned = clean_text(raw)
                            meta = extract_metadata_from_text(cleaned, f.name)
                            st.session_state.pending_files.append({
                                "name": f.name, "path": file_path,
                                "cleaned": cleaned, "meta": meta,
                                "type": f.name.rsplit(".", 1)[-1],
                            })
                        except Exception as e:
                            st.error(f"解析失败: {f.name} - {e}")

    # 待入库文件列表
    if st.session_state.pending_files:
        st.subheader("待入库文件")
        for i, pf in enumerate(st.session_state.pending_files):
            with st.container(border=True):
                c1, c2 = st.columns([3, 1])
                with c1:
                    st.markdown(f"**{pf['name']}**")
                    m = pf["meta"]
                    st.caption(f"标准编号: {m.get('standard_number','未识别')} | 名称: {m.get('standard_name','未识别')}")

                    # 快速编辑元数据
                    with st.expander("编辑元数据"):
                        m["standard_number"] = st.text_input("标准编号", m.get("standard_number", ""), key=f"sn_{i}")
                        m["standard_name"] = st.text_input("标准名称", m.get("standard_name", ""), key=f"sn2_{i}")
                        m["doc_status"] = st.selectbox("状态", VALID_STATUSES,
                                                        index=VALID_STATUSES.index(m.get("doc_status", "现行有效"))
                                                        if m.get("doc_status") in VALID_STATUSES else 0,
                                                        key=f"st_{i}")
                        m["applicable_field"] = st.text_input("适用领域", m.get("applicable_field", ""), key=f"af_{i}")
                        m["responsible_unit"] = st.text_input("归口单位", m.get("responsible_unit", ""), key=f"ru_{i}")
                with c2:
                    if st.button("✅ 入库", key=f"ingest_{i}", type="primary"):
                        _do_ingest(pf)
                        st.session_state.pending_files.pop(i)
                        st.rerun()
                    if st.button("🗑️ 移除", key=f"remove_{i}"):
                        st.session_state.pending_files.pop(i)
                        st.rerun()

    # 已入库文档
    st.divider()
    st.subheader("已入库文档")
    docs = list_documents(limit=30)
    if not docs:
        st.info("暂无已入库文档")
    else:
        for doc in docs:
            status_icon = {"现行有效": "🟢", "修订中": "🟡", "废止": "🔴"}.get(doc.get("doc_status", ""), "⚪")
            st.caption(
                f"{status_icon} [{doc.get('standard_number','')}] {doc.get('standard_name','')} "
                f"({doc.get('doc_status','')}) | ID:{doc['id']}"
            )

    if st.button("← 返回对话", use_container_width=True):
        st.session_state.side_mode = "chat"
        st.rerun()


def _do_ingest(pf):
    try:
        doc_id = insert_document(
            standard_number=pf["meta"].get("standard_number", ""),
            standard_name=pf["meta"].get("standard_name", pf["name"]),
            applicable_field=pf["meta"].get("applicable_field", ""),
            doc_status=pf["meta"].get("doc_status", "现行有效"),
            responsible_unit=pf["meta"].get("responsible_unit", ""),
            file_path=pf["path"], file_type=pf["type"],
        )
        chunks_data = chunk_text(pf["cleaned"])
        if chunks_data:
            texts = [c["chunk_text"] for c in chunks_data]
            embs = embed_texts(texts)
            vectors = []
            for j, (c, e) in enumerate(zip(chunks_data, embs)):
                vectors.append({
                    "document_id": doc_id, "chunk_text": c["chunk_text"],
                    "chunk_index": j, "section_title": c.get("section_title", ""),
                    "clause_number": c.get("clause_number", ""),
                    "chunk_type": c.get("chunk_type", "指导性说明"),
                    "embedding": e, "metadata": {},
                })
            insert_vectors_batch(vectors)
        st.success(f"入库成功: ID={doc_id}, {len(chunks_data)}个块")
    except Exception as e:
        st.error(f"入库失败: {e}")


def render_optimize_panel():
    """文本优化面板"""
    st.markdown("## ✏️ 海军公文文本优化")
    st.caption("去口语化 · 理顺逻辑 · 统一术语 · 规整格式")

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**原文输入**")
        original = st.text_area("原文", height=400, label_visibility="collapsed",
                                placeholder="粘贴需要优化的方案、报告、条款...",
                                key="opt_input")
    with c2:
        st.markdown("**优化结果**")
        if st.button("✨ 开始优化", type="primary", use_container_width=True) and original.strip():
            with st.spinner("优化中..."):
                result = optimize_text(original)
            if result.get("optimized"):
                st.success(result.get("changes_summary", "优化完成"))
                st.markdown(result["optimized"])
                st.download_button("📥 下载", result["optimized"],
                                   file_name="优化文本.txt", mime="text/plain")

    if st.button("← 返回对话", use_container_width=True):
        st.session_state.side_mode = "chat"
        st.rerun()


def render_gap_panel():
    """查漏补缺面板"""
    st.markdown("## 🔬 标准查漏补缺")
    st.caption("自动检索关联标准，识别内容缺口，给出增补建议")

    docs = list_documents(is_active=True, limit=100)
    if not docs:
        st.info("暂无已入库文档")
        return

    doc_map = {f"[{d.get('standard_number','')}] {d.get('standard_name','')} (ID:{d['id']})": d["id"] for d in docs}

    c1, c2 = st.columns([3, 1])
    with c1:
        selected = st.selectbox("选择目标标准", list(doc_map.keys()), label_visibility="collapsed")
    with c2:
        if st.button("🔬 开始分析", type="primary", use_container_width=True):
            with st.spinner("分析中..."):
                result = analyze_gaps(doc_map[selected])
            if result.get("related_standards"):
                st.subheader("📎 关联标准")
                for rs in result["related_standards"]:
                    st.markdown(f"- [{rs['standard_number']}] {rs['standard_name']}")
            st.subheader("📊 分析报告")
            st.markdown(result.get("gap_report", "分析失败"))

    if st.button("← 返回对话", use_container_width=True):
        st.session_state.side_mode = "chat"
        st.rerun()


def render_compliance_panel():
    """合规自查面板"""
    st.markdown("## ✅ 标准合规自查")
    st.caption("提交制度/方案，对照现行标准逐条校验")

    c1, c2 = st.columns(2)
    with c1:
        submitted = st.text_area("制度/方案内容", height=400, label_visibility="collapsed",
                                 placeholder="粘贴需要校验的制度、方案、操作规程...",
                                 key="comply_input")
    with c2:
        if st.button("✅ 开始校验", type="primary", use_container_width=True) and submitted.strip():
            with st.spinner("校验中..."):
                result = check_compliance(submitted)
            st.markdown(result.get("report", "校验失败"))
            if result.get("sources"):
                with st.expander("📖 引用标准"):
                    for s in result["sources"]:
                        st.caption(f"[{s['standard_number']}] {s['standard_name']}")

    if st.button("← 返回对话", use_container_width=True):
        st.session_state.side_mode = "chat"
        st.rerun()


# ==================== 主入口 ====================
render_sidebar()
render_main()
