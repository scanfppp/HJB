"""
数据库 CRUD 操作封装
涵盖文档管理、向量操作、查询日志、用户管理
"""

import json
from datetime import date, datetime
from typing import Optional

import psycopg2
from psycopg2.extras import Json

from database.connection import execute_query, get_connection, release_connection
from config.settings import VECTOR_TABLE
from utils.logger import get_logger

logger = get_logger(__name__)


# ============================================================
# 文档元数据操作
# ============================================================

def insert_document(
    standard_number: str = "",
    standard_name: str = "",
    applicable_field: str = "",
    publish_date: Optional[date] = None,
    implement_date: Optional[date] = None,
    doc_status: str = "现行有效",
    responsible_unit: str = "",
    file_path: str = "",
    file_type: str = "",
) -> int:
    """插入文档元数据，返回文档ID"""
    sql = """
        INSERT INTO documents
            (standard_number, standard_name, applicable_field,
             publish_date, implement_date, doc_status, responsible_unit,
             file_path, file_type)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """
    result = execute_query(sql, (
        standard_number, standard_name, applicable_field,
        publish_date, implement_date, doc_status, responsible_unit,
        file_path, file_type,
    ))
    doc_id = result[0][0]
    logger.info(f"文档已入库: ID={doc_id}, 名称={standard_name}")
    return doc_id


def update_document(doc_id: int, **kwargs) -> bool:
    """更新文档元数据"""
    allowed = [
        "standard_number", "standard_name", "applicable_field",
        "publish_date", "implement_date", "doc_status",
        "responsible_unit", "is_active"
    ]
    sets = []
    values = []
    for k, v in kwargs.items():
        if k in allowed:
            sets.append(f"{k} = %s")
            values.append(v)
    if not sets:
        return False
    values.append(doc_id)
    sql = f"UPDATE documents SET {', '.join(sets)} WHERE id = %s"
    execute_query(sql, tuple(values), fetch=False)
    logger.info(f"文档 {doc_id} 已更新: {list(kwargs.keys())}")
    return True


def get_document(doc_id: int) -> Optional[dict]:
    """获取单个文档信息"""
    sql = "SELECT * FROM documents WHERE id = %s"
    result = execute_query(sql, (doc_id,))
    if not result:
        return None
    return _row_to_dict(result[0], [
        "id", "standard_number", "standard_name", "applicable_field",
        "publish_date", "implement_date", "doc_status", "responsible_unit",
        "file_path", "file_type", "upload_time", "is_active"
    ])


def list_documents(
    doc_status: str = None,
    applicable_field: str = None,
    keyword: str = None,
    is_active: bool = None,
    limit: int = 100,
    offset: int = 0,
) -> list:
    """列表查询文档"""
    conditions = []
    params = []

    if doc_status:
        conditions.append("doc_status = %s")
        params.append(doc_status)
    if applicable_field:
        conditions.append("applicable_field = %s")
        params.append(applicable_field)
    if keyword:
        conditions.append("(standard_name ILIKE %s OR standard_number ILIKE %s)")
        params.extend([f"%{keyword}%", f"%{keyword}%"])
    if is_active is not None:
        conditions.append("is_active = %s")
        params.append(is_active)

    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    sql = f"SELECT * FROM documents{where} ORDER BY upload_time DESC LIMIT %s OFFSET %s"
    params.extend([limit, offset])

    rows = execute_query(sql, tuple(params))
    keys = [
        "id", "standard_number", "standard_name", "applicable_field",
        "publish_date", "implement_date", "doc_status", "responsible_unit",
        "file_path", "file_type", "upload_time", "is_active"
    ]
    return [_row_to_dict(r, keys) for r in rows]


