import re
import html
from collections import Counter, defaultdict

import spacy


# ============================================================
# SPACY MODEL
# ============================================================

MODEL_NAME = "en_core_web_sm"


def load_nlp_model():
    try:
        return spacy.load(MODEL_NAME, disable=["ner"])
    except OSError as exc:
        raise RuntimeError(
            "spaCy English model is not installed.\n\n"
            "Run:\n"
            "python -m spacy download en_core_web_sm"
        ) from exc


nlp = load_nlp_model()


# ============================================================
# STOP WORDS
# ============================================================

STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "been", "being", "by",
    "for", "from", "has", "have", "had", "he", "her", "here", "hers",
    "him", "his", "how", "i", "if", "in", "into", "is", "it", "its",
    "itself", "me", "my", "of", "on", "or", "our", "ours", "she",
    "that", "the", "their", "theirs", "them", "then", "there", "these",
    "they", "this", "those", "to", "too", "under", "up", "very", "we",
    "were", "what", "when", "where", "which", "who", "whom", "why",
    "will", "with", "you", "your", "yours", "about", "above", "after",
    "again", "against", "all", "also", "any", "because", "before",
    "below", "between", "both", "but", "can", "could", "did", "do",
    "does", "doing", "during", "each", "few", "further", "just",
    "more", "most", "over", "same", "some", "such", "than", "through",
    "until", "while", "would", "should", "may", "might", "must", "shall",
}


# Pure recruitment / HR boilerplate – never a skill
GENERIC_WORDS = {
    "ability", "abilities", "advantageous", "candidate", "candidates",
    "capacity", "clearly", "company", "companies", "contribute",
    "contribution", "demonstrable", "demonstrated", "duties", "ensure",
    "ensuring", "experience", "experienced", "field", "function",
    "functions", "highly", "ideal", "including", "job", "knowledge",
    "maintain", "maintaining", "organisation", "organization", "possess",
    "preferred", "proficient", "provide", "provided", "providing",
    "related", "required", "requirements", "responsibilities",
    "responsibility", "role", "roles", "skills", "staff", "support",
    "supporting", "teams", "team", "work", "working",
    "desirable", "advantageous", "starting", "offer", "offers",
    "benefits", "summary", "depending", "gross", "annum", "salary",
    "salaries", "kes", "usd", "gbp", "euro", "per",
}


# Broad words that are only useful inside phrases
GENERIC_STANDALONE = {
    "data", "monitoring", "management", "system", "systems", "project",
    "projects", "programme", "programmes", "program", "programs",
    "quality", "digital", "technical", "software", "platform",
    "platforms", "information", "development", "implementation",
    "report", "reports", "reporting", "framework", "frameworks",
    "process", "processes", "team", "teams", "advisor", "adviser",
    "support", "training", "module", "modules", "tool", "tools",
    "method", "methods", "approach", "approaches", "solution",
    "solutions", "activity", "activities", "performance", "result",
    "results", "indicator", "indicators", "collection", "service",
    "services", "business", "stakeholder", "stakeholders",
}


OTHER_GENERIC = {
    "information", "person", "people", "individual", "individuals",
    "position", "positions", "years", "year", "month", "months",
    "salary", "gross", "annum", "offer", "offers", "benefits",
    "summary", "starting", "ideal", "desirable", "advantageous",
    "development", "duties", "responsibility", "responsibilities",
    "requirement", "requirements", "candidate", "candidates",
    "kes", "usd", "gbp", "euro", "per",
}


INCIDENTAL_WORDS = {
    "advisor", "adviser", "candidate", "company", "department",
    "employee", "employees", "function", "functions", "job",
    "manager", "officer", "organization", "organisation", "position",
    "role", "staff", "team", "teams", "unit", "work", "workplace",
    "responsibility", "responsibilities", "duty", "duties", "module",
    "modules", "task", "tasks",
}


ACTION_VERBS = {
    "achieve", "address", "align", "analyse", "analyze", "assess",
    "build", "collect", "communicate", "contribute", "coordinate",
    "create", "curate", "deliver", "develop", "ensure", "facilitate",
    "guide", "implement", "improve", "include", "interpret", "manage",
    "monitor", "oversee", "prepare", "provide", "review", "strengthen",
    "translate", "validate", "conduct", "maintain", "support", "lead",
    "use", "utilize", "utilise", "work", "assist", "design", "produce",
    "report", "track", "organize", "organise", "plan", "execute",
    "write", "present", "engage", "possess", "ensuring",
}


HARD_CUES = {
    "analytics", "analysis", "analytical", "statistic", "statistics",
    "statistical", "database", "databases", "sql", "dataset", "datasets",
    "dashboard", "dashboards", "visualisation", "visualization",
    "reporting", "indicator", "indicators", "monitoring", "evaluation",
    "measurement", "software", "system", "systems", "digital",
    "technology", "technical", "programming", "coding", "automation",
    "platform", "platforms", "project", "projects", "programme",
    "program", "programmes", "programs", "implementation", "framework",
    "frameworks", "quality", "compliance", "research", "survey",
    "surveys", "finance", "financial", "budget", "budgets",
    "procurement", "operations", "logistics", "planning", "strategy",
    "strategic", "documentation", "management", "engineering", "design",
    "development", "validation", "cleaning", "integrity", "insight",
    "insights", "picklist", "outcome", "output", "donor", "theory",
    "change", "capacity", "partner", "partners", "guideline", "guidelines",
    "workshop", "workshops", "seminar", "seminars",
}


