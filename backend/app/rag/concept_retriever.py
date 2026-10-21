"""
Legal concept to constitutional provision mapping.
Maps high-level legal concepts (in English + Indian languages) to specific 
article number ranges or groups for direct retrieval boosting.

This resolves the retrieval quality problem for conceptual queries like:
- "What are fundamental rights?" → Articles 12-35 (Part III)
- "What are directive principles?" → Articles 36-51 (Part IV)
- "Remedies for violation of fundamental rights" → Articles 32, 226
"""
import re
from typing import List, Optional


# Map concept keywords to article groups for retrieval boosting
CONCEPT_ARTICLE_MAP = {
    # Fundamental Rights
    "fundamental rights": ("article_group", ["12", "13", "14", "15", "16", "17", "18",
                                              "19", "20", "21", "21A", "22", "23", "24",
                                              "25", "26", "27", "28", "29", "30", "32"]),
    "fundamental right": ("article_group", ["12", "13", "14", "15", "16", "17", "18",
                                             "19", "20", "21", "21A", "22", "23", "24"]),
    "right to equality": ("article_group", ["14", "15", "16", "17", "18"]),
    "right to freedom": ("article_group", ["19", "20", "21", "21A", "22"]),
    "right against exploitation": ("article_group", ["23", "24"]),
    "freedom of religion": ("article_group", ["25", "26", "27", "28"]),
    "cultural and educational rights": ("article_group", ["29", "30"]),
    "right to constitutional remedies": ("article_group", ["32"]),
    "remedies for violation": ("article_group", ["32", "226"]),
    "writ petition": ("article_group", ["32", "226"]),
    "habeas corpus": ("article_group", ["32", "226"]),
    "mandamus": ("article_group", ["32", "226"]),
    "certiorari": ("article_group", ["32", "226"]),
    "quo warranto": ("article_group", ["32", "226"]),
    "legal remedies": ("article_group", ["32", "226"]),
    "constitutional remedy": ("article_group", ["32", "226"]),
    "petition supreme court": ("article_group", ["32"]),
    "petition high court": ("article_group", ["226"]),
    "writ jurisdiction": ("article_group", ["32", "226"]),

    # Directive Principles
    "directive principles": ("article_group", ["36", "37", "38", "39", "39A", "40",
                                               "41", "42", "43", "44", "45", "46", "47", "48", "48A", "49", "50", "51"]),
    "dpsp": ("article_group", ["36", "37", "38", "39", "39A", "40", "41", "43", "44", "45", "46", "47", "48", "48A"]),

    # Fundamental Duties
    "fundamental duties": ("article_group", ["51A"]),
    "fundamental duty": ("article_group", ["51A"]),

    # Right to Property
    "right to property": ("article_group", ["300A"]),
    "property rights": ("article_group", ["300A", "19"]),

    # Environment
    "environment protection": ("article_group", ["48A", "51A"]),
    "forest protection": ("article_group", ["48A", "51A"]),
    "trees protection": ("article_group", ["48A", "51A"]),
    "wildlife protection": ("article_group", ["48A", "51A"]),
    "protect environment": ("article_group", ["48A", "51A"]),

    # Equality
    "equality before law": ("article_group", ["14"]),
    "equal protection": ("article_group", ["14"]),
    "prohibition of discrimination": ("article_group", ["15"]),
    "equality of opportunity": ("article_group", ["16"]),
    "abolition of untouchability": ("article_group", ["17"]),

    # Freedom / Liberty
    "right to life": ("article_group", ["21"]),
    "personal liberty": ("article_group", ["21"]),
    "right to education": ("article_group", ["21A"]),
    "freedom of speech": ("article_group", ["19"]),
    "freedom of expression": ("article_group", ["19"]),
    "right to move freely": ("article_group", ["19"]),
    "protection from arrest": ("article_group", ["22"]),
    "preventive detention": ("article_group", ["22"]),

    # Preamble & Structure
    "preamble": ("article_search", "preamble"),
    "part iii": ("article_group", ["12", "13", "14", "15", "16", "17", "18",
                                   "19", "20", "21", "22", "23", "24", "25", "26", "27", "28", "29", "30", "32"]),
    "part iv": ("article_group", ["36", "37", "38", "39", "40", "41", "42", "43", "44", "45", "46", "47", "48", "48A", "49", "50", "51"]),
    "part iva": ("article_group", ["51A"]),
}

