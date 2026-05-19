"""
文档管理区 — 上传、解析、入库、编辑、状态管理
"""

import streamlit as st
import pandas as pd

from document.parser import parse_file, save_uploaded_file, get_file_info
from document.cleaner import clean_text
from document.chunker import chunk_text
from document.metadata import extract_metadata_from_text, VALID_STATUSES
from embeddings.embedder import embed_texts
from database.operations import (
    insert_document, update_document, list_documents,
    delete_document, insert_vectors_batch,
    get_document,
)
from config.settings import SUPPORTED_FORMATS
from utils.logger import get_logger

logger = get_logger(__name__)


def render_document_tab():
    col_left, col_right = st.columns([1, 1], gap="large")

    with col_left:
        with st.container(border=True):
            st.subheader("📤 文档上传")
            st.caption(f"支持格式: {', '.join(SUPPORTED_FORMATS).upper()} | 单文件最大 200MB")

            uploaded_files = st.file_uploader(
                "选择文件",
                type=SUPPORTED_FORMATS,
                accept_multiple_files=True,
                label_visibility="collapsed",
            )

            if uploaded_files:
                if st.button("🚀 解析并入库", type="primary", use_container_width=True):
                    for f in uploaded_files:
                        _process_and_ingest(f)

    with col_right:
        with st.container(border=True):
            st.subheader("📑 元数据确认与入库")
            _render_metadata_panel()

    st.divider()

    with st.container(border=True):
        st.subheader("🗂️ 已入库文档")
        _render_document_list()


def _render_metadata_panel():
    pending_keys = [k for k in st.session_state.keys() if k.startswith("pending_metadata_")]
    if not pending_keys:
        st.info("📭 请先上传文档进行解析")
        return

    file_names = [k.replace("pending_metadata_", "") for k in pending_keys]
    selected_file = st.selectbox("待入库文件", file_names, label_visibility="collapsed")

    meta_key = f"pending_metadata_{selected_file}"
    file_key = f"pending_file_{selected_file}"

    if meta_key not in st.session_state:
        return

    metadata = st.session_state[meta_key]

    with st.form(f"meta_form_{selected_file[:10]}"):
        standard_number = st.text_input("标准编号 *", value=metadata.get("standard_number", ""))
        standard_name = st.text_input("标准名称 *", value=metadata.get("standard_name", ""))
        applicable_field = st.text_input("适用领域", value=metadata.get("applicable_field", ""))

        status_index = 0
        if metadata.get("doc_status") in VALID_STATUSES:
            status_index = VALID_STATUSES.index(metadata["doc_status"])
        doc_status = st.selectbox("文档状态 *", VALID_STATUSES, index=status_index)

        responsible_unit = st.text_input("归口单位", value=metadata.get("responsible_unit", ""))

        c1, c2 = st.columns(2)
        with c1:
            publish_date = st.date_input("发布时间", value=metadata.get("publish_date"))
        with c2:
            implement_date = st.date_input("实施时间", value=metadata.get("implement_date"))

        if st.form_submit_button("✅ 确认入库", type="primary", use_container_width=True):
            if not standard_name.strip():
                st.error("标准名称为必填项")
                return

            try:
                file_data = st.session_state[file_key]

                doc_id = insert_document(
                    standard_number=standard_number,
                    standard_name=standard_name,
                    applicable_field=applicable_field,
                    publish_date=publish_date if publish_date else None,
                    implement_date=implement_date if implement_date else None,
                    doc_status=doc_status,
                    responsible_unit=responsible_unit,
                    file_path=file_data["file_path"],
                    file_type=file_data["file_type"],
                )

                chunks = chunk_text(file_data["cleaned_text"])
                if chunks:
                    chunk_texts = [c["chunk_text"] for c in chunks]
                    embeddings = embed_texts(chunk_texts)

                    vectors_data = []
                    for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
                        vectors_data.append({
                            "document_id": doc_id,
                            "chunk_text": chunk["chunk_text"],
                            "chunk_index": i,
                            "section_title": chunk.get("section_title", ""),
                            "clause_number": chunk.get("clause_number", ""),
                            "chunk_type": chunk.get("chunk_type", "指导性说明"),
                            "embedding": emb,
                            "metadata": {},
                        })
                    insert_vectors_batch(vectors_data)

                del st.session_state[meta_key]
                del st.session_state[file_key]

                st.success(f"✅ 入库完成！文档ID: {doc_id}, 共{len(chunks)}个向量块")
                st.rerun()

            except Exception as e:
                st.error(f"入库失败: {e}")


