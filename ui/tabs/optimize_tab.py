"""
文本优化区 — 按海军军用文书规范优化文案
"""

import streamlit as st

from rag.optimizer import optimize_text
from utils.logger import get_logger

logger = get_logger(__name__)


def render_optimize_tab():
    with st.container(border=True):
        st.subheader("✏️ 海军公文文本智能优化")
        st.caption("修正口语化表述、梳理逻辑层级、统一专业术语、规整格式结构")

        aspects = st.multiselect(
            "优化维度",
            ["去口语化", "理顺逻辑", "统一术语", "规整格式"],
            default=["去口语化", "理顺逻辑", "统一术语", "规整格式"],
        )

    c1, c2 = st.columns([1, 1], gap="large")

    with c1:
        with st.container(border=True):
            st.markdown("**📝 原文输入**")
            original_text = st.text_area(
                "原文",
                height=420,
                placeholder="在此粘贴需要优化的方案、报告、制度、条款等文本...",
                label_visibility="collapsed",
            )

            with st.expander("📎 快捷示例"):
                if st.button("载入示例文本"):
                    st.session_state["optimize_input_raw"] = _get_sample_text()
                    st.rerun()

    with c2:
        with st.container(border=True):
            st.markdown("**✨ 优化结果**")

            if st.button("✨ 开始优化", type="primary", use_container_width=True):
                text_to_optimize = original_text or st.session_state.get("optimize_input_raw", "")
                if not text_to_optimize.strip():
                    st.warning("请先输入需要优化的文本")
                    return

                with st.spinner("正在优化..."):
                    result = optimize_text(text_to_optimize, optimization_aspects=aspects)

                if result.get("optimized"):
                    st.markdown(result["optimized"])
                    st.divider()
                    st.caption("📊 变更摘要")
                    st.info(result.get("changes_summary", ""))
                    st.download_button(
                        "📥 下载优化后文本",
                        result["optimized"],
                        file_name="优化后文本.txt",
                        mime="text/plain",
                    )


def _get_sample_text():
    return """舰艇安全管理制度（草稿）

一、总则
咱这个制度是为了保证舰艇上的人和设备都安全，不搞那些有危险的事情。

二、消防方面
舰上得备好消防用的东西，比如灭火器啊，消防水龙带什么的。
大家得会用这些消防器材，不要到时候手忙脚乱的。
如果着火了，先喊人，然后再想办法灭火。

三、弹药管理
弹药库那边要管严一点，不能啥人都能进去。进去得登记，不能带火种。
搬弹药的时候轻拿轻放，别磕碰了。
定期检查弹药情况，发现问题及时上报。

四、日常检查
每个星期都要检查一次各种安全设施，看看有没有坏的或者过期的。
如果有问题要记下来，然后找人修。修好了也要记录。

五、附则
这个制度从下发那天开始执行。
以前要是有跟这个不一样的规定，以这个为准。"""
