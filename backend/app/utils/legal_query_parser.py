"""
Deterministic (regex-based) legal query understanding with full multilingual
and Indic-numeral support across English, Telugu, Hindi, Tamil, Kannada, Malayalam,
Bengali, Marathi, Gujarati, Punjabi, Odia, and Urdu.

Extracts Articles, Sections, Rules, Chapters deterministically and instantly
without expensive/slow LLM round-trips.
"""
import re
import unicodedata
from typing import Optional, Dict

def normalize_indic_digits(text: str) -> str:
    """Converts any Unicode decimal digits (e.g. Devanagari २१, Telugu ౨౧, etc.)
    into standard ASCII 0-9 digits."""
    res = []
    for ch in text:
        if unicodedata.category(ch) == "Nd":
            res.append(str(unicodedata.digit(ch)))
        else:
            res.append(ch)
    return "".join(res)

# Multilingual keywords for Article:
# English: article, art
# Telugu: ఆర్టికల్, ఆర్టికల్స్, అధికరణ, అధికరణం, నిబంధన
# Hindi/Marathi: अनुच्छेद, धारा, कलम (in constitution context)
# Tamil: சரத்து, உறுப்பு
# Kannada: ವಿಧಿ, ಪರಿಚ್ಛೇದ
# Malayalam: അനുച്ഛേദം
# Bengali: অনুচ্ছেদ
# Gujarati: અનુચ્છેદ
# Punjabi: ਅਨੁਛੇਦ
# Odia: ଅନୁଚ୍ଛେଦ
# Urdu: آرٹیکل
ARTICLE_KW = (
    r"(?:article|art\.?|"
    r"ఆర్టికల్|ఆర్టికల్స్|అధికరణం|అధికరణ|నిబంధన|విధి|"
    r"अनुच्छेद|"
    r"சரத்து|உறுப்பு|"
    r"ವಿಧಿ|ಆರ್ಟಿಕಲ್|ಪರಿಚ್ಛೇದ|ಅನುಚ್ಛೇದ|"
    r"അനുച്ഛേദം|"
    r"অনুচ্ছেদ|"
    r"અનુચ્છેદ|"
    r"ਅਨੁਛੇਦ|"
    r"ଅନୁଚ୍ଛେଦ|"
    r"آرٹیکل)"
)

# Multilingual keywords for Section:
# English: section, sec
# Telugu: సెక్షన్, సెక్షన్లు, విభాగం, దఫా
# Hindi/Marathi: धारा, कलम
# Tamil: பிரிவு
# Kannada: ಪ್ರಕರಣ, ಸೆಕ್ಷನ್, ವಿಭಾಗ
# Malayalam: വകുപ്പ്, സെക്ഷൻ
# Bengali: ধারা, বিভাগ
# Gujarati: કલમ
# Punjabi: ਧਾਰਾ
# Odia: ଧାରା
# Urdu: دفعہ|سیکشن
SECTION_KW = (
    r"(?:section|sec\.?|"
    r"సెక్షన్|సెక్షన్లు|విభాగం|దఫా|"
    r"धारा|कलम|"
    r"பிரிவ(?:ு|ை|ின்)|"
    r"ಪ್ರಕರಣ|ಸೆಕ್ಷನ್|ವಿಭಾಗ|"
    r"വകുപ്പ്|സെക്ഷൻ|"
    r"ধারা|বিভাগ|"
    r"કલમ|"
    r"ਧਾਰਾ|"
    r"ଧାରା|"
    r"دفعہ|سیکشن)"
)

# Multilingual keywords for Rule:
RULE_KW = (
    r"(?:rule|rules|"
    r"రూల్|రూల్స్|నియమం|నిబంధన|"
    r"नियम|"
    r"விதி|"
    r"ನಿಯಮ|"
    r"ചട്ടം|നിയമം|"
    r"নিয়ম|"
    r"નિયમ|"
    r"ਨਿਯਮ|"
    r"ନିୟମ|"
    r"رول|قاعدہ)"
)

