
import re
import html
from functools import lru_cache
from collections import defaultdict

try:
    from .data import SKILL_GROUPS
except ImportError:
    from data import SKILL_GROUPS


# ============================================================
# CONFIGURATION
# ============================================================

SKILL_WEIGHTS = {
    "hard": 0.50,
    "soft": 0.30,
    "other": 0.20,
}

CATEGORY_ORDER = ("hard", "soft", "other")

STATUS_ORDER = {
    "MISSING": 0,
    "NEEDS REVIEW": 1,
    "COVERED": 2,
}

MIN_TERM_LENGTH = 1


# ============================================================
# NORMALIZATION
# ============================================================

PLURAL_EXCEPTIONS = {
    "analyses": "analysis",
    "databases": "database",
    "dashboards": "dashboard",
    "indicators": "indicator",
    "stakeholders": "stakeholder",
    "communications": "communication",
    "presentations": "presentation",
    "systems": "system",
    "processes": "process",
    "policies": "policy",
    "activities": "activity",
    "surveys": "survey",
    "reports": "report",
    "projects": "project",
    "programmes": "programme",
    "programs": "program",
    "budgets": "budget",
    "frameworks": "framework",
    "results": "result",
    "tools": "tool",
    "services": "service",
    "solutions": "solution",
    "skills": "skill",
    "degrees": "degree",
    "certifications": "certification",
    "requirements": "requirement",
    "qualifications": "qualification",
    "responsibilities": "responsibility",
    "deliverables": "deliverable",
    "procedures": "procedure",
    "strategies": "strategy",
    "technologies": "technology",
    "methodologies": "methodology",
    "analyses": "analysis",
    "indices": "index",
    "matrices": "matrix",
    "criteria": "criterion",
    "data": "data",
    "people": "people",
    "children": "child",
    "women": "woman",
    "men": "man",
    "mice": "mouse",
    "geese": "goose",
    "staff": "staff",
    "series": "series",
    "species": "species",
    "businesses": "business",
    "companies": "company",
    "countries": "country",
    "counties": "county",
    "facilities": "facility",
    "communities": "community",
    "policies": "policy",
    "opportunities": "opportunity",
    "capacities": "capacity",
    "priorities": "priority",
    "activities": "activity",
    "organizations": "organization",
    "organisations": "organisation",
}