def _process_and_ingest(uploaded_file):
    try:
        with st.spinner(f"正在保存: {uploaded_file.name}..."):
            file_path = save_uploaded_file(uploaded_file)
            file_info = get_file_info(file_path)

        with st.spinner("正在解析文档..."):
            raw_text = parse_file(file_path)

        with st.spinner("正在清洗文本..."):
            cleaned_text = clean_text(raw_text)

        with st.spinner("正在提取元数据..."):
            metadata = extract_metadata_from_text(cleaned_text, uploaded_file.name)

        st.session_state[f"pending_metadata_{uploaded_file.name}"] = metadata
        st.session_state[f"pending_file_{uploaded_file.name}"] = {
            "file_path": file_path,
            "cleaned_text": cleaned_text,
            "file_type": file_info["file_type"],
        }
        st.success(f"✅ {uploaded_file.name} 解析完成，请在右侧确认元数据")

    except Exception as e:
        st.error(f"❌ 处理失败: {uploaded_file.name} - {e}")


def _render_document_list():
    c1, c2 = st.columns([3, 1])
    with c2:
        status_filter = st.selectbox("状态筛选", ["全部", "现行有效", "修订中", "废止"], label_visibility="collapsed")

    status_arg = None if status_filter == "全部" else status_filter
    docs = list_documents(doc_status=status_arg, limit=50)

    if not docs:
        st.info("📭 暂无已入库的文档，请上传标准文档")
        return

    table_data = []
    for doc in docs:
        table_data.append({
            "ID": doc["id"],
            "标准编号": doc.get("standard_number", ""),
            "标准名称": doc.get("standard_name", ""),
            "领域": doc.get("applicable_field", ""),
            "状态": doc.get("doc_status", ""),
            "上传时间": str(doc.get("upload_time", ""))[:10],
            "启用": "✅" if doc.get("is_active") else "❌",
        })

    st.dataframe(pd.DataFrame(table_data), use_container_width=True, hide_index=True, height=300)

    with st.expander("⚙️ 文档操作"):
        col_a, col_b, col_c = st.columns([1, 1, 2])
        with col_a:
            doc_id = st.number_input("文档ID", min_value=1, step=1)
        with col_b:
            action = st.selectbox("操作", ["查看详情", "修改状态", "标记下架", "删除文档"])
        with col_c:
            if st.button("执行", use_container_width=True):
                _handle_document_action(doc_id, action)


def _handle_document_action(doc_id, action):
    if action == "查看详情":
        doc = get_document(doc_id)
        if doc:
            st.json({k: str(v) for k, v in doc.items()})
        else:
            st.error("文档不存在")

    elif action == "修改状态":
        new_status = st.selectbox("新状态", VALID_STATUSES, key="change_status_popup")
        if st.button("确认修改"):
            update_document(doc_id, doc_status=new_status)
            st.success("状态已更新")
            st.rerun()

    elif action == "标记下架":
        doc = get_document(doc_id)
        if doc:
            new_active = not doc.get("is_active", True)
            update_document(doc_id, is_active=new_active)
            st.success("已下架" if not new_active else "已重新上架")
            st.rerun()

    elif action == "删除文档":
        if st.button("⚠️ 确认删除（不可撤销）", type="secondary"):
            delete_document(doc_id)
            st.success("文档已删除")
            st.rerun()
