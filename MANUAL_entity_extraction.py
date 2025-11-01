import re, json
from pathlib import Path
from datetime import datetime

# ---------- FILES ----------
EN_FILE = Path("test_sample_en_parsed.json")
LV_FILE = Path("test_sample_lv_parsed.json") # Not used in loading, but kept for context
DE_FILE = Path("test_sample_de_parsed.json")

# ---------- REGEX EXTRACTION ----------
ENTITY_PATTERNS = {
    # ... (1, 2, 3, 4 remain the same)
    "date": (
        r"(?:" 
        # Latvian: 2025. gada 18. marts / 2025. gada 18. martā / 2025. gada 18. janvāra
        r"\b\d{4}\.\s*(?:gada)?\s*\d{1,2}\.\s*(?:"
        r"janv(?:āris|ārī|āra)?|febr(?:uāris|ruārī|ruāra)?|marts?|martā|aprīlis?|aprīlī|"
        r"maijs?|maijā|jūnijs?|jūnijā|jūlijs?|jūlijā|augusts?|augustā|"
        r"septembris?|septembrī|oktobris?|oktobrī|novembris?|novembrī|"
        r"decembris?|decembrī"
        r")\b"
        r"|"
        # EN / DE: 18. Januar 2024, 18 March 2025, 18/03/2025
        r"\b\d{1,2}[.\-/]?\s*(?:"
        r"Jan(?:uar|uary)?|Feb(?:ruar|ruary)?|März|Maerz|Mar(?:ch)?|Apr(?:il)?|"
        r"Mai|May|Jun[iy]?|Jul[iy]?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|"
        r"Okt(?:ober)?|Oct(?:ober)?|Nov(?:ember)?|Dez(?:ember)?|Dec(?:ember)?"
        r")\s*\d{2,4}\b"
        r"|"
        # Numeric fallback: 18.03.2025
        r"\b\d{1,2}[.\-/]\d{1,2}[.\-/]\d{2,4}\b"
        r")"
    ),

    "number": r"(?<![A-Za-z])\d{1,6}(?:[.,]\d{3})*(?:[.,]\d+)?(?![A-Za-z])",

    "eur_amount": (
        r"(?:EUR|€)\s?\d{1,6}(?:[.,\s]\d{3})*(?:[.,]\d+)?"
        r"|\d{1,6}(?:[.,\s]\d{3})*(?:[.,]\d+)?\s?(?:EUR|€|miljardi|miljoni|Million|Milliarde|Mio|Mrd)"
    ),

    "percent": r"\b\d{1,3}(?:[.,]\d+)?\s?%",

    # --- 5️⃣ LEGAL REFERENCES (EN/DE/LV variants) (FIXED: Simplified to capture full reference) ---
    "legal_ref": (
        # This broad pattern captures the entire phrase, which we clean up later.
        r"\b(?:Council|Regulation|Regula|Regulas|Verordnung|Directive|Direktīva|Decision|Lēmums)"
        r"\s*\((?:EU|ES|EURATOM|EK|EC)(?:\s*,\s*(?:EU|ES|EURATOM|EK|EC))*\)?"
        r"(?:\s*(?:No\.|Nr\.|N\.)\s*)?\s*\d+\s*/\s*\d{4}\b" # NUMBER/YEAR
        r"|\b\((?:EU|ES|EURATOM|EK|EC)(?:\s*,\s*(?:EU|ES|EURATOM|EK|EC))*\)\s*\d{4}\s*/\s*\d+\b" # YEAR/NUMBER (fallback)
    ),

    # ... (6, 7 remain the same)
    "article": (
        r"(?:(?:Article|Art\.?|Artikel|pants?|panta|pantā|pantu)"
        r"\s*\d+[A-Za-z]?(?:\(\d+\))?)"
    ),

    "range": r"\b\d{4}\s?[–\-—]\s?\d{4}\b"
}


# ---------- CROSS-LINGUAL EQUIVALENCE MAP ----------
ENTITY_EQUIVALENCE = {
    "ES": "EU",
    "EK": "EC",
    "EURATO": "EURATOM"
}

# ---------- MONTH NAMES ----------
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