# Multilingual keywords for Chapter:
CHAPTER_KW = (
    r"(?:chapter|"
    r"అధ్యాయం|అధ్యాయము|"
    r"अध्याय|"
    r"அத்தியாயம்|"
    r"ಅಧ್ಯಾಯ|"
    r"অধ্যায়|"
    r"પ્રકરણ|"
    r"ਅਧਿਆਇ|"
    r"ଅଧ୍ୟାୟ|"
    r"باب)"
)

CONSTITUTION_HINT_RE = re.compile(
    r"\b(?:constitution|samvidhan|rajyangam)\b|"
    r"संविधान|రాజ్యాంగం|அரசியலமைப்ப|ಸಂವಿಧಾನ|ഭരണഘടന|সংবিধান|બંધારણ|ਸੰਵਿਧਾਨ|ସମ୍ବିଧାନ|آئین",
    re.IGNORECASE,
)

LEGAL_TOPIC_RE = re.compile(
    r"\b(?:law|legal|constitution|article|section|rule|act|court|judge|lawyer|attorney|"
    r"rights?|fundamental|writ|petition|appeal|police|fir|crime|criminal|civil|sue|lawsuit|"
    r"arrest|bail|offence|offense|prosecution|tenant|landlord|divorce|custody|inheritance|"
    r"property dispute|contract|consumer complaint|employment dispute|judgment|judgement|"
    r"supreme court|high court|parliament|precedent)\b|"
    r"कानून|कानूनी|संविधान|अधिकार|अदालत|न्यायालय|पुलिस|मुकदमा|वकील|जमानत|शिकायत|"
    r"చట్టం|రాజ్యాంగం|హక్కులు|కోర్టు|పోలీసు|న్యాయవాది|వివాదం|"
    r"சட்டம்|அரசியலமைப்பு|உரிமை|பிரிவ(?:ு|ை|ின்)|நீதிமன்றம்|காவல்துறை|வழக்கறிஞர்|"
    r"ಕಾನೂನು|ಸಂವಿಧಾನ|ಹಕ್ಕು|ನ್ಯಾಯಾಲಯ|ಪೊಲೀಸ್|ವಕೀಲ|"
    r"നിയമം|ഭരണഘടന|അവകാശം|കോടതി|പോലീസ്|അഭിഭാഷകൻ|"
    r"আইন|সংবিধান|অধিকার|আদালত|পুলিশ|আইনজীবী|"
    r"કાયદો|બંધારણ|અધિકાર|અદાલત|પોલીસ|વકીલ|"
    r"ਕਾਨੂੰਨ|ਸੰਵਿਧਾਨ|ਅਧਿਕਾਰ|ਅਦਾਲਤ|ਪੁਲਿਸ|ਵਕੀਲ|"
    r"قانون|آئین|حقوق|عدالت|پولیس|وکیل",
    re.IGNORECASE | re.UNICODE,
)

# Patterns: keyword followed by number (e.g. "Article 21", "ఆర్టికల్ 21", "అధికరణ 21A")
ARTICLE_PRE_RE = re.compile(rf"{ARTICLE_KW}\s*[-:–—]?\s*(\d{{1,3}}[A-Za-z]?)\b", re.IGNORECASE)
# Patterns: number followed by keyword (e.g. "21వ అధికరణ", "21st article", "21वां अनुच्छेद")
ARTICLE_POST_RE = re.compile(rf"\b(\d{{1,3}}[A-Za-z]?)(?:st|nd|rd|th|వ|va|वां|वें)?\s*{ARTICLE_KW}", re.IGNORECASE)

SECTION_PRE_RE = re.compile(rf"{SECTION_KW}\s*[-:–—]?\s*(\d{{1,4}}[A-Za-z]?)\b", re.IGNORECASE)
SECTION_POST_RE = re.compile(rf"\b(\d{{1,4}}[A-Za-z]?)(?:st|nd|rd|th|వ|va|वां|वें|வது|ஆவது)?\s*{SECTION_KW}", re.IGNORECASE)