SOFT_CUES = {
    "communication", "communications", "communicate", "collaboration",
    "collaborative", "teamwork", "leadership", "leading", "lead",
    "negotiation", "interpersonal", "relationship", "relationships",
    "coordination", "coordinate", "facilitation", "facilitate",
    "presentation", "presentations", "writing", "written", "verbal",
    "listening", "mentoring", "coaching", "training", "guidance",
    "decision", "decisions", "problem", "solving", "adaptability",
    "flexibility", "initiative", "creativity", "critical", "thinking",
    "stakeholder", "stakeholders", "engagement",
}


TECHNICAL_TERMS = {
    "sql", "python", "excel", "tableau", "stata", "rstudio", "powerbi",
    "power", "bi", "gis", "spss", "sas", "java", "javascript", "html",
    "css", "django", "flask", "mysql", "postgresql", "postgres",
    "oracle", "mongodb", "aws", "azure", "docker", "git", "github",
    "kubernetes", "salesforce", "surveycto", "odk", "redcap", "arcgis",
    "qgis", "r",
}


ABBREVIATION_MAP = {
    "m and e": "monitoring evaluation",
    "m e": "monitoring evaluation",
    "m&e": "monitoring evaluation",
    "powerbi": "power bi",
    "power bi": "power bi",
    "ms excel": "excel",
    "microsoft excel": "excel",
    "microsoft power bi": "power bi",
    "key performance indicator": "performance indicator",
    "key performance indicators": "performance indicator",
    "human resource": "human resources",
    "human resources": "human resources",
    "h r": "human resources",
    "data visualisation": "data visualization",
    "data analyses": "data analysis",
    "data analytics": "data analytics",
    "r studio": "rstudio",
    "r/rstudio": "rstudio",
    "r / rstudio": "rstudio",
    "r rstudio": "rstudio",
}


PROFICIENCY_MODIFIERS = {
    "advanced", "basic", "excellent", "good", "proven", "relevant",
    "strong", "solid", "practical", "professional", "proficient",
    "high", "sound", "demonstrated", "appropriate", "complex",
}


APPROVED_PHRASES = {
    "data quality", "data system", "data systems", "data management",
    "data analysis", "data analytics", "data visualization",
    "data visualisation", "data collection", "data reporting",
    "data dashboard", "data quality assessment", "data integrity",
    "data validation", "data cleaning", "complex dataset", "complex datasets",
    "performance monitoring", "programme monitoring", "program monitoring",
    "programme performance", "program performance",
    "project management", "programme management", "program management",
    "database management", "results database", "result database",
    "result framework", "results framework", "performance management",
    "decision making", "decision-making",
    "problem solving", "problem-solving",
    "stakeholder engagement", "technical assistance", "technical writing",
    "interpersonal communication", "written communication",
    "verbal communication",
    "team leadership", "relationship management",
    "quality assurance",
    "advanced excel", "power bi",
    "business intelligence",
    "project planning", "strategic planning",
    "research ethics", "qualitative research", "quantitative research",
    "research methodology", "research methods",
    "policy development", "policy analysis",
    "change management", "risk management",
    "financial management", "financial reporting",
    "programme design", "program design",
    "learning management", "knowledge management",
    "report writing", "technical reporting",
    "monitoring system", "monitoring systems",
    "digital system", "digital systems",
    "information system", "information systems",
    "digital data collection", "data collection platform",
    "information management", "capacity development",
    "theory of change", "donor report", "donor reports",
    "project report", "project reports",
    "standard indicator", "standard indicators",
    "output indicator", "outcome indicator",
    "analytical tool", "analytical tools",
    "statistical tool", "statistical tools",
    "structured database", "structured databases",
}


# Absolute noise – salary, currency, pure numbers, recruitment fluff
NOISE_TERMS = {
    "gross", "annum", "salary", "salaries", "kes", "usd", "gbp", "euro",
    "starting", "offer", "offers", "benefits", "summary", "depending",
    "ideal candidate", "highly desirable", "possess experience",
    "non profit", "non profit setting", "profit setting",
    "gross salary", "gross per", "gross per annum", "starting gross salary",
    "per annum", "staff benefits", "staff benefits summary",
}


INCIDENTAL_PHRASE_WORDS = {
    "said", "once", "house", "gain", "will", "also", "including",
    "strong", "practical", "advanced", "demonstrable", "demonstrated",
    "standard", "key", "complex", "structured", "guideline",
    "guidelines", "product", "products", "related", "colleagues",
    "staff", "teams", "team", "advisor", "adviser", "workshops",
    "seminars", "modules", "materials", "ensuring", "possess",
}