# ---------- HELPERS ----------
def clean_text(text: str) -> str:
    if not isinstance(text, str):
        return ""
    text = re.sub(r"[\u00A0\u202F\u2009]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()

def normalize_date(text):
    text = clean_text(text)
    
    # FIX: Use text_processed to handle the German date format with a period after the day
    text_processed = re.sub(r"(\b\d{1,2})\.\s*([A-Za-zäÄöÖüÜ]+)\s*(\d{4}\b)", r"\1 \2 \3", text)

    # Latvian: 2025. gada 1. janvāra → 2025-01-01
    m = re.match(r"(\d{4})\.\s*(?:gada)?\s*(\d{1,2})\.\s*([A-Za-zāčēģīķļņōŗšūž]+)", text)
    if m:
        y, d, mon = m.groups()
        mon = re.sub(r"(ā|a|s|āra)$", "", mon.lower())
        month = MONTHS.get(mon, 0)
        if month:
            return f"{y}-{month:02d}-{int(d):02d}"

    # English/German formats (using pre-processed text to catch "11. September 2013")
    m = re.match(r"(\d{1,2})\s*([A-Za-zäÄöÖüÜ]+)\s*(\d{4})", text_processed)
    if m:
        d, mon, y = m.groups()
        month = MONTHS.get(mon.lower(), 0)
        if month:
            return f"{y}-{month:02d}-{int(d):02d}"

    # Numeric fallback
    m = re.match(r"(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{2,4})", text)
    if m:
        d, mth, y = map(int, m.groups())
        y = y + 2000 if y < 100 else y
        return f"{y}-{mth:02d}-{d:02d}"

    return text

def normalize_number(text):
    val = text.replace(" ", "").replace(",", ".")
    try:
        return str(float(val))
    except:
        return val

# ---------- LEGAL REF CANONICALIZER (FIXED) ----------
# FIXED: Added 'Council' and swapped year/num to match NUMBER/YEAR format
LEGAL_RECANON = re.compile(
    r"(?:\((?P<codes>(?:[A-Z]+)(?:\s*,\s*[A-Z]+)*)\)\s*)?"
    r"(?:(?:Council|Regulation|Regula|Regulas|Verordnung|Directive|Direktīva|Decision|Lēmums)"
    r"\s*\((?P<codes2>(?:[A-Z]+)(?:\s*,\s*[A-Z]+)*)\)\s*(?:No\.|Nr\.|N\.)?\s*)?"
    r"(?P<num>\d+)\s*/\s*(?P<year>\d{4})", re.I
)

# ---------- NORMALIZATION ----------
def normalize_entity(tag, val):
    val = val.strip()
    if tag == "date":
        return normalize_date(val)
    if tag in ("percent", "number"):
        return normalize_number(val)
    if tag == "eur_amount":
        s = val.upper().replace(" ", "")
        s = re.sub(r"(\d+(?:[.,]\d+)?)EUR", r"EUR\1", s)
        s = re.sub(r"EUR(\d+(?:[.,]\d+)?)", r"EUR\1", s)
        s = re.sub(r"MILJARDI", "BILLION", s)
        s = re.sub(r"MILJONI", "MILLION", s)
        s = s.replace(",", ".")
        return s
    
    if tag == "legal_ref":
        s = clean_text(val).upper()
        
        # --- FIX: Proactively strip legal keywords and 'No.' prefix ---
        # 1. Strip the legal entity words (Council, Regulation, Verordnung, etc.)
        s = re.sub(
            r"\b(?:COUNCIL|REGULATION|REGULA|REGULAS|VERORDNUNG|DIRECTIVE|DIREKTĪVA|DECISION|LĒMUMS)\s*", 
            "", s, flags=re.I
        )
        # 2. Strip all variants of the number prefix (No., Nr., N.) 
        s = re.sub(r"\s*(?:NO\.|NR\.|N\.)\s*", "", s, flags=re.I)
        # 3. Re-clean to handle extra spaces after stripping
        s = clean_text(s)
        # -----------------------------------------------------------
        
        m = LEGAL_RECANON.search(s) # Search the clean, reduced string
        
        if not m:
            # Fallback if the code/number pattern isn't found
            for k, v in ENTITY_EQUIVALENCE.items():
                s = s.replace(k.upper(), v.upper())
            return s
        
        # Now, the simplified regex only has one codes group to check
        codes = m.group("codes")
        year, num = m.group("year"), m.group("num")
        
        code_list = []
        if codes:
            for c in re.split(r"\s*,\s*", codes):
                c = ENTITY_EQUIVALENCE.get(c.strip(), c.strip()).upper()
                code_list.append(c)
        
        if not code_list:
            # This should not happen with the extraction logic, but is a safe fallback
            code_list = ["EU"]
            
        order = {"EC": 0, "EU": 1, "EURATOM": 2}
        code_list = sorted(set(code_list), key=lambda x: order.get(x, 99))
        
        return f"({', '.join(code_list)}){year}/{num}"

    # ... (article and default returns remain the same)
    if tag == "article":
        norm = re.sub(r"(Article|Artikel|Art\.?|pants?|panta|pantā|pantu)", "Art", val, flags=re.I)
        m = re.search(r"(\d+[A-Za-z]?(?:\(\d+\))?)", norm)
        if m:
            return f"Art {m.group(1)}"
        return "Art"
    return val.strip()

# ---------- LOAD ----------
def load_paragraphs(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)[0]["para"]
    return {p["para_number"]: p["para"] for p in data}
def load_paragraphs(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)[0]["para"]
    return {p["para_number"]: p["para"] for p in data}

en_map = load_paragraphs(EN_FILE)
# Renamed lv_map to de_map for correct tracking of the German file
de_map = load_paragraphs(DE_FILE) 

# ---------- ENTITY EXTRACTION ----------
def extract_entities(text):
    text = clean_text(text)
    entities = {}
    for tag, pat in ENTITY_PATTERNS.items():
        matches = re.findall(pat, text, re.I)
        if matches:
            entities[tag] = [normalize_entity(tag, m) for m in matches]
    return entities

# ---------- SMART COMPARISON ----------
def is_significant_mismatch(en_vals, de_vals):
    """Return True only if one side lacks all equivalents."""
    if not en_vals and not de_vals:
        return False
    en_set, de_set = set(en_vals), set(de_vals)
    if en_set & de_set:
        return False  # any overlap = acceptable
    return True

# ---------- CONSISTENCY CHECK ----------
mismatches = []
for num in sorted(set(en_map) & set(de_map)): 
    en_ents = extract_entities(en_map[num])
    de_ents = extract_entities(de_map[num]) 
    for tag in ENTITY_PATTERNS:
        if tag in en_ents or tag in de_ents:
            if is_significant_mismatch(en_ents.get(tag, []), de_ents.get(tag, [])): 
                mismatches.append({
                    "para": num,
                    "type": tag,
                    "en": en_ents.get(tag, []),
                    "de": de_ents.get(tag, []) 
                })

# ---------- REPORT ----------
for m in mismatches:
    en_only = set(m["en"]) - set(m["de"]) 
    de_only = set(m["de"]) - set(m["en"]) 
    print(f"⚠️ Para {m['para']} — {m['type']} mismatch")
    if en_only:
        print(f"   EN-only: {sorted(en_only)}")
    if de_only:
        print(f"   DE-only: {sorted(de_only)}")
    print()