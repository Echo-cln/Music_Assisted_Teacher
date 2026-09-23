
import json, httpx
from app.core.config import get_settings

class OpenAICompatibleAdapter:
    def __init__(self, model=None, base_url=None, api_key=None):
        s=get_settings()
        self.model=model or s.ai_model
        self.base_url=(base_url or s.ai_base_url).rstrip("/")
        self.api_key=api_key or s.ai_api_key

    def stream(self,messages):
        if not self.api_key:
            raise ValueError("未配置AI_API_KEY")
        payload={"model":self.model,"messages":messages,"stream":True,"temperature":0.7}
        with httpx.Client(timeout=httpx.Timeout(150,connect=10)) as c:
            with c.stream("POST",self.base_url+"/chat/completions",
                headers={"Authorization":f"Bearer {self.api_key}","Content-Type":"application/json"},
                json=payload) as r:
                r.raise_for_status()
                for line in r.iter_lines():
                    if not line.startswith("data: "): continue
                    d=line[6:]
                    if d=="[DONE]": break
                    obj=json.loads(d)
                    delta=obj.get("choices",[{}])[0].get("delta",{}).get("content")
                    if delta: yield delta
