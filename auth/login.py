"""
简易登录验证模块 — 默认账号密码登录
使用SHA256哈希存储密码
"""

import hashlib
import streamlit as st
from typing import Optional

from database.operations import verify_user, create_user
from config.settings import DEFAULT_USER, DEFAULT_PASSWORD
from utils.logger import get_logger

logger = get_logger(__name__)


def hash_password(password: str) -> str:
    """SHA256密码哈希"""
    return hashlib.sha256(password.encode()).hexdigest()


def check_login(username: str, password: str) -> Optional[dict]:
    """验证登录，成功返回用户信息，失败返回None"""
    if not username or not password:
        return None

    password_hash = hash_password(password)
    user = verify_user(username, password_hash)

    if user:
        logger.info(f"用户登录成功: {username}")
        return user
    else:
        logger.warning(f"登录失败: {username}")
        return None


def init_session_state():
    """初始化Streamlit会话状态"""
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False
    if "user" not in st.session_state:
        st.session_state.user = None
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []


def login_ui():
    """登录界面"""
    st.markdown("""
    <div style="text-align: center; padding: 40px 0 20px 0;">
        <h1 style="font-size: 3rem;">⚓ 海军标准 RAG 智能体</h1>
        <p style="color: #666; font-size: 1.1rem;">
            标准精准检索 · 专业智能问答 · 长文结构化总结 · 公文级文本润色 · 标准查漏补缺
        </p>
    </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 1, 1])

    with col2:
        with st.form("login_form"):
            st.markdown("### 用户登录")
            username = st.text_input("用户名", placeholder="请输入用户名")
            password = st.text_input("密码", type="password", placeholder="请输入密码")
            submitted = st.form_submit_button("登 录", use_container_width=True)

            if submitted:
                user = check_login(username, password)
                if user:
                    st.session_state.logged_in = True
                    st.session_state.user = user
                    st.session_state.chat_history = []
                    st.success("登录成功！")
                    st.rerun()
                else:
                    st.error("用户名或密码错误")

        st.caption(f"默认账号: {DEFAULT_USER} / {DEFAULT_PASSWORD}")


def logout_ui():
    """登出按钮"""
    if st.sidebar.button("退出登录", use_container_width=True):
        st.session_state.logged_in = False
        st.session_state.user = None
        st.session_state.chat_history = []
        st.rerun()


def require_login(func):
    """登录验证装饰器（用于需要登录的页面）"""
    def wrapper(*args, **kwargs):
        if not st.session_state.get("logged_in", False):
            st.warning("请先登录")
            st.stop()
        return func(*args, **kwargs)
    return wrapper
