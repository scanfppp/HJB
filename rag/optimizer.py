"""
文本智能优化 — 按海军军用文书规范优化
修正口语化、梳理逻辑、统一术语、规整格式
"""

from config.prompts import TEXT_OPTIMIZE_PROMPT
from llm.client import chat_with_prompt
from utils.logger import get_logger

logger = get_logger(__name__)


def optimize_text(
    original_text: str,
    optimization_aspects: list = None,
) -> dict:
    """
    文本智能优化主函数

    Args:
        original_text: 原始文本
        optimization_aspects: 优化维度列表
            ["去口语化", "理顺逻辑", "统一术语", "规整格式"]

    Returns:
        dict: {"original": ..., "optimized": ..., "changes_summary": ...}
    """
    if not original_text.strip():
        return {
            "original": original_text,
            "optimized": "",
            "changes_summary": "请输入需要优化的文本内容",
        }

    if optimization_aspects is None:
        optimization_aspects = ["去口语化", "理顺逻辑", "统一术语", "规整格式"]

    # 在提示词中加入具体优化维度
    aspect_instructions = _build_aspect_instructions(optimization_aspects)

    optimized_prompt = TEXT_OPTIMIZE_PROMPT.replace(
        "【优化要求】",
        f"【优化要求】\n{aspect_instructions}"
    )

    logger.info(f"开始文本优化: 原文{len(original_text)}字, 优化维度={optimization_aspects}")

    optimized = chat_with_prompt(
        optimized_prompt,
        original_text,
        max_tokens=4096,
    )

    # 生成变更摘要
    changes = _generate_changes_summary(original_text, optimized)

    return {
        "original": original_text,
        "optimized": optimized or "（优化失败，请重试）",
        "changes_summary": changes,
        "aspects": optimization_aspects,
    }


def _build_aspect_instructions(aspects: list) -> str:
    """根据选定维度构建优化指令"""
    aspect_map = {
        "去口语化": "1. 修正口语化表述：将口语化、非正式、方言化表达替换为标准制式话术，确保符合海军公文语言规范",
        "理顺逻辑": "2. 梳理逻辑层级：理顺段落结构，确保层次分明、逻辑递进、因果关系清晰",
        "统一术语": "3. 统一专业术语：校核并统一海军专业标准术语，确保前后一致、全文统一",
        "规整格式": "4. 规整格式结构：按公文规范调整段落格式、序号体系、标题层级",
    }

    instructions = []
    for i, aspect in enumerate(aspects, 0):
        if aspect in aspect_map:
            # 保持原有序号
            inst = aspect_map[aspect].split("：", 1)[-1] if "：" in aspect_map[aspect] else aspect_map[aspect]
            instructions.append(f"{i+1}. {inst}")

    instructions.append("5. 严格保留原文核心业务含义不变")
    return "\n".join(instructions)


def _generate_changes_summary(original: str, optimized: str) -> str:
    """生成变更摘要"""
    changes = []

    # 简单的变更检测
    original_lines = original.strip().split("\n")
    optimized_lines = optimized.strip().split("\n") if optimized else []

    if len(optimized_lines) != len(original_lines):
        changes.append(f"段落结构调整：原文{len(original_lines)}段 → 优化后{len(optimized_lines)}段")

    if len(optimized) != len(original):
        diff = len(optimized) - len(original)
        sign = "+" if diff > 0 else ""
        changes.append(f"篇幅变化：{sign}{diff}字符")

    if not changes:
        changes.append("文本已按海军文书规范优化，保留了原文核心含义")

    return "\n".join(changes)