RULE_PRE_RE = re.compile(rf"{RULE_KW}\s*[-:–—]?\s*(\d{{1,4}}[A-Za-z]?)\b", re.IGNORECASE)
RULE_POST_RE = re.compile(rf"\b(\d{{1,4}}[A-Za-z]?)(?:st|nd|rd|th|వ|va|वां|वें)?\s*{RULE_KW}", re.IGNORECASE)

CHAPTER_RE = re.compile(rf"{CHAPTER_KW}\s*[-:–—]?\s*([IVXLCDM\d]{{1,6}})\b", re.IGNORECASE)

ACT_NAME_RE = re.compile(
    r"\b((?:indian\s+)?[a-z][a-z ,'&]{3,60}act,?\s*\d{4})\b", re.IGNORECASE
)
ACT_ABBREVIATION_RE = re.compile(r"\b(BNSS|BNS|BSA)\b", re.IGNORECASE)

TAMIL_SPOKEN_SEVEN_RE = re.compile(
    r"(?<!\d)(?P<tens>[2-9]0)\s+(?:செவன்|செவன|சேவன்|சேவன|seven)(?:ாவது|ஆவது|வது|th)?(?=\s*பிரிவ(?:ு|ை|ின்))",
    re.IGNORECASE,
)


def parse_legal_query(message: str) -> Dict:
    """
    Returns a structured intent, e.g.:
      {"query_type": "article", "number": "21", "document_hint": "constitution"}
      {"query_type": "section", "number": "302", "document_hint": None}
      {"query_type": "general", "number": None, "document_hint": None}
    """
    # 1. Normalize Indic numerals to standard ASCII digits
    text = normalize_indic_digits(message.strip())
    text = TAMIL_SPOKEN_SEVEN_RE.sub(
        lambda match: str(int(match.group("tens")) + 7), text
    )

    # Check for Article
    art_m = ARTICLE_PRE_RE.search(text) or ARTICLE_POST_RE.search(text)
    if art_m:
        return {
            "query_type": "article",
            "number": art_m.group(1).upper(),
            "document_hint": "constitution",
            "act_name": None,
        }

    # Check for Section
    sec_m = SECTION_PRE_RE.search(text) or SECTION_POST_RE.search(text)
    if sec_m:
        if CONSTITUTION_HINT_RE.search(text):
            return {
                "query_type": "article",
                "number": sec_m.group(1).upper(),
                "document_hint": "constitution",
                "act_name": None,
            }
        act_m = ACT_NAME_RE.search(text)
        abbreviation_m = ACT_ABBREVIATION_RE.search(text)
        return {
            "query_type": "section",
            "number": sec_m.group(1).upper(),
            "document_hint": "act",
            "act_name": abbreviation_m.group(1).upper() if abbreviation_m else (
                act_m.group(1).strip() if act_m else None
            ),
        }

    # Check for Rule
    rule_m = RULE_PRE_RE.search(text) or RULE_POST_RE.search(text)
    if rule_m:
        return {
            "query_type": "rule",
            "number": rule_m.group(1).upper(),
            "document_hint": "rules",
            "act_name": None,
        }

    # Check for Chapter
    chap_m = CHAPTER_RE.search(text)
    if chap_m:
        return {
            "query_type": "chapter",
            "number": chap_m.group(1).upper(),
            "document_hint": "constitution" if CONSTITUTION_HINT_RE.search(text) else None,
            "act_name": None,
        }

    return {"query_type": "general", "number": None, "document_hint": None, "act_name": None}


def is_legal_query(message: str) -> bool:
    """Return whether a message should use legal-document retrieval."""
    if parse_legal_query(message)["query_type"] != "general":
        return True
    return bool(LEGAL_TOPIC_RE.search(message))