def delete_document(doc_id: int) -> bool:
    """删除文档及其所有向量块"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(f"DELETE FROM {VECTOR_TABLE} WHERE document_id = %s", (doc_id,))
            cur.execute("DELETE FROM documents WHERE id = %s", (doc_id,))
            conn.commit()
        logger.info(f"文档 {doc_id} 及其向量块已删除")
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        release_connection(conn)


def get_distinct_fields() -> list:
    """获取所有不重复的适用领域"""
    result = execute_query("SELECT DISTINCT applicable_field FROM documents WHERE applicable_field != ''")
    return [r[0] for r in result]


def get_document_count_by_status() -> dict:
    """按状态统计文档数量"""
    result = execute_query(
        "SELECT doc_status, COUNT(*) FROM documents GROUP BY doc_status"
    )
    return {r[0]: r[1] for r in result}


# ============================================================
# 向量块操作
# ============================================================

def insert_vectors_batch(vectors_data: list) -> int:
    """批量插入向量块"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            inserted = 0
            for item in vectors_data:
                embedding_str = f"[{','.join(str(v) for v in item['embedding'])}]"
                sql = f"""
                    INSERT INTO {VECTOR_TABLE}
                        (document_id, chunk_text, chunk_index, section_title,
                         clause_number, chunk_type, embedding, metadata)
                    VALUES (%s, %s, %s, %s, %s, %s, %s::vector, %s)
                """
                cur.execute(sql, (
                    item["document_id"],
                    item["chunk_text"],
                    item["chunk_index"],
                    item.get("section_title", ""),
                    item.get("clause_number", ""),
                    item.get("chunk_type", "指导性说明"),
                    embedding_str,
                    Json(item.get("metadata", {})),
                ))
                inserted += 1
            conn.commit()
        logger.info(f"批量插入 {inserted} 个向量块")
        return inserted
    except Exception as e:
        conn.rollback()
        logger.error(f"向量入库失败: {e}")
        raise
    finally:
        release_connection(conn)


def delete_vectors_by_document(doc_id: int) -> int:
    """删除指定文档的所有向量块"""
    sql = f"DELETE FROM {VECTOR_TABLE} WHERE document_id = %s"
    execute_query(sql, (doc_id,), fetch=False)
    return 0


def get_chunks_by_document(doc_id: int) -> list:
    """获取文档的所有分块"""
    sql = f"""
        SELECT id, chunk_text, chunk_index, section_title, clause_number, chunk_type, metadata
        FROM {VECTOR_TABLE}
        WHERE document_id = %s
        ORDER BY chunk_index
    """
    rows = execute_query(sql, (doc_id,))
    keys = ["id", "chunk_text", "chunk_index", "section_title", "clause_number", "chunk_type", "metadata"]
    return [_row_to_dict(r, keys) for r in rows]


# ============================================================
# 语义向量检索
# ============================================================

def vector_search(embedding: list, top_k: int = 10, filters: dict = None) -> list:
    """向量相似度检索"""
    embedding_str = f"[{','.join(str(v) for v in embedding)}]"

    conditions = []
    params = []

    if filters:
        if filters.get("doc_status"):
            conditions.append("d.doc_status = %s")
            params.append(filters["doc_status"])
        if filters.get("applicable_field"):
            conditions.append("d.applicable_field = %s")
            params.append(filters["applicable_field"])
        if filters.get("standard_number"):
            conditions.append("d.standard_number = %s")
            params.append(filters["standard_number"])
        if filters.get("doc_ids"):
            placeholders = ",".join(["%s"] * len(filters["doc_ids"]))
            conditions.append(f"v.document_id IN ({placeholders})")
            params.extend(filters["doc_ids"])

    where = " AND " + " AND ".join(conditions) if conditions else ""
    if where:
        where = " AND " + where

    params.extend([embedding_str, embedding_str, top_k])

    sql = f"""
        SELECT
            v.id, v.document_id, v.chunk_text, v.chunk_index,
            v.section_title, v.clause_number, v.chunk_type,
            1 - (v.embedding <=> %s::vector) AS similarity,
            d.standard_number, d.standard_name, d.doc_status,
            d.applicable_field, d.responsible_unit
        FROM {VECTOR_TABLE} v
        JOIN documents d ON v.document_id = d.id
        WHERE d.is_active = TRUE{where}
        ORDER BY v.embedding <=> %s::vector
        LIMIT %s
    """

    rows = execute_query(sql, tuple(params))
    keys = [
        "id", "document_id", "chunk_text", "chunk_index",
        "section_title", "clause_number", "chunk_type", "similarity",
        "standard_number", "standard_name", "doc_status",
        "applicable_field", "responsible_unit"
    ]
    return [_row_to_dict(r, keys) for r in rows]


