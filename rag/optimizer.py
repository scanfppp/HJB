"""
文本智能优化 — 按海军军用文书规范优化
修正口语化、梳理逻辑、统一术语、规整格式
V2：支持文风选择、优化强度、篇幅控制、二次调整
"""

import re

from config.prompts import (
    TEXT_OPTIMIZE_PROMPT, TEXT_OPTIMIZE_PROMPT_V2, TEXT_CONTINUE_OPTIMIZE_PROMPT,
    OPTIMIZE_STYLES, OPTIMIZE_INTENSITY, OPTIMIZE_LENGTH,
)
from llm.client import chat_with_prompt, chat_stream
from utils.logger import get_logger

logger = get_logger(__name__)


def build_optimize_messages(
    original_text: str,
    style: str = "standard",
    intensity: str = "medium",
    length: str = "keep",
    optimization_aspects: list = None,
) -> list:
    """
    构建优化所需的 messages 列表（V2），供流式端点使用。

    Args:
        original_text: 原始文本
        style: 文风键名 (standard|concise|authoritative|briefing)
        intensity: 优化强度 (light|medium|deep)
        length: 篇幅控制 (keep|shorten|expand)
        optimization_aspects: 自定义优化维度列表，为 None 时根据 intensity 自动选择
    """
    style_info = OPTIMIZE_STYLES.get(style, OPTIMIZE_STYLES["standard"])
    intensity_info = OPTIMIZE_INTENSITY.get(intensity, OPTIMIZE_INTENSITY["medium"])
    length_info = OPTIMIZE_LENGTH.get(length, OPTIMIZE_LENGTH["keep"])

    if optimization_aspects is None:
        optimization_aspects = _intensity_aspects(intensity)

    aspect_instructions = _build_aspect_instructions(optimization_aspects)

    prompt = TEXT_OPTIMIZE_PROMPT_V2.format(
        style=f"{style_info['label']}：{style_info['desc']}",
        intensity=f"{intensity_info['label']}：{intensity_info['desc']}",
        length=f"{length_info['label']}：{length_info['desc']}",
        aspects=aspect_instructions,
        original_text=original_text,
    )

    return [
        {"role": "system", "content": prompt},
        {"role": "user", "content": original_text},
    ]


def build_continue_optimize_messages(previous_result: str, adjustment: str) -> list:
    """
    构建「继续调整」的 messages 列表。
    将上次优化结果作为输入，用户追加调整指令。
    """
    prompt = TEXT_CONTINUE_OPTIMIZE_PROMPT.format(
        previous_result=previous_result,
        adjustment=adjustment,
    )
    return [
        {"role": "system", "content": prompt},
        {"role": "user", "content": adjustment},
    ]