def normalize_text(text):
    if text is None:
        return ""

    if not isinstance(text, str):
        text = str(text)

    text = html.unescape(text).lower()

    text = (
        text.replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace("\u2010", "-")
        .replace("\u2011", "-")
        .replace("\u2012", "-")
        .replace("\u2015", "-")
        .replace("\u2212", "-")
    )

    text = text.replace("&", " and ")
    text = text.replace("/", " / ")
    text = text.replace("-", " ")

    # Preserve common technical characters such as +, # and dots.
    text = re.sub(r"[^a-z0-9+#.\s]", " ", text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


@lru_cache(maxsize=100000)
def normalize_token(token):
    token = normalize_text(token)

    if not token:
        return ""

    if token in PLURAL_EXCEPTIONS:
        return PLURAL_EXCEPTIONS[token]

    if token.endswith("ies") and len(token) > 4:
        return token[:-3] + "y"

    if token.endswith("sses") and len(token) > 5:
        return token[:-2]

    if (
        token.endswith("s")
        and not token.endswith(("ss", "us", "is"))
        and len(token) > 3
    ):
        return token[:-1]

    return token


@lru_cache(maxsize=100000)
def canonical_term(term):
    normalized = normalize_text(term)

    if not normalized:
        return ""

    return " ".join(
        normalize_token(word)
        for word in normalized.split()
    )


def normalize_for_matching(text):
    normalized = normalize_text(text)

    if not normalized:
        return ""

    return " ".join(
        normalize_token(word)
        for word in normalized.split()
    )


# ============================================================
# SKILL GROUP PREPARATION
# ============================================================

def flatten_skill_group(value):
    results = []

    if isinstance(value, str):
        if value.strip():
            results.append(value.strip())

    elif isinstance(value, dict):
        for nested_value in value.values():
            results.extend(flatten_skill_group(nested_value))

    elif isinstance(value, (list, tuple, set)):
        for item in value:
            results.extend(flatten_skill_group(item))

    return results


def load_skill_groups():
    groups = {
        "hard": [],
        "soft": [],
        "other": [],
    }

    for category in CATEGORY_ORDER:
        source = SKILL_GROUPS.get(category, [])
        terms = flatten_skill_group(source)
        seen = set()

        for term in terms:
            canonical = canonical_term(term)

            if not canonical or canonical in seen:
                continue

            if len(canonical.split()) < MIN_TERM_LENGTH:
                continue

            seen.add(canonical)

            groups[category].append({
                "term": term,
                "canonical": canonical,
                "category": category,
            })

    return groups


SKILL_LOOKUP = load_skill_groups()


# ============================================================
# FAST MULTI-PHRASE MATCHING
# ============================================================

def build_phrase_trie(items):
    """
    Build a token trie for efficient matching against large
    dictionaries.

    This avoids scanning the full job description separately
    for every dictionary entry.
    """
    root = {}

    for item in items:
        tokens = item["canonical"].split()

        if not tokens:
            continue

        node = root

        for token in tokens:
            node = node.setdefault(token, {})

        node.setdefault("__items__", []).append(item)

    return root


def get_all_skill_items():
    return [
        item
        for category in CATEGORY_ORDER
        for item in SKILL_LOOKUP.get(category, [])
    ]


ALL_SKILL_ITEMS = get_all_skill_items()
SKILL_TRIE = build_phrase_trie(ALL_SKILL_ITEMS)


def tokenize_normalized(text):
    normalized = normalize_for_matching(text)

    if not normalized:
        return []

    return normalized.split()


def count_all_phrases(text, trie=None):
    """
    Count all recognized phrases in a text in one pass.

    Returns:
        {
            (category, canonical_term): occurrence_count
        }

    The trie allows the number of dictionary entries to grow
    substantially without requiring one full-text regex scan
    for every entry.
    """
    if not text:
        return {}

    if trie is None:
        trie = SKILL_TRIE

    tokens = tokenize_normalized(text)

    if not tokens:
        return {}

    counts = defaultdict(int)
    token_count = len(tokens)

    for start in range(token_count):
        node = trie

        for position in range(start, token_count):
            token = tokens[position]

            if token not in node:
                break

            node = node[token]

            terminal_items = node.get("__items__")

            if terminal_items:
                for item in terminal_items:
                    key = (
                        item["category"],
                        item["canonical"],
                    )
                    counts[key] += 1

    return dict(counts)


# ============================================================
# PHRASE MATCHING HELPERS
# ============================================================

@lru_cache(maxsize=100000)
def phrase_pattern(term):
    normalized = normalize_for_matching(term)

    if not normalized:
        return None

    words = normalized.split()
    phrase = r"\s+".join(
        re.escape(word)
        for word in words
    )

    return re.compile(
        r"(?<![a-z0-9])" + phrase + r"(?![a-z0-9])",
        flags=re.I,
    )


def count_phrase_occurrences(text, term):
    if not text or not term:
        return 0

    normalized_text = normalize_for_matching(text)
    normalized_term = normalize_for_matching(term)

    if not normalized_text or not normalized_term:
        return 0

    pattern = phrase_pattern(normalized_term)

    if pattern is None:
        return 0

    return sum(1 for _ in pattern.finditer(normalized_text))


def find_phrase_matches(text, term):
    if not text or not term:
        return []

    pattern = phrase_pattern(term)

    if pattern is None:
        return []

    return list(
        pattern.finditer(
            normalize_for_matching(text)
        )
    )


@lru_cache(maxsize=100000)
def original_phrase_pattern(term):
    """
    Precompile a pattern that recognizes common singular and
    plural forms in the original text.
    """
    words = normalize_text(term).split()

    if not words:
        return None

    token_patterns = []

    for word in words:
        canonical = normalize_token(word)

        variants = {
            re.escape(word),
            re.escape(canonical),
        }

        if canonical.endswith("y") and len(canonical) > 2:
            variants.add(
                re.escape(canonical[:-1] + "ies")
            )
        else:
            variants.add(
                re.escape(canonical + "s")
            )

        token_patterns.append(
            "(?:" +
            "|".join(
                sorted(variants, key=len, reverse=True)
            ) +
            ")"
        )

    phrase = r"[\s\-/]+".join(token_patterns)

    return re.compile(
        r"(?<![a-z0-9])" + phrase + r"(?![a-z0-9])",
        flags=re.I,
    )


def find_original_phrase_matches(text, term):
    if not text or not term:
        return []

    pattern = original_phrase_pattern(term)

    if pattern is None:
        return []

    return list(pattern.finditer(text))


# ============================================================
# REQUIREMENT DISCOVERY
# ============================================================

def extract_job_requirements(job_description):
    if not job_description:
        return []

    counts = count_all_phrases(job_description)
    discovered = []

    for item in ALL_SKILL_ITEMS:
        count = counts.get(
            (item["category"], item["canonical"]),
            0,
        )

        if count <= 0:
            continue

        discovered.append({
            "term": item["term"],
            "canonical": item["canonical"],
            "category": item["category"],
            "job_count": count,
        })

    discovered.sort(
        key=lambda item: (
            -len(item["canonical"].split()),
            -len(item["canonical"]),
            item["term"].lower(),
        )
    )

    return discovered


# ============================================================
# CLASSIFICATION
# ============================================================

TERM_CLASSIFICATION = {}

for category in CATEGORY_ORDER:
    for item in SKILL_LOOKUP.get(category, []):
        TERM_CLASSIFICATION.setdefault(
            item["canonical"],
            category,
        )


def classify_term(term, full_text=""):
    """
    Classify a term using the loaded skill groups.

    The optional full_text parameter is retained for compatibility.
    """
    canonical = canonical_term(term)

    return TERM_CLASSIFICATION.get(canonical, "other")


# ============================================================
# CV MATCHING
# ============================================================

def match_requirement(term, cv_text):
    cv_count = count_phrase_occurrences(
        cv_text,
        term,
    )

    if cv_count > 0:
        return {
            "matched_term": term,
            "match_method": "exact_normalized",
            "match_confidence": 100.0,
            "resume_count": cv_count,
        }

    return {
        "matched_term": "—",
        "match_method": "missing",
        "match_confidence": 0.0,
        "resume_count": 0,
    }


def match_requirements_batch(requirements, cv_text):
    """
    Match all requirements against the CV using one trie pass.
    """
    cv_counts = count_all_phrases(cv_text)
    results = {}

    for requirement in requirements:
        key = (
            requirement["category"],
            requirement["canonical"],
        )

        count = cv_counts.get(key, 0)

        results[key] = {
            "matched_term": (
                requirement["term"]
                if count > 0
                else "—"
            ),
            "match_method": (
                "exact_normalized"
                if count > 0
                else "missing"
            ),
            "match_confidence": (
                100.0
                if count > 0
                else 0.0
            ),
            "resume_count": count,
        }

    return results


# ============================================================
# COVERAGE AND STATUS
# ============================================================

def calculate_coverage(job_count, resume_count):
    if job_count <= 0:
        return 0.0

    return round(
        min(resume_count / job_count, 1.0) * 100,
        2,
    )


def coverage_status(job_count, resume_count):
    if resume_count <= 0:
        return "MISSING"

    if resume_count < job_count:
        return "NEEDS REVIEW"

    return "COVERED"


# ============================================================
# EVIDENCE
# ============================================================

def find_evidence_sentence(term, cv_text):
    if not term or not cv_text:
        return ""

    sentences = re.split(
        r"(?<=[.!?])\s+|\n+",
        cv_text,
    )

    for sentence in sentences:
        if count_phrase_occurrences(sentence, term) > 0:
            return sentence.strip()

    return ""


# ============================================================
# REQUIREMENT RECORD
# ============================================================

def make_term_record(requirement, cv_text, match=None):
    term = requirement["term"]
    job_count = requirement["job_count"]
    category = requirement["category"]

    if match is None:
        match = match_requirement(
            requirement["canonical"],
            cv_text,
        )

    resume_count = match["resume_count"]

    coverage = calculate_coverage(
        job_count,
        resume_count,
    )

    status = coverage_status(
        job_count,
        resume_count,
    )

    evidence = ""

    if resume_count > 0:
        evidence = find_evidence_sentence(
            requirement["canonical"],
            cv_text,
        )

    return {
        "term": term,
        "matched_term": (
            term if resume_count > 0 else "—"
        ),
        "category": category,
        "job_count": job_count,
        "resume_count": resume_count,
        "coverage": coverage,
        "status": status,
        "match_method": match["match_method"],
        "match_confidence": match["match_confidence"],
        "evidence_sentence": evidence,
    }


# ============================================================
# SCORING
# ============================================================

def category_score(items):
    """
    Include every requirement in the category.
    Missing requirements contribute zero.
    """
    if not items:
        return None

    return round(
        sum(
            item["coverage"]
            for item in items
        ) / len(items),
        1,
    )


def overall_score(hard_score, soft_score, other_score):
    """
    Use configured category weights.
    Categories with no identified requirements are excluded,
    and the remaining weights are normalized.
    """
    scores = {
        "hard": hard_score,
        "soft": soft_score,
        "other": other_score,
    }

    available = {
        category: score
        for category, score in scores.items()
        if score is not None
    }

    if not available:
        return 0

    total_weight = sum(
        SKILL_WEIGHTS[category]
        for category in available
    )

    if total_weight == 0:
        return 0

    result = sum(
        score * SKILL_WEIGHTS[category]
        for category, score in available.items()
    ) / total_weight

    return round(result)


# ============================================================
# SORTING
# ============================================================

def result_sort_key(item):
    return (
        STATUS_ORDER.get(
            item.get("status"),
            3,
        ),
        -item.get("job_count", 0),
        item.get("term", "").lower(),
    )


# ============================================================
# HIGHLIGHTING
# ============================================================

def highlight_text(text, requirements, prefix):
    if not text:
        return ""

    matches = []

    for item in requirements:
        term = item.get("term", "")
        category = item.get("category", "other")

        if not term:
            continue

        for match in find_original_phrase_matches(
            text,
            term,
        ):
            matches.append({
                "start": match.start(),
                "end": match.end(),
                "category": category,
                "term": term,
            })

    # Longest match first at a shared starting position.
    matches.sort(
        key=lambda item: (
            item["start"],
            -(item["end"] - item["start"]),
            item["category"],
        )
    )

    selected = []
    last_end = -1

    for item in matches:
        if item["start"] < last_end:
            continue

        selected.append(item)
        last_end = item["end"]

    output = []
    cursor = 0

    for item in selected:
        output.append(
            html.escape(
                text[cursor:item["start"]]
            )
        )

        category = item["category"]
        matched_text = text[
            item["start"]:item["end"]
        ]

        output.append(
            f'<span class="{prefix}-{category}" '
            f'data-term="{html.escape(item["term"], quote=True)}">'
            f'{html.escape(matched_text)}</span>'
        )

        cursor = item["end"]

    output.append(
        html.escape(text[cursor:])
    )

    return "".join(output).replace(
        "\n",
        "<br>",
    )


def highlight_job_description(text, classified_terms):
    return highlight_text(
        text,
        classified_terms,
        "jd",
    )


def highlight_cv_text(text, classified_terms):
    matched_terms = [
        item
        for item in classified_terms
        if item.get("status") in {
            "COVERED",
            "NEEDS REVIEW",
        }
    ]

    return highlight_text(
        text,
        matched_terms,
        "cv",
    )


# ============================================================
# OTHER REQUIREMENT EXTRACTION
# ============================================================

def extract_year_requirements(text):
    if not text:
        return []

    patterns = [
        r"\b(\d+)\+?\s*(?:years?|yrs?)\s+"
        r"(?:of\s+)?(?:relevant\s+)?experience\b",

        r"\bminimum\s+of?\s*(\d+)\s*"
        r"(?:years?|yrs?)\b",

        r"\bat\s+least\s+(\d+)\s*"
        r"(?:years?|yrs?)\b",

        r"\b(\d+)\+?\s*(?:years?|yrs?)\s+in\b",

        r"\b(\d+)\s*-\s*\d+\s*"
        r"(?:years?|yrs?)\s+experience\b",
    ]

    found = set()

    for pattern in patterns:
        for match in re.finditer(
            pattern,
            text,
            flags=re.I,
        ):
            try:
                found.add(int(match.group(1)))
            except (ValueError, TypeError):
                continue

    return sorted(found)


def extract_education_requirements(text):
    if not text:
        return []

    patterns = [
        r"\bph\.?\s*d\.?\b",
        r"\bdoctorate\b",
        r"\bdoctoral\b",
        r"\bmaster(?:'s)?\b",
        r"\bmasters\b",
        r"\bmsc\b",
        r"\bm\.?\s*sc\.?\b",
        r"\bma\b",
        r"\bm\.?\s*a\.?\b",
        r"\bmba\b",
        r"\bm\.?\s*b\.?\s*a\.?\b",
        r"\bpostgraduate\b",
        r"\bpost-graduate\b",
        r"\bbachelor(?:'s)?\b",
        r"\bbachelors\b",
        r"\bbsc\b",
        r"\bb\.?\s*sc\.?\b",
        r"\bba\b",
        r"\bb\.?\s*a\.?\b",
        r"\bundergraduate\b",
        r"\bdiploma\b",
        r"\bhigher diploma\b",
        r"\badvanced diploma\b",
        r"\bdegree\b",
        r"\bcertificate\b",
        r"\bprofessional qualification\b",
        r"\btertiary education\b",
        r"\btechnical qualification\b",
    ]

    found = []

    for pattern in patterns:
        found.extend(
            match.group(0).lower()
            for match in re.finditer(
                pattern,
                text,
                flags=re.I,
            )
        )

    return list(dict.fromkeys(found))


def extract_certification_requirements(text):
    if not text:
        return []

    patterns = [
        r"\bPMP\b",
        r"\bPRINCE2\b",
        r"\bCPA\b",
        r"\bACCA\b",
        r"\bCFA\b",
        r"\bCISA\b",
        r"\bCISM\b",
        r"\bCIPD\b",
        r"\bCIPS\b",
        r"\bSix\s+Sigma\b",
        r"\bLean\s+Six\s+Sigma\b",
        r"\bITIL\b",
        r"\bAWS\s+Certified\b",
        r"\bMicrosoft\s+Certified\b",
        r"\bGoogle\s+Certified\b",
        r"\bCisco\s+Certified\b",
        r"\bCompTIA\b",
        r"\bCCNA\b",
        r"\bCCNP\b",
        r"\bSHRM\b",
        r"\bPHR\b",
        r"\bSPHR\b",
        r"\bCHRP\b",
        r"\bCHRL\b",
        r"\bcertified\b",
        r"\bcertification\b",
        r"\bcertifications\b",
        r"\blicen[cs]e\b",
        r"\blicen[cs]ed\b",
        r"\bprofessional registration\b",
        r"\bmembership of\b",
        r"\bmember of\b",
    ]

    found = []

    for pattern in patterns:
        found.extend(
            match.group(0)
            for match in re.finditer(
                pattern,
                text,
                flags=re.I,
            )
        )

    return list(dict.fromkeys(found))


# ============================================================
# MAIN ANALYSIS
# ============================================================

def analyze_cv_against_job(cv_text, job_description):
    if not isinstance(cv_text, str):
        cv_text = str(cv_text or "")

    if not isinstance(job_description, str):
        job_description = str(
            job_description or ""
        )

    cv_text = cv_text.strip()
    job_description = job_description.strip()

    if not cv_text:
        raise ValueError(
            "CV text is empty."
        )

    if not job_description:
        raise ValueError(
            "Job description is empty."
        )

    # 1. Discover requirements from the JD.
    discovered = extract_job_requirements(
        job_description
    )

    # 2. Count all CV matches in one pass.
    cv_counts = count_all_phrases(
        cv_text
    )

    # 3. Create requirement records.
    all_items = []

    for requirement in discovered:
        key = (
            requirement["category"],
            requirement["canonical"],
        )

        resume_count = cv_counts.get(
            key,
            0,
        )

        match = {
            "matched_term": (
                requirement["term"]
                if resume_count > 0
                else "—"
            ),
            "match_method": (
                "exact_normalized"
                if resume_count > 0
                else "missing"
            ),
            "match_confidence": (
                100.0
                if resume_count > 0
                else 0.0
            ),
            "resume_count": resume_count,
        }

        all_items.append(
            make_term_record(
                requirement,
                cv_text,
                match=match,
            )
        )

    # 4. Separate categories.
    hard_items = [
        item
        for item in all_items
        if item["category"] == "hard"
    ]

    soft_items = [
        item
        for item in all_items
        if item["category"] == "soft"
    ]

    other_items = [
        item
        for item in all_items
        if item["category"] == "other"
    ]

    # 5. Sort requirements.
    hard_items.sort(
        key=result_sort_key
    )

    soft_items.sort(
        key=result_sort_key
    )

    other_items.sort(
        key=result_sort_key
    )

    all_items.sort(
        key=result_sort_key
    )

    # 6. Calculate category and overall scores.
    hard_score = category_score(
        hard_items
    )

    soft_score = category_score(
        soft_items
    )

    other_score = category_score(
        other_items
    )

    match_score = overall_score(
        hard_score,
        soft_score,
        other_score,
    )

    # 7. Count statuses.
    covered = sum(
        item["status"] == "COVERED"
        for item in all_items
    )

    needs_review = sum(
        item["status"] == "NEEDS REVIEW"
        for item in all_items
    )

    missing = sum(
        item["status"] == "MISSING"
        for item in all_items
    )

    available = covered + needs_review

    # 8. Missing and available keywords.
    missing_terms = list(
        dict.fromkeys(
            item["term"]
            for item in all_items
            if item["status"] == "MISSING"
        )
    )

    available_terms = list(
        dict.fromkeys(
            item["term"]
            for item in all_items
            if item["status"] in {
                "COVERED",
                "NEEDS REVIEW",
            }
        )
    )

    missing_terms_text = ", ".join(
        missing_terms
    )

    # 9. Highlight JD and CV.
    highlighted_jd = highlight_job_description(
        job_description,
        all_items,
    )

    highlighted_cv = highlight_cv_text(
        cv_text,
        all_items,
    )

    # 10. Score label.
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

    # 11. Return report data.
    return {
        "match_score": match_score,
        "score_label": score_label,

        "scores": {
            "hard": hard_score,
            "soft": soft_score,
            "other": other_score,
        },

        "weights": {
            "hard": 65,
            "soft": 25,
            "other": 10,
        },

        "counts": {
            "all": len(all_items),
            "available": available,
            "covered": covered,
            "needs_review": needs_review,
            "missing": missing,
            "hard": len(hard_items),
            "soft": len(soft_items),
            "other": len(other_items),
        },

        "hard_skills": hard_items,
        "soft_skills": soft_items,
        "other_requirements": other_items,

        "requirements": all_items,
        "terms": all_items,

        "missing_terms": missing_terms,
        "missing_terms_text": missing_terms_text,
        "available_terms": available_terms,

        "highlighted_jd": highlighted_jd,
        "highlighted_cv": highlighted_cv,

        "years_required": extract_year_requirements(
            job_description
        ),

        "education_required": extract_education_requirements(
            job_description
        ),

        "certification_required": extract_certification_requirements(
            job_description
        ),

        "discovery": {
            "method": "Token trie lookup from data.py",
            "dictionary_size": len(ALL_SKILL_ITEMS),
            "candidate_count": len(discovered),
            "final_requirement_count": len(all_items),
        },
    }


# ============================================================
# PUBLIC HELPERS
# ============================================================

def get_hard_skills(job_description):
    return [
        item
        for item in extract_job_requirements(
            job_description
        )
        if item["category"] == "hard"
    ]


def get_soft_skills(job_description):
    return [
        item
        for item in extract_job_requirements(
            job_description
        )
        if item["category"] == "soft"
    ]


def get_other_keywords(job_description):
    return [
        item
        for item in extract_job_requirements(
            job_description
        )
        if item["category"] == "other"
    ]


# ============================================================
# OPTIONAL DICTIONARY MANAGEMENT
# ============================================================

def refresh_skill_lookup():
    """
    Call this if SKILL_GROUPS is modified while the application
    is running.

    Rebuilds the normalized lookup and trie.
    """
    global SKILL_LOOKUP
    global ALL_SKILL_ITEMS
    global SKILL_TRIE
    global TERM_CLASSIFICATION

    SKILL_LOOKUP = load_skill_groups()

    ALL_SKILL_ITEMS = get_all_skill_items()

    SKILL_TRIE = build_phrase_trie(
        ALL_SKILL_ITEMS
    )

    TERM_CLASSIFICATION = {}

    for category in CATEGORY_ORDER:
        for item in SKILL_LOOKUP.get(
            category,
            [],
        ):
            TERM_CLASSIFICATION.setdefault(
                item["canonical"],
                category,
            )

    normalize_token.cache_clear()
    canonical_term.cache_clear()
    phrase_pattern.cache_clear()
    original_phrase_pattern.cache_clear()


def get_dictionary_statistics():
    """
    Return useful information about dictionary size.
    """
    return {
        "hard": len(
            SKILL_LOOKUP.get("hard", [])
        ),
        "soft": len(
            SKILL_LOOKUP.get("soft", [])
        ),
        "other": len(
            SKILL_LOOKUP.get("other", [])
        ),
        "total": len(
            ALL_SKILL_ITEMS
        ),
        "unique_canonical_terms": len(
            TERM_CLASSIFICATION
        ),
    }


# ============================================================
# EXPORTS
# ============================================================

__all__ = [
    "normalize_text",
    "normalize_token",
    "canonical_term",
    "normalize_for_matching",
    "flatten_skill_group",
    "load_skill_groups",
    "refresh_skill_lookup",
    "get_dictionary_statistics",
    "build_phrase_trie",
    "count_all_phrases",
    "extract_job_requirements",
    "classify_term",
    "count_phrase_occurrences",
    "find_phrase_matches",
    "find_original_phrase_matches",
    "match_requirement",
    "match_requirements_batch",
    "calculate_coverage",
    "coverage_status",
    "make_term_record",
    "highlight_text",
    "highlight_job_description",
    "highlight_cv_text",
    "category_score",
    "overall_score",
    "result_sort_key",
    "extract_year_requirements",
    "extract_education_requirements",
    "extract_certification_requirements",
    "analyze_cv_against_job",
    "get_hard_skills",
    "get_soft_skills",
    "get_other_keywords",
]