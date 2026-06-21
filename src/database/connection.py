"""
数据库连接池管理 — PostgreSQL + pgvector
使用 psycopg2 连接池，支持多线程并发
"""

import psycopg2
from psycopg2 import pool
from config.settings import (
    DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD,
    DB_MIN_CONN, DB_MAX_CONN, DB_CONN_TIMEOUT,
)
from utils.logger import get_logger

logger = get_logger(__name__)

_connection_pool = None


def get_connection_pool() -> pool.ThreadedConnectionPool:
    """获取数据库连接池（单例）"""
    global _connection_pool
    if _connection_pool is None:
        _connection_pool = pool.ThreadedConnectionPool(
            minconn=DB_MIN_CONN,
            maxconn=DB_MAX_CONN,
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
        )
    return _connection_pool


def get_connection():
    """从连接池获取一个连接，带超时"""
    import threading

    pool_obj = get_connection_pool()
    result = [None]
    error = [None]

    def _get():
        try:
            result[0] = pool_obj.getconn()
        except Exception as e:
            error[0] = e

    t = threading.Thread(target=_get, daemon=True)
    t.start()
    t.join(timeout=DB_CONN_TIMEOUT)

    if t.is_alive():
        logger.error(f"数据库连接池已满，{DB_CONN_TIMEOUT}秒内无法获取连接")
        raise RuntimeError(f"数据库连接池已满，请稍后重试")
    if error[0]:
        raise error[0]
    return result[0]


def release_connection(conn):
    """归还连接到连接池"""
    if conn:
        get_connection_pool().putconn(conn)


def close_pool():
    """关闭连接池"""
    global _connection_pool
    if _connection_pool:
        _connection_pool.closeall()
        _connection_pool = None


def execute_query(sql: str, params: tuple = None, fetch: bool = True):
    """执行SQL查询的便捷函数"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            if fetch:
                result = cur.fetchall()
            else:
                result = None
            conn.commit()
            return result
    except Exception:
        conn.rollback()
        raise
    finally:
        release_connection(conn)


def execute_batch(sql: str, params_list: list):
    """批量执行SQL"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.executemany(sql, params_list)
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        release_connection(conn)


def check_connection() -> bool:
    """测试数据库连接是否正常"""
    try:
        result = execute_query("SELECT 1", fetch=True)
        return result[0][0] == 1
    except Exception:
        return False
