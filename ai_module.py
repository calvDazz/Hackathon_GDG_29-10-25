# ai_module.py
import re, json, hashlib
from difflib import SequenceMatcher

# 引用 WatsonX 配置（简化为可独立使用）
USE_WX = False
wx_model = None

try:
    from ibm_watsonx_ai import APIClient
    from ibm_watsonx_ai.foundation_models import ModelInference
    from dotenv import load_dotenv
    import os
    load_dotenv()
    apikey = os.getenv("WATSONX_APIKEY")
    url = os.getenv("WATSONX_URL")
    project = os.getenv("WATSONX_PROJECT_ID")
    if apikey and url and project:
        wx_client = APIClient({"apikey": apikey, "url": url})
        wx_model = ModelInference(model_id="meta-llama/llama-3-3-70b-instruct",
                                  api_client=wx_client, project_id=project)
        USE_WX = True
except Exception:
    pass


def text_similarity_factual(en_text: str, de_text: str) -> float:
    """基于 factual signature + WatsonX 的混合语义相似度"""
    if not en_text or not de_text:
        return 0.0

    # ---------- 先构建 factual signature ----------
    def signature(t):
        t = t.lower()
        t = re.sub(r"€|eur|euro", "eur", t)
        t = re.sub(r"\d{1,2}\s*[A-Za-z]+\s*\d{4}", "date", t)
        t = re.sub(r"(regulation|verordnung)\s*\(eu[^\)]*\)\s*\d{4}/\d+", "reg", t)
        t = re.sub(r"article\s*\d+", "article", t)
        t = re.sub(r"\s+", "", t)
        return hashlib.md5(t.encode("utf-8")).hexdigest()[:12]

    sig_en = signature(en_text)
    sig_de = signature(de_text)

    if sig_en == sig_de:
        base_score = 1.0
    else:
        base_score = SequenceMatcher(None, sig_en, sig_de).ratio()

    # ---------- WatsonX 精修 ----------
    if USE_WX and wx_model:
        prompt = f"""
You are a bilingual factual consistency checker.
Return JSON only:
{{"semantic_similarity":0.0-1.0, "comment":"short factual note"}}

[EN]
{en_text}

[DE]
{de_text}
"""
        try:
            result = wx_model.generate_text(prompt=prompt, params={"max_new_tokens":180, "temperature":0})
            import json
            m = re.search(r"\{[\s\S]*\}", str(result))
            if m:
                obj = json.loads(m.group(0))
                if "semantic_similarity" in obj:
                    return float(obj["semantic_similarity"])
        except Exception:
            pass

    return round(float(base_score), 3)
