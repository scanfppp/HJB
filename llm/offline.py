"""
离线大模型接口（预留）
—— 后期无缝切换离线私有化大模型，适配内网离线部署
"""

from utils.logger import get_logger

logger = get_logger(__name__)


def offline_chat(messages: list) -> str:
    """
    离线大模型调用占位函数

    后期替换方式：
    1. 将离线模型文件放入指定路径
    2. 加载模型（如 vLLM / llama.cpp / transformers）
    3. 替换此函数为实现代码
    4. 设置环境变量 OFFLINE_MODE=true 启用

    示例实现（vLLM）:
        from vllm import LLM
        llm = LLM(model=OFFLINE_MODEL_PATH)
        outputs = llm.generate([messages])
        return outputs[0].outputs[0].text
    """
    raise NotImplementedError(
        "离线大模型尚未配置。\n"
        "请完成以下步骤：\n"
        "1. 部署离线大模型到内网服务器\n"
        "2. 在 settings.py 中设置 OFFLINE_MODEL_PATH\n"
        "3. 设置环境变量 OFFLINE_MODE=true\n"
        "4. 在 llm/offline.py 中实现 offline_chat 函数\n"
    )


def is_offline_available() -> bool:
    """检查离线模型是否可用"""
    return False
