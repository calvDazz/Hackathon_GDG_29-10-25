# -*- coding: utf-8 -*-
"""
final.py — Entity-based factual comparison with optional WatsonX semantic AI
Fully compatible with Flask app.py (2-file or 3-file mode)
"""

import re, json, os, hashlib
from pathlib import Path
from datetime import datetime
from difflib import SequenceMatcher

# ---------- Optional WatsonX AI Semantic Engine ----------
USE_WX = False
wx_model = None

try:
    from ibm_watsonx_ai import APIClient
    from ibm_watsonx_ai.foundation_models import ModelInference
    from dotenv import load_dotenv
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


# ---------- REGEX EXTRACTION ----------
ENTITY_PATTERNS = {
    "date": (
        r"(?:"  
        r"\b\d{4}\.\s*(?:gada)?\s*\d{1,2}\.\s*(?:" 
        r"janv(?:āris|ārī|āra)?|febr(?:uāris|ruārī|ruāra)?|marts?|martā|aprīlis?|aprīlī|"
        r"maijs?|maijā|jūnijs?|jūnijā|jūlijs?|jūlijā|augusts?|augustā|"
        r"septembris?|septembrī|oktobris?|oktobrī|novembris?|novembrī|"
        r"decembris?|decembrī"
        r")\b"
        r"|"
        r"\b\d{1,2}[.\-/]?\s*(?:" 
        r"Jan(?:uar|uary)?|Feb(?:ruar|ruary)?|März|Maerz|Mar(?:ch)?|Apr(?:il)?|"
        r"Mai|May|Jun[iy]?|Jul[iy]?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|"
        r"Okt(?:ober)?|Oct(?:ober)?|Nov(?:ember)?|Dez(?:ember)?|Dec(?:ember)?"
        r")\s*\d{2,4}\b"
        r"|"
        r"\b\d{1,2}[.\-/]\d{1,2}[.\-/]\d{2,4}\b"
        r")"
    ),
    "number": r"(?<![A-Za-z])\d{1,6}(?:[.,\s]\d{3})*(?:[.,]\d+)?(?![A-Za-z])",
    "eur_amount": (
        r"(?:EUR|€)\s?\d{1,6}(?:[.,\s]\d{3})*(?:[.,]\d+)?"
        r"|\d{1,6}(?:[.,\s]\d{3})*(?:[.,]\d+)?\s?(?:EUR|€|miljardi|miljoni|Million|Milliarde|Mio|Mrd)"
    ),
    "percent": r"\b\d{1,3}(?:[.,]\d+)?\s?%",
    "legal_ref": (
        r"\((?:EU|ES|EURATOM|EK|EC)(?:\s*,\s*(?:EU|ES|EURATOM|EK|EC))*\)\s*\d{4}\s*/\s*\d+"
        r"|"
        r"(?:Regulation|Regula|Regulas|Verordnung|Directive|Direktīva|Decision|Lēmums)"
        r"\s*\((?:EU|ES|EURATOM|EK|EC)(?:\s*,\s*(?:EU|ES|EURATOM|EK|EC))*\)"
        r"(?:\s*(?:No\.|Nr\.|N\.)\s*)?\d{4}\s*/\s*\d+"
    ),
    "article": (
        r"(?:(?:Article|Art\.?|Artikel|pants?|panta|pantā|pantu)"
        r"\s*\d+[A-Za-z]?(?:\(\d+\))?)"
    ),
    "range": r"\b\d{4}\s?[–\-—]\s?\d{4}\b"
}

ENTITY_EQUIVALENCE = {
    "ES": "EU",
    "EK": "EC",
    "EURATO": "EURATOM"
}

MONTHS = {
    'january':1,'february':2,'march':3,'april':4,'may':5,'june':6,'july':7,
    'august':8,'september':9,'october':10,'november':11,'december':12,
    'januar':1,'februar':2,'märz':3,'maerz':3,'mai':5,'juni':6,'juli':7,
    'august':8,'september':9,'oktober':10,'november':11,'dezember':12,
    "janvāris":1,"janvārī":1,"februāris":2,"februārī":2,"marts":3,"martā":3,
    "aprīlis":4,"aprīlī":4,"maijs":5,"maijā":5,"jūnijs":6,"jūnijā":6,
    "jūlijs":7,"jūlijā":7,"augusts":8,"augustā":8,"septembris":9,"septembrī":9,
    "oktobris":10,"oktobrī":10,"novembris":11,"novembrī":11,"decembris":12,"decembrī":12
}

LEGAL_RECANON = re.compile(
    r"(?:\((?P<codes>(?:[A-Z]+)(?:\s*,\s*[A-Z]+)*)\)\s*)?"
    r"(?:(?:Regulation|Regula|Regulas|Verordnung|Directive|Direktīva|Decision|Lēmums)"
    r"\s*\((?P<codes2>(?:[A-Z]+)(?:\s*,\s*[A-Z]+)*)\)\s*(?:No\.|Nr\.|N\.)?\s*)?"
    r"(?P<year>\d{4})\s*/\s*(?P<num>\d+)", re.I
)

# ---------- Helpers ----------