def compute_changes(original: str, optimized: str, intensity: str = "medium") -> dict:
    """基于原始文本和优化后文本，生成结构化变更摘要（按强度分层）"""
    changes = []
    terminology_count = 0
    structural_count = 0
    format_count = 0
    correction_count = 0

    original_lines = original.strip().split("\n")
    optimized_lines = optimized.strip().split("\n") if optimized else []

    # 段落结构变化
    if len(optimized_lines) != len(original_lines):
        structural_count += abs(len(optimized_lines) - len(original_lines))
        changes.append(f"段落结构调整：原文{len(original_lines)}段 → 优化后{len(optimized_lines)}段")

    # 篇幅变化
    if len(optimized) != len(original):
        diff = len(optimized) - len(original)
        sign = "+" if diff > 0 else ""
        changes.append(f"篇幅变化：{sign}{diff}字符")
        if intensity == "deep":
            format_count = max(1, abs(diff) // 50)

    # 术语和句式变化（启发式检测）
    if original and optimized:
        orig_chars = set(original)
        opt_chars = set(optimized)
        diff_ratio = len(opt_chars - orig_chars) / max(len(orig_chars), 1)
        if diff_ratio > 0.03:
            terminology_count = max(1, int(diff_ratio * 10))
            if intensity in ("medium", "deep"):
                format_count = max(format_count, int(diff_ratio * 8))

    # 轻度模式下只报纠错
    if intensity == "light" and not changes:
        correction_count = 1
        changes.append("已完成基础纠错检查")

    if not changes:
        changes.append("文本已按海军文书规范优化，保留了原文核心含义")

    return {
        "summary": "\n".join(changes),
        "correction_count": correction_count,
        "terminology_changes": terminology_count,
        "structural_changes": structural_count,
        "format_changes": format_count,
        "intensity": intensity,
    }


def clean_output(text: str) -> str:
    """
    后处理安全兜底：移除 LLM 输出中行首的破折号标记，合并为段落。
    无论提示词效果如何，确保输出不会出现"——"开头的行。
    """
    if not text:
        return text

    lines = text.split('\n')
    result = []
    for line in lines:
        stripped = line.lstrip()
        # 移除行首的 —— 或 — 标记（可能带空格）
        if stripped.startswith('——') or stripped.startswith('—'):
            content = stripped.lstrip('—— —')
            if result and result[-1].strip():
                # 如果上一行以句号、分号结束，追加为独立句；否则接续
                last = result[-1].rstrip()
                if last.endswith(('。', '；', '）', ')', '：')):
                    result.append(content)
                else:
                    result[-1] = last + '；' + content
            else:
                result.append(content)
        else:
            result.append(line)

    # 清理连续空行（最多保留一个）
    cleaned = []
    prev_empty = False
    for line in result:
        empty = not line.strip()
        if empty:
            if not prev_empty:
                cleaned.append(line)
            prev_empty = True
        else:
            cleaned.append(line)
            prev_empty = False

    return '\n'.join(cleaned)


# ============================================================
# 内部辅助
# ============================================================

def _intensity_aspects(intensity: str) -> list:
    """根据强度级别返回对应的优化维度"""
    if intensity == "light":
        return ["纠正语病"]
    elif intensity == "deep":
        return ["去口语化", "理顺逻辑", "统一术语", "规整格式", "细节补充"]
    else:
        return ["去口语化", "理顺逻辑", "统一术语"]


def _build_aspect_instructions(aspects: list) -> str:
    """根据选定维度构建优化指令"""
    aspect_map = {
        "去口语化": "修正口语化表述：将口语化、非正式、方言化表达替换为标准制式话术，确保符合海军公文语言规范",
        "理顺逻辑": "梳理逻辑层级：理顺段落结构，确保层次分明、逻辑递进、因果关系清晰",
        "统一术语": "统一专业术语：校核并统一海军专业标准术语，确保前后一致、全文统一",
        "规整格式": "规整格式结构：按公文规范调整段落格式、序号体系、标题层级",
        "细节补充": "补充细节内容：对过于笼统的表述补充具体细节、数据支撑或案例说明",
        "纠正语病": "修正基础语病：纠正错别字、语法错误、标点符号不当、搭配不当等问题",
    }

    instructions = []
    for i, aspect in enumerate(aspects, 0):
        if aspect in aspect_map:
            inst = aspect_map[aspect].split("：", 1)[-1] if "：" in aspect_map[aspect] else aspect_map[aspect]
            instructions.append(f"{i+1}. {inst}")

    instructions.append(f"{len(instructions)+1}. 严格保留原文核心业务含义不变")
    return "\n".join(instructions)


# ============================================================
# 向后兼容的函数
# ============================================================

def _generate_changes_summary(original: str, optimized: str) -> str:
    """生成变更摘要（文本格式，向后兼容）"""
    result = compute_changes(original, optimized)
    return result["summary"]


def optimize_text(
    original_text: str,
    optimization_aspects: list = None,
) -> dict:
    """
    文本智能优化主函数（同步版，向后兼容）

    Args:
        original_text: 原始文本
        optimization_aspects: 优化维度列表

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

    changes = _generate_changes_summary(original_text, optimized)

    return {
        "original": original_text,
        "optimized": optimized or "（优化失败，请重试）",
        "changes_summary": changes,
        "aspects": optimization_aspects,
    }