# ============================================================
# NORMALIZATION
# ============================================================

def normalize_text(text):
    if not text:
        return ""
    text = text.lower()
    text = text.replace("\u2013", "-").replace("\u2014", "-")
    text = text.replace("&", " and ")
    text = text.replace("/", " / ")
    text = text.replace("-", " ")
    text = re.sub(r"[^a-z0-9+#.\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_term(term):
    term = normalize_text(term)
    if not term:
        return ""
    if term in ABBREVIATION_MAP:
        return ABBREVIATION_MAP[term]
    return term


def normalize_token(token):
    token = token.lower().strip()
    if not token:
        return ""
    exceptions = {
        "systems": "system", "analyses": "analysis",
        "statistics": "statistics", "series": "series",
        "business": "business", "process": "process",
        "processes": "process", "success": "success",
        "access": "access", "databases": "database",
        "dashboards": "dashboard", "projects": "project",
        "programmes": "programme", "programs": "program",
        "surveys": "survey", "indicators": "indicator",
        "stakeholders": "stakeholder", "relationships": "relationship",
        "communications": "communication", "presentations": "presentation",
        "datasets": "dataset", "platforms": "platform",
        "frameworks": "framework", "budgets": "budget",
        "reports": "report", "teams": "team", "tools": "tool",
        "modules": "module", "activities": "activity",
        "results": "result", "solutions": "solution",
        "insights": "insight",
    }
    if token in exceptions:
        return exceptions[token]
    if token.endswith("ies") and len(token) > 4:
        return token[:-3] + "y"
    if token.endswith("sses"):
        return token[:-2]
    if token.endswith("s") and not token.endswith("ss") and len(token) > 3:
        return token[:-1]
    return token


def canonical_term(term):
    normalized = normalize_term(term)
    if not normalized:
        return ""
    words = normalized.split()
    result = []
    for word in words:
        if word in STOP_WORDS:
            continue
        nw = normalize_token(word)
        if nw:
            result.append(nw)
    return " ".join(result)


def canonical_spacy_token(token):
    text = normalize_text(token.text)
    lemma = normalize_text(token.lemma_)
    value = lemma if lemma and lemma not in {"-pron-", "be"} else text
    return normalize_token(value)


def is_good_word(word):
    word = word.lower().strip()
    if len(word) < 2:
        return False
    if word in STOP_WORDS or word in OTHER_GENERIC or word in NOISE_TERMS:
        return False
    # Reject pure numbers or numbers with currency
    if re.fullmatch(r"[\d\s.,]+", word):
        return False
    if re.search(r"\d", word) and any(c in word for c in "kes$£€"):
        return False
    return True


def is_noise_term(term):
    """Reject salary figures, currency, pure numbers, recruitment fluff."""
    if not term:
        return True
    t = term.lower().strip()
    if t in NOISE_TERMS:
        return True
    # Mostly digits
    digits = sum(1 for c in t if c.isdigit())
    if digits > 0 and digits / max(len(t), 1) > 0.4:
        return True
    # Contains currency or salary language
    if re.search(r"\b(kes|usd|gbp|euro|salary|gross|annum|per annum)\b", t):
        return True
    # Broken fragments that start with single letter + space
    if re.match(r"^[a-z]\s+", t):
        return True
    return False


def clean_phrase(phrase):
    phrase = normalize_text(phrase)
    if not phrase or is_noise_term(phrase):
        return None
    words = phrase.split()
    if len(words) > 4:
        return None
    cleaned = []
    for word in words:
        if not word or word in STOP_WORDS:
            return None
        if not is_good_word(word):
            return None
        cleaned.append(word)
    return " ".join(cleaned) if cleaned else None


# ============================================================
# VALIDATION
# ============================================================

def get_token_context(token):
    values = set()
    if token is None:
        return values
    doc = token.doc
    start = max(0, token.i - 5)
    end = min(len(doc), token.i + 6)
    for i in range(start, end):
        if i == token.i:
            continue
        v = canonical_spacy_token(doc[i])
        if v:
            values.add(v)
    return values


def is_heading_like_token(token):
    if token is None:
        return False
    sentence = token.sent.text.strip()
    if not sentence:
        return False
    if len(sentence.split()) <= 5:
        return True
    if token.text.isupper() and len(token.text) > 2:
        return True
    return False


def is_valid_single_word_requirement(word, doc=None, token=None):
    word = canonical_term(word)
    if not word or " " in word or is_noise_term(word):
        return False
    if word in (STOP_WORDS | GENERIC_WORDS | OTHER_GENERIC | ACTION_VERBS | INCIDENTAL_WORDS | NOISE_TERMS):
        return False

    if word in TECHNICAL_TERMS:
        return True

    strong_soft = {
        "communication", "collaboration", "teamwork", "leadership",
        "negotiation", "interpersonal", "coordination", "facilitation",
        "presentation", "writing", "initiative", "adaptability",
        "flexibility", "creativity", "listening", "mentoring",
        "coaching", "guidance",
    }
    if word in strong_soft:
        return True

    strong_hard = {
        "analytics", "analysis", "statistics", "statistical",
        "database", "sql", "dataset", "dashboard", "visualisation",
        "visualization", "programming", "coding", "automation",
        "compliance", "procurement", "logistics", "engineering",
        "operations", "evaluation", "measurement", "indicator",
        "framework", "validation", "cleaning", "integrity",
        "insight", "picklist", "outcome", "output",
    }
    if word in strong_hard:
        return True

    contextual = {
        "research", "strategy", "strategic", "planning", "analytical",
        "documentation", "policy", "finance", "financial", "budget",
        "quality", "management", "technical", "reporting", "design",
        "development", "monitoring", "system", "platform", "software",
        "digital", "project", "programme", "program", "performance",
        "collection", "implementation", "capacity", "partner",
        "guideline", "workshop", "seminar", "training", "donor",
        "theory", "change",
    }
    if word in contextual or word in GENERIC_STANDALONE:
        if token is None:
            return True
        surrounding = get_token_context(token)
        req_patterns = {
            "experience", "proficiency", "proficient", "knowledge",
            "expertise", "skills", "skill", "ability", "capacity",
            "demonstrated", "demonstrable", "strong", "sound",
            "understanding", "familiarity", "competence", "competency",
            "using", "use", "with", "in", "of", "for", "including",
            "such", "as", "or", "and",
        }
        if surrounding & req_patterns or is_heading_like_token(token):
            return True
        if len(token.sent.text.split()) <= 12:
            return True
        return False

    return False


def is_requirement_phrase(phrase, doc=None, token=None):
    phrase = canonical_term(phrase)
    if not phrase or is_noise_term(phrase):
        return False
    words = phrase.split()
    if len(words) > 4:
        return False

    approved = {canonical_term(v) for v in APPROVED_PHRASES}
    if phrase in approved:
        return True

    if len(words) == 1:
        return is_valid_single_word_requirement(words[0], doc=doc, token=token)

    if any(w in INCIDENTAL_PHRASE_WORDS for w in words):
        return False
    if any(w in ACTION_VERBS for w in words):
        return False
    if any(w in NOISE_TERMS for w in words):
        return False

    if any(w in TECHNICAL_TERMS for w in words):
        return True
    if any(w in SOFT_CUES for w in words):
        return True

    strong_hard = {
        "analytics", "analysis", "statistic", "statistics", "statistical",
        "database", "sql", "dataset", "dashboard", "dashboards",
        "visualisation", "visualization", "programming", "coding",
        "automation", "compliance", "procurement", "logistics",
        "operations", "engineering", "research", "policy", "quality",
        "planning", "strategy", "documentation", "evaluation", "measurement",
        "indicator", "framework", "validation", "cleaning", "integrity",
        "monitoring", "system", "platform", "performance", "collection",
        "reporting", "management", "project", "programme", "program",
    }
    if any(w in strong_hard for w in words):
        return True

    return True


# ============================================================
# EXTRACTION
# ============================================================

def simplify_chunk_tokens(tokens):
    values = []
    for token in tokens:
        if token.is_space or token.is_punct:
            continue
        word = normalize_text(token.text)
        if not word or word in STOP_WORDS or word in PROFICIENCY_MODIFIERS:
            continue
        if word in {
            "skill", "skills", "ability", "abilities", "experience",
            "knowledge", "expertise", "proficiency", "proficient",
        }:
            continue
        if is_noise_term(word):
            continue
        values.append(word)
    if not values:
        return None
    if len(values) <= 4:
        return " ".join(values)
    for word in values:
        if word in TECHNICAL_TERMS:
            return word
    for length in (4, 3, 2):
        for i in range(len(values) - length + 1):
            candidate = " ".join(values[i:i + length])
            if candidate in APPROVED_PHRASES:
                return candidate
    return " ".join(values[:2])


def discover_approved_phrases(text):
    normalized = normalize_text(text)
    found = set()
    for phrase in APPROVED_PHRASES:
        pn = normalize_text(phrase)
        if not pn:
            continue
        pattern = re.compile(
            r"(?<![a-z0-9])" + re.escape(pn) + r"(?![a-z0-9])", re.I
        )
        if pattern.search(normalized):
            found.add(canonical_term(phrase))
    return found


def extract_list_items(text):
    found = set()
    parts = re.split(r"[,;/]|\bor\b|\band\b", text, flags=re.I)
    for part in parts:
        part = part.strip()
        if not part or len(part.split()) > 5:
            continue
        cleaned = clean_phrase(part)
        if cleaned:
            can = canonical_term(cleaned)
            if can and not is_noise_term(can) and is_requirement_phrase(can):
                found.add(can)
    return found


def suppress_compound_components(candidates):
    """
    Aggressive but safe suppression of weaker forms when a stronger
    compound exists.
    Example: "power bi" present → drop "power" and "bi"
    """
    candidates = set(candidates)
    compounds = [v for v in candidates if len(v.split()) >= 2]

    # Explicit parent → children rules for the most common cases
    parent_child = {
        "power bi": {"power", "bi", "powerbi"},
        "advanced excel": {"excel", "advanced"},
        "data visualisation": {"visualisation", "visualization", "data"},
        "data visualization": {"visualisation", "visualization", "data"},
        "data quality": {"quality", "data"},
        "data collection": {"collection", "data"},
        "data management": {"management", "data"},
        "data analysis": {"analysis", "data"},
        "data analytics": {"analytics", "data"},
        "programme monitoring": {"monitoring", "programme", "program"},
        "program monitoring": {"monitoring", "programme", "program"},
        "performance monitoring": {"monitoring", "performance"},
        "project management": {"management", "project"},
        "programme management": {"management", "programme", "program"},
        "program management": {"management", "programme", "program"},
        "business intelligence": {"business", "intelligence"},
        "rstudio": {"r", "studio"},
        "r rstudio": {"r", "rstudio", "studio"},
    }

    for parent, children in parent_child.items():
        parent_can = canonical_term(parent)
        if parent_can in candidates:
            for child in children:
                child_can = canonical_term(child)
                if child_can in candidates and child_can != parent_can:
                    candidates.discard(child_can)

    # Generic: drop weak single words that appear inside any compound
    for compound in compounds:
        for w in compound.split():
            if w in TECHNICAL_TERMS and w not in {"power", "bi", "r"}:
                continue
            if w in candidates and not is_valid_single_word_requirement(w):
                candidates.discard(w)

    return candidates


def extract_job_requirements(text):
    doc = nlp(text)
    candidates = set()

    # 1. Noun chunks
    for chunk in doc.noun_chunks:
        simplified = simplify_chunk_tokens(chunk)
        if not simplified:
            continue
        phrase = clean_phrase(simplified)
        if not phrase:
            can = canonical_term(simplified)
            if can and not is_noise_term(can) and is_requirement_phrase(can):
                candidates.add(can)
            continue
        canonical = canonical_term(phrase)
        if not canonical or is_noise_term(canonical):
            continue
        representative = None
        for token in chunk:
            tc = canonical_spacy_token(token)
            if tc and tc in canonical.split():
                representative = token
                break
        if is_requirement_phrase(canonical, doc=doc, token=representative):
            candidates.add(canonical)

    # 2. Single tokens
    for token in doc:
        if token.is_space or token.is_punct:
            continue
        original = normalize_term(token.text)
        lemma = canonical_spacy_token(token)
        for value in {original, lemma}:
            if not value:
                continue
            canonical = canonical_term(value)
            if not canonical or is_noise_term(canonical):
                continue
            if canonical in TECHNICAL_TERMS:
                candidates.add(canonical)
                continue
            if canonical in SOFT_CUES or canonical in HARD_CUES or canonical in GENERIC_STANDALONE:
                if is_valid_single_word_requirement(canonical, doc=doc, token=token):
                    candidates.add(canonical)

    # 3. Approved phrases
    candidates.update(discover_approved_phrases(text))

    # 4. Adjacent compounds
    for i in range(len(doc) - 1):
        first, second = doc[i], doc[i + 1]
        if first.is_space or second.is_space or first.is_punct or second.is_punct:
            continue
        fw = canonical_spacy_token(first)
        sw = canonical_spacy_token(second)
        if not fw or not sw:
            continue
        phrase = f"{fw} {sw}"
        can = canonical_term(phrase)
        if can and not is_noise_term(can) and is_requirement_phrase(can, doc=doc, token=first):
            candidates.add(can)
        if i + 2 < len(doc):
            third = doc[i + 2]
            if not (third.is_space or third.is_punct):
                tw = canonical_spacy_token(third)
                if tw:
                    phrase3 = f"{fw} {sw} {tw}"
                    can3 = canonical_term(phrase3)
                    if can3 and not is_noise_term(can3) and is_requirement_phrase(can3, doc=doc, token=first):
                        candidates.add(can3)

    # 5. List extraction
    candidates.update(extract_list_items(text))

    # 6. Final clean + suppression of weaker forms
    candidates = {c for c in candidates if c and len(c) > 1 and not is_noise_term(c)}
    candidates = suppress_compound_components(candidates)
    return candidates


# ============================================================
# MATCHING
# ============================================================

def normalize_cv_for_matching(text):
    if not text:
        return ""
    value = text.lower()
    value = value.replace("\u2013", "-").replace("\u2014", "-")
    value = value.replace("&", " and ").replace("/", " / ").replace("-", " ")
    value = re.sub(r"[^a-z0-9+#.\s]", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def normalized_occurrences(text, term):
    if not text or not term:
        return 0
    normalized_text = normalize_cv_for_matching(text)
    normalized_term = canonical_term(term)
    if not normalized_text or not normalized_term:
        return 0
    pattern = re.compile(
        r"(?<![a-z0-9])" + re.escape(normalized_term) + r"(?![a-z0-9])", re.I
    )
    return len(pattern.findall(normalized_text))


def term_aliases(term):
    canonical = canonical_term(term)
    if not canonical:
        return set()
    aliases = {canonical}
    normalized = normalize_term(term)
    if normalized:
        aliases.add(canonical_term(normalized))
    mapped = ABBREVIATION_MAP.get(normalized)
    if mapped:
        aliases.add(canonical_term(mapped))
    for short, long_form in ABBREVIATION_MAP.items():
        if canonical_term(long_form) == canonical:
            aliases.add(canonical_term(short))
    if canonical == "data visualisation":
        aliases.add("data visualization")
    if canonical == "data visualization":
        aliases.add("data visualisation")
    if canonical == "power bi":
        aliases.update({"powerbi", "power bi"})
    if canonical == "rstudio":
        aliases.update({"r studio", "r/rstudio", "r rstudio"})
    return {v for v in aliases if v}


def build_cv_evidence_index(text):
    index = Counter()
    if not text:
        return index
    normalized_text = normalize_cv_for_matching(text)
    index["__full_text__"] = normalized_text
    for match in re.finditer(r"[a-z0-9+#.]+", normalized_text):
        token = match.group(0).strip(".")
        if token:
            c = canonical_term(token)
            if c:
                index[c] += 1
    tokens = normalized_text.split()
    for i in range(len(tokens) - 1):
        p2 = canonical_term(f"{tokens[i]} {tokens[i+1]}")
        if p2:
            index[p2] += 1
        if i + 2 < len(tokens):
            p3 = canonical_term(f"{tokens[i]} {tokens[i+1]} {tokens[i+2]}")
            if p3:
                index[p3] += 1
    return index


def build_cv_display_index(text):
    display = defaultdict(Counter)
    if not text:
        return display
    doc = nlp(text)
    for token in doc:
        if token.is_space or token.is_punct:
            continue
        c = canonical_spacy_token(token)
        if c:
            display[c][token.text] += 1
    for i in range(len(doc) - 1):
        first, second = doc[i], doc[i + 1]
        if first.is_space or second.is_space or first.is_punct or second.is_punct:
            continue
        fc = canonical_spacy_token(first)
        sc = canonical_spacy_token(second)
        if not fc or not sc:
            continue
        canonical = f"{fc} {sc}"
        original = f"{first.text} {second.text}"
        display[canonical][original] += 1
        if i + 2 < len(doc):
            third = doc[i + 2]
            if not (third.is_space or third.is_punct):
                tc = canonical_spacy_token(third)
                if tc:
                    display[f"{fc} {sc} {tc}"][f"{first.text} {second.text} {third.text}"] += 1
    return display


def match_requirement(term, cv_index, cv_text=""):
    target = canonical_term(term)
    if not target:
        return None, "missing", 0.0, 0
    full_text = cv_index.get("__full_text__", "")
    if not full_text and cv_text:
        full_text = normalize_cv_for_matching(cv_text)
    best_alias, best_count = None, 0
    for alias in term_aliases(target):
        count = normalized_occurrences(full_text, alias)
        if count > best_count:
            best_alias, best_count = alias, count
    if best_alias and best_count > 0:
        return best_alias, "exact", 100.0, best_count
    return None, "missing", 0.0, 0


def find_evidence_sentence(matched_term, cv_text):
    if not matched_term or not cv_text:
        return ""
    target = canonical_term(matched_term)
    if not target:
        return ""
    aliases = term_aliases(target)
    doc = nlp(cv_text)
    for sent in doc.sents:
        sn = normalize_cv_for_matching(sent.text)
        for alias in aliases:
            if normalized_occurrences(sn, alias) > 0:
                return sent.text.strip()
    return ""


def calculate_coverage(job_count, cv_count):
    if job_count <= 0 or cv_count <= 0:
        return 0.0
    return min(cv_count / job_count, 1.0) * 100


def coverage_status(job_count, cv_count):
    if cv_count <= 0:
        return "MISSING"
    if cv_count < job_count:
        return "NEEDS REVIEW"
    return "COVERED"


def make_term_record(term, job_count, cv_index, cv_display_index, cv_text):
    matched_key, match_method, match_confidence, cv_count = match_requirement(
        term, cv_index, cv_text
    )
    matched_term = "—"
    if matched_key:
        examples = cv_display_index.get(canonical_term(matched_key), {})
        matched_term = max(examples, key=examples.get) if examples else matched_key
    coverage = calculate_coverage(job_count, cv_count)
    evidence = find_evidence_sentence(matched_key, cv_text) if matched_key else ""
    return {
        "term": term,
        "matched_term": matched_term,
        "job_count": job_count,
        "resume_count": cv_count,
        "coverage": round(coverage, 2),
        "status": coverage_status(job_count, cv_count),
        "match_method": match_method,
        "match_confidence": round(match_confidence, 2),
        "evidence_sentence": evidence,
    }


def classify_term(term, full_text=""):
    canonical = canonical_term(term)
    if not canonical:
        return "other"
    hard_phrases = {
        "data quality", "data system", "data systems", "data management",
        "data analysis", "data analytics", "data visualization",
        "data visualisation", "data collection", "data reporting",
        "data dashboard", "data integrity", "data validation", "data cleaning",
        "performance monitoring", "programme monitoring", "program monitoring",
        "programme performance", "program performance",
        "project management", "programme management", "program management",
        "database management", "structured database", "result database",
        "results database", "result framework", "results framework",
        "advanced excel", "power bi", "quality assurance",
        "research ethics", "qualitative research", "quantitative research",
        "research methodology", "research methods", "policy development",
        "policy analysis", "programme design", "program design",
        "business intelligence", "data quality assessment",
        "monitoring system", "digital system", "information system",
        "digital data collection", "information management",
        "capacity development", "theory of change",
    }
    soft_phrases = {
        "decision making", "problem solving", "stakeholder engagement",
        "technical writing", "interpersonal communication",
        "written communication", "verbal communication",
        "team leadership", "relationship management",
    }
    if canonical in hard_phrases:
        return "hard"
    if canonical in soft_phrases:
        return "soft"
    words = set(canonical.split())
    if words & TECHNICAL_TERMS:
        return "hard"
    hard_signal = {
        "analytics", "analysis", "analytical", "statistic", "statistics",
        "statistical", "database", "sql", "dataset", "dashboard",
        "visualisation", "visualization", "evaluation", "measurement",
        "technology", "programming", "coding", "automation", "compliance",
        "research", "survey", "surveys", "finance", "financial", "budget",
        "budgets", "procurement", "operations", "logistics", "planning",
        "strategy", "strategic", "documentation", "engineering", "policy",
        "quality", "technical", "reporting", "management", "indicator",
        "framework", "validation", "cleaning", "integrity", "monitoring",
        "system", "platform", "performance", "collection", "project",
        "programme", "program",
    }
    if words & hard_signal:
        return "hard"
    if words & SOFT_CUES:
        return "soft"
    return "other"


# ============================================================
# HIGHLIGHTING
# ============================================================

def highlight_job_description(text, classified_terms):
    if not text:
        return ""
    terms = sorted(classified_terms, key=lambda x: len(x["term"]), reverse=True)
    escaped = html.escape(text)
    placeholders = {}
    idx = 0
    for item in terms:
        term = item["term"]
        if not term:
            continue
        css = f"jd-{item['category']}"
        pattern = re.compile(
            r"(?<![A-Za-z0-9])" + re.escape(html.escape(term)) + r"(?![A-Za-z0-9])", re.I
        )
        def repl(m, _idx=idx, _term=term, _css=css):
            nonlocal idx
            ph = f"___JDMATCH_{idx}___"
            idx += 1
            placeholders[ph] = (
                f'<span class="{_css}" data-term="{html.escape(_term)}">'
                f"{m.group(0)}</span>"
            )
            return ph
        escaped = pattern.sub(repl, escaped)
    for ph, rep in placeholders.items():
        escaped = escaped.replace(ph, rep)
    return escaped.replace("\n", "<br>")


def highlight_cv_text(text, classified_terms):
    if not text:
        return ""
    escaped = html.escape(text)
    placeholders = {}
    idx = 0
    usable = [
        item for item in classified_terms
        if item.get("status") in {"COVERED", "NEEDS REVIEW"}
        and item.get("matched_term") not in {None, "", "—"}
    ]
    usable.sort(key=lambda x: len(x.get("matched_term", "")), reverse=True)
    for item in usable:
        matched = item.get("matched_term", "")
        if not matched:
            continue
        css = f"cv-{item.get('category', 'other')}"
        for alias in sorted(term_aliases(matched), key=len, reverse=True):
            if not alias:
                continue
            pattern = re.compile(
                r"(?<![A-Za-z0-9])" + re.escape(html.escape(alias)) + r"(?![A-Za-z0-9])", re.I
            )
            def repl(m, _idx=idx, _term=item["term"], _css=css):
                nonlocal idx
                ph = f"___CVMATCH_{idx}___"
                idx += 1
                placeholders[ph] = (
                    f'<span class="{_css}" data-term="{html.escape(_term)}">'
                    f"{m.group(0)}</span>"
                )
                return ph
            escaped = pattern.sub(repl, escaped)
    for ph, rep in placeholders.items():
        escaped = escaped.replace(ph, rep)
    return escaped.replace("\n", "<br>")


# ============================================================
# SCORING – Missing items lower the percentage
# ============================================================

def category_score(items):
    if not items:
        return None
    total = sum(item["coverage"] for item in items)
    return round(total / len(items), 1)


def overall_score(hard_score, soft_score, other_score):
    scores = []
    if hard_score is not None:
        scores.append((hard_score, 0.55))
    if soft_score is not None:
        scores.append((soft_score, 0.25))
    if other_score is not None:
        scores.append((other_score, 0.20))
    if not scores:
        return 0
    tw = sum(w for _, w in scores)
    return round(sum(s * w for s, w in scores) / tw) if tw > 0 else 0


def result_sort_key(item):
    order = {"MISSING": 0, "NEEDS REVIEW": 1, "COVERED": 2}
    return (order.get(item.get("status"), 3), -item.get("job_count", 0), item.get("term", ""))


def extract_year_requirements(text):
    reqs = []
    patterns = [
        r"(\d+)\+?\s*(?:years?|yrs?)\s+(?:of\s+)?experience",
        r"minimum\s+(\d+)\s*(?:years?|yrs?)",
        r"at\s+least\s+(\d+)\s*(?:years?|yrs?)",
        r"(\d+)\+?\s*(?:years?|yrs?)\s+in",
    ]
    for p in patterns:
        for m in re.findall(p, text, re.I):
            try:
                reqs.append(int(m))
            except (ValueError, TypeError):
                pass
    return sorted(set(reqs))


def extract_education_requirements(text):
    patterns = [
        r"\bphd\b", r"\bdoctorate\b", r"\bmaster(?:'s)?\b",
        r"\bmsc\b", r"\bma\b", r"\bmba\b",
        r"\bbachelor(?:'s)?\b", r"\bbsc\b", r"\bba\b",
        r"\bdiploma\b", r"\bcertificate\b",
    ]
    found = []
    for p in patterns:
        found.extend(m.lower() for m in re.findall(p, text, re.I))
    return list(dict.fromkeys(found))


def extract_certification_requirements(text):
    patterns = [
        r"\bPMP\b", r"\bCPA\b", r"\bACCA\b", r"\bCFA\b",
        r"\bCISA\b", r"\bCISM\b", r"\bPRINCE2\b",
        r"\bcertified\b", r"\bcertification\b", r"\blicen[cs]e\b",
    ]
    found = []
    for p in patterns:
        found.extend(m.lower() for m in re.findall(p, text, re.I))
    return list(dict.fromkeys(found))


# ============================================================
# MAIN ENGINE
# ============================================================

def analyze_cv_against_job(cv_text, job_description):
    if not cv_text or not cv_text.strip():
        raise ValueError("CV text is empty.")
    if not job_description or not job_description.strip():
        raise ValueError("Job description is empty.")

    cv_text = cv_text.strip()
    job_description = job_description.strip()

    discovered = extract_job_requirements(job_description)
    jd_counter = Counter()
    for term in discovered:
        cnt = normalized_occurrences(job_description, term)
        if cnt > 0:
            jd_counter[canonical_term(term)] = cnt

    cv_index = build_cv_evidence_index(cv_text)
    cv_display = build_cv_display_index(cv_text)

    hard_items, soft_items, other_items, all_items = [], [], [], []

    for term, job_count in jd_counter.items():
        cat = classify_term(term, job_description)
        rec = make_term_record(term, job_count, cv_index, cv_display, cv_text)
        rec["category"] = cat
        all_items.append(rec)
        if cat == "hard":
            hard_items.append(rec)
        elif cat == "soft":
            soft_items.append(rec)
        else:
            other_items.append(rec)

    hard_items.sort(key=result_sort_key)
    soft_items.sort(key=result_sort_key)
    other_items.sort(key=result_sort_key)
    all_items.sort(key=result_sort_key)

    hard_score = category_score(hard_items)
    soft_score = category_score(soft_items)
    other_score = category_score(other_items)
    match_score = overall_score(hard_score, soft_score, other_score)

    covered = sum(1 for i in all_items if i["status"] == "COVERED")
    needs_review = sum(1 for i in all_items if i["status"] == "NEEDS REVIEW")
    missing = sum(1 for i in all_items if i["status"] == "MISSING")

    if match_score >= 85:
        score_label = "Excellent Match"
    elif match_score >= 75:
        score_label = "Strong Match"
    elif match_score >= 60:
        score_label = "Good Match"
    elif match_score >= 45:
        score_label = "Moderate Match"
    else:
        score_label = "Low Match"

    return {
        "match_score": match_score,
        "score_label": score_label,
        "scores": {
            "hard": hard_score if hard_score is not None else 0,
            "soft": soft_score if soft_score is not None else 0,
            "other": other_score if other_score is not None else 0,
        },
        "score_availability": {
            "hard_available": sum(
                1 for i in hard_items if i["status"] in {"COVERED", "NEEDS REVIEW"}
            ),
            "soft_available": sum(
                1 for i in soft_items if i["status"] in {"COVERED", "NEEDS REVIEW"}
            ),
            "other_available": sum(
                1 for i in other_items if i["status"] in {"COVERED", "NEEDS REVIEW"}
            ),
        },
        "counts": {
            "all": len(all_items),
            "available": covered + needs_review,
            "covered": covered,
            "needs_review": needs_review,
            "missing": missing,
        },
        "hard_skills": hard_items,
        "soft_skills": soft_items,
        "other_requirements": other_items,
        "requirements": all_items,
        "terms": all_items,
        "missing_terms": [i["term"] for i in all_items if i["status"] == "MISSING"],
        "available_terms": [
            i["term"] for i in all_items if i["status"] in {"COVERED", "NEEDS REVIEW"}
        ],
        "highlighted_jd": highlight_job_description(job_description, all_items),
        "highlighted_cv": highlight_cv_text(cv_text, all_items),
        "years_required": extract_year_requirements(job_description),
        "education_required": extract_education_requirements(job_description),
        "certification_required": extract_certification_requirements(job_description),
    }