
import json, re

def parse_json(text: str) -> dict:
    if not text:
        raise ValueError("模型返回为空")
    text=text.strip()
    text=re.sub(r"^```json\s*", "", text, flags=re.I)
    text=re.sub(r"```$", "", text.strip())
    try:
        return json.loads(text)
    except Exception:
        start=text.find("{")
        end=text.rfind("}")
        if start>=0 and end>start:
            return json.loads(text[start:end+1])
        raise