# ============================================================
# 关键词全文检索
# ============================================================

def keyword_search(keywords: str, top_k: int = 10, filters: dict = None) -> list:
    """基于中文分词的全文关键词检索"""
    conditions = ["d.is_active = TRUE"]
    params = []

    if keywords.strip():
        # 使用 ILIKE 进行模糊匹配（支持中文）
        like_pattern = f"%{keywords.strip()}%"
        conditions.append("(v.chunk_text ILIKE %s OR d.standard_name ILIKE %s OR d.standard_number ILIKE %s)")
        params.extend([like_pattern, like_pattern, like_pattern])

    if filters:
        if filters.get("doc_status"):
            conditions.append("d.doc_status = %s")
            params.append(filters["doc_status"])
        if filters.get("applicable_field"):
            conditions.append("d.applicable_field = %s")
            params.append(filters["applicable_field"])
        if filters.get("standard_number"):
            conditions.append("d.standard_number = %s")
            params.append(filters["standard_number"])

    params.extend([top_k])

    where = " AND ".join(conditions)
    sql = f"""
        SELECT
            v.id, v.document_id, v.chunk_text, v.chunk_index,
            v.section_title, v.clause_number, v.chunk_type,
            0.5 AS similarity,
            d.standard_number, d.standard_name, d.doc_status,
            d.applicable_field, d.responsible_unit
        FROM {VECTOR_TABLE} v
        JOIN documents d ON v.document_id = d.id
        WHERE {where}
        LIMIT %s
    """

    rows = execute_query(sql, tuple(params))
    keys = [
        "id", "document_id", "chunk_text", "chunk_index",
        "section_title", "clause_number", "chunk_type", "similarity",
        "standard_number", "standard_name", "doc_status",
        "applicable_field", "responsible_unit"
    ]
    return [_row_to_dict(r, keys) for r in rows]


# ============================================================
# 查询日志
# ============================================================

def log_query(username: str, query_text: str, response_text: str,
              query_type: str, sources: list = None):
    """记录查询日志"""
    sql = """
        INSERT INTO query_logs (username, query_text, response_text, query_type, sources)
        VALUES (%s, %s, %s, %s, %s)
    """
    execute_query(sql, (
        username, query_text, response_text, query_type,
        Json(sources or []),
    ), fetch=False)


def get_recent_logs(limit: int = 50) -> list:
    """获取最近查询日志"""
    sql = """
        SELECT * FROM query_logs ORDER BY timestamp DESC LIMIT %s
    """
    rows = execute_query(sql, (limit,))
    keys = ["id", "username", "query_text", "response_text", "query_type", "sources", "timestamp"]
    return [_row_to_dict(r, keys) for r in rows]


# ============================================================
# 用户管理
# ============================================================

def verify_user(username: str, password_hash: str) -> Optional[dict]:
    """验证用户登录"""
    sql = "SELECT id, username, role FROM users WHERE username = %s AND password_hash = %s"
    result = execute_query(sql, (username, password_hash))
    if not result:
        return None
    return {"id": result[0][0], "username": result[0][1], "role": result[0][2]}


def create_user(username: str, password_hash: str, role: str = "user") -> int:
    """创建新用户"""
    sql = "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, %s) RETURNING id"
    result = execute_query(sql, (username, password_hash, role))
    return result[0][0]


# ============================================================
# 工具函数
# ============================================================

def _row_to_dict(row: tuple, keys: list) -> dict:
    """将数据库行转换为字典"""
    result = {}
    for i, key in enumerate(keys):
        if i < len(row):
            val = row[i]
            if isinstance(val, (date, datetime)):
                val = str(val)
            elif isinstance(val, str) and (val.startswith('{') or val.startswith('[')):
                try:
                    val = json.loads(val)
                except (json.JSONDecodeError, TypeError):
                    pass
            result[key] = val
    return result
