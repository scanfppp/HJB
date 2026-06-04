"""
日志管理模块 — 文件日志 + 控制台输出
支持日志轮转和清理
"""

import os
import logging
from logging.handlers import TimedRotatingFileHandler
from datetime import datetime

from config.settings import LOG_DIR, LOG_LEVEL, LOG_MAX_DAYS


def get_logger(name: str) -> logging.Logger:
    """获取命名日志器"""
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    logger.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))

    # 确保日志目录存在
    os.makedirs(LOG_DIR, exist_ok=True)

    # 文件处理器（按天轮转）
    log_file = os.path.join(LOG_DIR, f"navy_rag_{datetime.now().strftime('%Y%m%d')}.log")
    file_handler = TimedRotatingFileHandler(
        log_file,
        when="midnight",
        interval=1,
        backupCount=LOG_MAX_DAYS,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_formatter)

    # 控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%H:%M:%S",
    )
    console_handler.setFormatter(console_formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


def clean_old_logs():
    """清理过期日志文件"""
    import time

    now = time.time()
    cutoff = now - LOG_MAX_DAYS * 86400

    for filename in os.listdir(LOG_DIR):
        filepath = os.path.join(LOG_DIR, filename)
        if os.path.isfile(filepath) and filename.endswith(".log"):
            if os.path.getmtime(filepath) < cutoff:
                os.remove(filepath)
