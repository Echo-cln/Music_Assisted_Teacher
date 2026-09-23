
"""模型无关 AI 提供层：支持 OpenAI Compatible 接口、结构化解析和失败降级。"""

import time
from collections.abc import Iterator
from app.services.llm.factory import get_adapter

def _retry_stream(messages, model=None):
    last=None
    for i, delay in enumerate([0,3,10]):
        try:
            if delay:
                time.sleep(delay)
            yield from get_adapter(model).stream(messages)
            return
        except Exception as e:
            last=e
    raise last

def _build_messages(base:dict, instruction:str):
    draft={k:v for k,v in base.items() if k!="generation_context"}
    evidence=base.get("generation_context",{})
    return [
        {"role":"system","content":
        "你是乡村小学音乐教研员。只输出合法JSON对象，不要Markdown。"
        "必须保持教案字段结构，不改变字段名称。"},
        {"role":"user","content":str({
            "draft":draft,
            "evidence":evidence,
            "instruction":instruction
        })}
    ]

def stream_lesson_json(base:dict, model=None)->Iterator[str]:
    yield from _retry_stream(_build_messages(base,"增强教学语言和课堂活动"), model)

def stream_adjusted_lesson_json(content:dict,instruction:str,model=None)->Iterator[str]:
    yield from _retry_stream(_build_messages(content,instruction), model)
