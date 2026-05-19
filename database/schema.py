"""
数据库Schema初始化 — 建表、建索引、启用pgvector扩展
执行一次即可完成全部表结构和索引创建
"""

from database.connection import get_connection, release_connection
from config.settings import VECTOR_DIMENSIONS, VECTOR_TABLE, INDEX_TYPE
from utils.logger import get_logger

logger = get_logger(__name__)

CREATE_TABLES_SQL = [
    # 启用 pgvector 扩展
    """
    CREATE EXTENSION IF NOT EXISTS vector;
    """,

    # 文档元数据表
    f"""
    CREATE TABLE IF NOT EXISTS documents (
        id SERIAL PRIMARY KEY,
        standard_number VARCHAR(100) DEFAULT '',
        standard_name VARCHAR(500) DEFAULT '',
        applicable_field VARCHAR(200) DEFAULT '',
        publish_date DATE,
        implement_date DATE,
        doc_status VARCHAR(20) DEFAULT '现行有效',
        responsible_unit VARCHAR(200) DEFAULT '',
        file_path VARCHAR(500) DEFAULT '',
        file_type VARCHAR(10) DEFAULT '',
        upload_time TIMESTAMP DEFAULT NOW(),
        is_active BOOLEAN DEFAULT TRUE
    );
    """,

    # 向量存储表
    f"""
    CREATE TABLE IF NOT EXISTS {VECTOR_TABLE} (
        id SERIAL PRIMARY KEY,
        document_id INTEGER REFERENCES documents(id) ON DELETE CASCADE,
        chunk_text TEXT NOT NULL,
        chunk_index INTEGER DEFAULT 0,
        section_title VARCHAR(300) DEFAULT '',
        clause_number VARCHAR(100) DEFAULT '',
        chunk_type VARCHAR(50) DEFAULT '指导性说明',
        embedding vector({VECTOR_DIMENSIONS}),
        metadata JSONB DEFAULT '{{}}'
    );
    """,

    # 查询日志表
    """
    CREATE TABLE IF NOT EXISTS query_logs (
        id SERIAL PRIMARY KEY,
        username VARCHAR(50) DEFAULT '',
        query_text TEXT DEFAULT '',
        response_text TEXT DEFAULT '',
        query_type VARCHAR(50) DEFAULT '',
        sources JSONB DEFAULT '[]',
        timestamp TIMESTAMP DEFAULT NOW()
    );
    """,

    # 用户表
    """
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        username VARCHAR(50) UNIQUE NOT NULL,
        password_hash VARCHAR(200) NOT NULL,
        role VARCHAR(20) DEFAULT 'user',
        created_at TIMESTAMP DEFAULT NOW()
    );
    """,
]

CREATE_INDEXES_SQL = [
    f"""
    CREATE INDEX IF NOT EXISTS idx_vector_embedding
    ON {VECTOR_TABLE}
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 200);
    """,

    "CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(doc_status);",
    "CREATE INDEX IF NOT EXISTS idx_documents_field ON documents(applicable_field);",
    "CREATE INDEX IF NOT EXISTS idx_documents_number ON documents(standard_number);",
    "CREATE INDEX IF NOT EXISTS idx_vector_doc_id ON vector_st(document_id);",
    "CREATE INDEX IF NOT EXISTS idx_query_logs_time ON query_logs(timestamp DESC);",
    "CREATE INDEX IF NOT EXISTS idx_query_logs_type ON query_logs(query_type);",
]


def init_db():
    """初始化数据库：建表 + 建索引 + 创建默认用户"""
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()

        # 执行建表语句
        for sql in CREATE_TABLES_SQL:
            try:
                cur.execute(sql)
                logger.info(f"执行建表/扩展: {sql[:60].strip()}...")
            except Exception as e:
                logger.warning(f"建表语句警告 (可能已存在): {e}")
                conn.rollback()

        conn.commit()
        logger.info("所有表创建完成")

        # 执行建索引语句
        for sql in CREATE_INDEXES_SQL:
            try:
                cur.execute(sql)
                logger.info(f"创建索引: {sql[:60].strip()}...")
            except Exception as e:
                logger.warning(f"索引创建警告: {e}")
                conn.rollback()

        conn.commit()
        logger.info("所有索引创建完成")

        # 创建默认用户
        _create_default_user(cur)
        conn.commit()

        logger.info("数据库初始化完成")
        return True

    except Exception as e:
        logger.error(f"数据库初始化失败: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            release_connection(conn)


def _create_default_user(cur):
    """创建默认管理员用户"""
    import hashlib
    from config.settings import DEFAULT_USER, DEFAULT_PASSWORD

    password_hash = hashlib.sha256(DEFAULT_PASSWORD.encode()).hexdigest()

    cur.execute(
        "SELECT id FROM users WHERE username = %s",
        (DEFAULT_USER,)
    )
    if cur.fetchone() is None:
        cur.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, %s)",
            (DEFAULT_USER, password_hash, "admin")
        )
        logger.info(f"默认用户 {DEFAULT_USER} 创建成功")


def reset_db():
    """重置数据库（删除所有表，谨慎使用）"""
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(f"DROP TABLE IF EXISTS {VECTOR_TABLE} CASCADE")
        cur.execute("DROP TABLE IF EXISTS documents CASCADE")
        cur.execute("DROP TABLE IF EXISTS query_logs CASCADE")
        cur.execute("DROP TABLE IF EXISTS users CASCADE")
        conn.commit()
        logger.info("数据库已重置（所有表已删除）")
        return True
    except Exception as e:
        logger.error(f"数据库重置失败: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            release_connection(conn)