# Multilingual keyword patterns → English concept mapping
MULTILINGUAL_CONCEPT_RE = [
    # Hindi
    (re.compile(r"मौलिक\s+अधिकारों\s+का\s+उल्लंघन|अधिकारों\s+का\s+उल्लंघन|कानूनी\s+उपाय|उपाय\s+अपना", re.UNICODE), "remedies for violation"),
    (re.compile(r"मौलिक\s+कर्तव्य", re.UNICODE), "fundamental duties"),
    (re.compile(r"मौलिक\s+अधिकार", re.UNICODE), "fundamental rights"),
    (re.compile(r"रिट\s+याचिका|रिट\s+पेटीशन", re.UNICODE), "writ petition"),
    (re.compile(r"कानूनी\s+राहत", re.UNICODE), "legal remedies"),
    (re.compile(r"नीति\s+निर्देशक\s+तत्व|राज्य\s+नीति\s+के\s+निर्देशक\s+सिद्धांत", re.UNICODE), "directive principles"),
    (re.compile(r"पर्यावरण\s+संरक्षण|वन\s+संरक्षण", re.UNICODE), "environment protection"),
    (re.compile(r"अभिव्यक्ति\s+की\s+स्वतंत्रता|बोलने\s+की\s+आज़ादी", re.UNICODE), "freedom of speech"),
    (re.compile(r"जीवन\s+का\s+अधिकार|व्यक्तिगत\s+स्वतंत्रता", re.UNICODE), "right to life"),
    (re.compile(r"समानता\s+का\s+अधिकार|कानून\s+के\s+समक्ष\s+समानता", re.UNICODE), "right to equality"),

    # Tamil
    (re.compile(r"அடிப்படை\s+உரிமை\s+மீறல்|உரிமை\s+மீறல்|சட்ட\s+நடவடிக்கை", re.UNICODE), "remedies for violation"),
    (re.compile(r"அடிப்படை\s+கடமைகள்", re.UNICODE), "fundamental duties"),
    (re.compile(r"அடிப்படை\s+உரிமைகள்|அடிப்படை\s+உரிமை", re.UNICODE), "fundamental rights"),
    (re.compile(r"ஆணை\s+மனு|ரிட்\s+மனு", re.UNICODE), "writ petition"),
    (re.compile(r"சுற்றுச்சூழல்\s+பாதுகாப்பு", re.UNICODE), "environment protection"),
    (re.compile(r"சம\s+நீதி|சமத்துவ\s+உரிமை", re.UNICODE), "right to equality"),
    (re.compile(r"வாழ்வுரிமை|சுதந்திரம்", re.UNICODE), "right to life"),
    (re.compile(r"வழிகாட்டும்\s+கோட்பாடுகள்|வழிகாட்டு\s+நெறிமுறைகள்", re.UNICODE), "directive principles"),

    # Telugu
    (re.compile(r"ప్రాథమిక\s+హక్కులు|ప్రాథమిక\s+హక్కు", re.UNICODE), "fundamental rights"),
    (re.compile(r"ప్రాథమిక\s+విధులు", re.UNICODE), "fundamental duties"),
    (re.compile(r"రిట్\s+పిటిషన్|న్యాయ\s+పరిష్కారం", re.UNICODE), "writ petition"),
    (re.compile(r"హక్కుల\s+ఉల్లంఘన|హక్కుల\s+రక్షణ", re.UNICODE), "remedies for violation"),
    (re.compile(r"పర్యావరణ\s+రక్షణ", re.UNICODE), "environment protection"),

    # Kannada
    (re.compile(r"ಮೂಲಭೂತ\s+ಹಕ್ಕುಗಳು|ಮೂಲಭೂತ\s+ಹಕ್ಕು", re.UNICODE), "fundamental rights"),
    (re.compile(r"ಮೂಲಭೂತ\s+ಕರ್ತವ್ಯಗಳು", re.UNICODE), "fundamental duties"),
    (re.compile(r"ನಿರ್ದೇಶಕ\s+ತತ್ತ್ವಗಳು", re.UNICODE), "directive principles"),
    (re.compile(r"ಪರಿಸರ\s+ರಕ್ಷಣೆ", re.UNICODE), "environment protection"),

    # Malayalam
    (re.compile(r"മൗലിക\s+അവകാശങ്ങൾ|മൗലിക\s+അവകാശം", re.UNICODE), "fundamental rights"),
    (re.compile(r"നിർദ്ദേശക\s+തത്ത്വങ്ങൾ", re.UNICODE), "directive principles"),
    (re.compile(r"പരിസ്ഥിതി\s+സംരക്ഷണം", re.UNICODE), "environment protection"),

    # Bengali
    (re.compile(r"মৌলিক\s+অধিকার|মৌলিক\s+অধিকারসমূহ", re.UNICODE), "fundamental rights"),
    (re.compile(r"মৌলিক\s+কর্তব্য", re.UNICODE), "fundamental duties"),
    (re.compile(r"নির্দেশমূলক\s+নীতি", re.UNICODE), "directive principles"),
    (re.compile(r"পরিবেশ\s+সংরক্ষণ", re.UNICODE), "environment protection"),

    # Gujarati
    (re.compile(r"મૂળભૂત\s+અધિકારો|મૂળભૂત\s+અધિકાર", re.UNICODE), "fundamental rights"),
    (re.compile(r"મૂળભૂત\s+ફરજો", re.UNICODE), "fundamental duties"),
    (re.compile(r"પર્યાવરણ\s+સંરક્ષણ", re.UNICODE), "environment protection"),

    # Punjabi
    (re.compile(r"ਮੌਲਿਕ\s+ਅਧਿਕਾਰ|ਮੌਲਿਕ\s+ਹੱਕ", re.UNICODE), "fundamental rights"),
    (re.compile(r"ਮੌਲਿਕ\s+ਕਰਤੱਵ", re.UNICODE), "fundamental duties"),
    (re.compile(r"ਵਾਤਾਵਰਣ\s+ਸੰਭਾਲ", re.UNICODE), "environment protection"),

    # Odia
    (re.compile(r"ମୌଳିକ\s+ଅଧିକାର|ମୌଳିକ\s+ଅଧିକାରଗୁଡ଼ିକ", re.UNICODE), "fundamental rights"),
    (re.compile(r"ମୌଳିକ\s+କର୍ତ୍ତବ୍ୟ", re.UNICODE), "fundamental duties"),
    (re.compile(r"ପରିବେଶ\s+ସୁରକ୍ଷା", re.UNICODE), "environment protection"),

    # Marathi
    (re.compile(r"मूलभूत\s+हक्क|मूलभूत\s+अधिकार|प्राथमिक\s+हक्क", re.UNICODE), "fundamental rights"),
    (re.compile(r"मूलभूत\s+कर्तव्ये", re.UNICODE), "fundamental duties"),
    (re.compile(r"मार्गदर्शक\s+तत्त्वे", re.UNICODE), "directive principles"),
    (re.compile(r"पर्यावरण\s+संरक्षण", re.UNICODE), "environment protection"),

    # Urdu
    (re.compile(r"بنیادی\s+حقوق|بنیادی\s+حق", re.UNICODE), "fundamental rights"),
    (re.compile(r"بنیادی\s+فرائض", re.UNICODE), "fundamental duties"),
    (re.compile(r"ماحولیات\s+تحفظ", re.UNICODE), "environment protection"),
]


def extract_concept_from_query(query: str) -> Optional[str]:
    """
    Detect if the query is about a high-level legal concept.
    Returns the English concept string or None.
    """
    # Check multilingual patterns first
    for pattern, concept in MULTILINGUAL_CONCEPT_RE:
        if pattern.search(query):
            return concept

    # Check English text (case-insensitive)
    q_lower = query.lower()
    for concept in sorted(CONCEPT_ARTICLE_MAP.keys(), key=len, reverse=True):
        if concept in q_lower:
            return concept

    return None


def get_articles_for_concept(concept: str) -> List[str]:
    """Return list of article numbers for a recognized concept."""
    entry = CONCEPT_ARTICLE_MAP.get(concept)
    if not entry:
        return []
    kind, data = entry
    if kind == "article_group":
        return data
    return []