def clean_text(text: str) -> str:
    if not isinstance(text, str):
        return ""
    text = re.sub(r"[\u00A0\u202F\u2009]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()

def normalize_date(text: str) -> str:
    text = clean_text(text)
    text = re.sub(r"\bgad(?:a|ā|am|us|ai)\b", "", text, flags=re.I).strip()
    m = re.match(r"(\d{4})\.\s*(?:gada)?\s*(\d{1,2})\.\s*([A-Za-zāčēģīķļņōŗšūž]+)", text)
    if m:
        y, d, mon = m.groups()
        mon = re.sub(r"(ā|a|s|āra)$", "", mon.lower())
        month = MONTHS.get(mon, 0)
        if month: return f"{y}-{month:02d}-{int(d):02d}"
    m = re.match(r"(\d{1,2})\.?\s*([A-Za-zäÄöÖüÜ]+)\s*(\d{4})", text)
    if m:
        d, mon, y = m.groups()
        month = MONTHS.get(mon.lower(), 0)
        if month: return f"{y}-{month:02d}-{int(d):02d}"
    m = re.match(r"(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{2,4})", text)
    if m:
        d, mth, y = map(int, m.groups())
        y = y + 2000 if y < 100 else y
        return f"{y}-{mth:02d}-{d:02d}"
    return text

def normalize_number(text: str) -> str:
    val = text.replace(" ", "").replace(",", ".")
    try:
        return str(float(val))
    except:
        return val

def normalize_entity(tag: str, val: str) -> str:
    val = val.strip()
    if tag == "date": return normalize_date(val)
    if tag in ("percent", "number"): return normalize_number(val)
    if tag == "eur_amount":
        s = val.upper().replace(" ", "")
        s = re.sub(r"(\d+(?:[.,]\d+)?)EUR", r"EUR\1", s)
        s = re.sub(r"MILJARDI", "BILLION", s)
        s = re.sub(r"MILJONI", "MILLION", s)
        s = s.replace(",", ".")
        return s
    if tag == "legal_ref":
        s = clean_text(val).upper()
        m = LEGAL_RECANON.search(s)
        if not m:
            for k, v in ENTITY_EQUIVALENCE.items():
                s = s.replace(k.upper(), v.upper())
            return s
        codes = m.group("codes") or m.group("codes2") or ""
        year, num = m.group("year"), m.group("num")
        code_list = []
        if codes:
            for c in re.split(r"\s*,\s*", codes):
                c = ENTITY_EQUIVALENCE.get(c.strip(), c.strip()).upper()
                code_list.append(c)
        if not code_list: code_list = ["EU"]
        order = {"EC": 0, "EU": 1, "EURATOM": 2}
        code_list = sorted(set(code_list), key=lambda x: order.get(x, 99))
        return f"({', '.join(code_list)}){year}/{num}"
    if tag == "article":
        norm = re.sub(r"(Article|Artikel|Art\.?|pants?|panta|pantā|pantu)", "Art", val, flags=re.I)
        m = re.search(r"(\d+[A-Za-z]?(?:\(\d+\))?)", norm)
        if m: return f"Art {m.group(1)}"
        return "Art"
    return val.strip()

def extract_entities(text: str):
    text = clean_text(text)
    out = {}
    for tag, pat in ENTITY_PATTERNS.items():
        matches = re.findall(pat, text, re.I)
        if matches:
            out[tag] = [normalize_entity(tag, m) for m in matches]
    return out

# ---------- Entity-based similarity ----------
def entity_similarity(ents_a: dict, ents_b: dict) -> float:
    """Compare factual overlap between entities."""
    if not ents_a and not ents_b:
        return 1.0
    if not ents_a or not ents_b:
        return 0.0

    tags = set(ENTITY_PATTERNS.keys())
    total, matched = 0, 0
    for tag in tags:
        a_vals, b_vals = set(ents_a.get(tag, [])), set(ents_b.get(tag, []))
        if not a_vals and not b_vals:
            continue
        total += 1
        if a_vals & b_vals:
            matched += 1
    return round(matched / total, 3) if total else 0.0

# ---------- Comparison + Report ----------

def load_paragraphs(path: Path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)[0]["para"]
    return {p["para_number"]: p["para"] for p in data}

def generate_report(en_path: Path, de_path: Path, lv_path: Path):
    en_map = load_paragraphs(en_path)
    de_map = load_paragraphs(de_path)
    lv_map = load_paragraphs(lv_path)

    all_nums = sorted(set(en_map) | set(de_map) | set(lv_map))
    rows = []
    for n in all_nums:
        en_txt, de_txt, lv_txt = en_map.get(n, ""), de_map.get(n, ""), lv_map.get(n, "")
        en_ents, de_ents, lv_ents = extract_entities(en_txt), extract_entities(de_txt), extract_entities(lv_txt)

        semantic_sim = entity_similarity(en_ents, de_ents)
        status = "green" if semantic_sim >= 0.8 else ("yellow" if semantic_sim >= 0.4 else "red")

        rows.append({
            "para_number": n,
            "en": en_txt,
            "de": de_txt,
            "entities": {"en": en_ents, "de": de_ents, "lv": lv_ents},
            "semantic_similarity": semantic_sim,
            "ai_comment": "Entity-based factual overlap",
            "status": status
        })

    return rows

def save_report_json(rows, out_path: Path):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
