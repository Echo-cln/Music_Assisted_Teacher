
from .openai_adapter import OpenAICompatibleAdapter

def get_adapter(model=None):
    # 所有 OpenAI Compatible 服务统一入口
    return OpenAICompatibleAdapter(model=model)
