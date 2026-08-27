"""Declarative, pure matching rules for incoming email — no I/O, easy to unit-test.

Two questions the poller asks of every message:

1. Which tracked company (if any) does the sender domain belong to?
2. Does this look like an application *confirmation* (so we can auto-flip the stage)?

Everything else — interview / offer / reject — is deliberately left for the user to
one-tap classify, because those emails are too free-form to auto-parse reliably.
"""
from __future__ import annotations

import re
from typing import Optional

# Subject/snippet phrases that strongly indicate "we received your application".
CONFIRMATION_PATTERNS = (
    "application received",
    "we have received your application",
    "thank you for applying",
    "thank you for your application",
    "application has been received",
    "successfully applied",
    "application submitted",
    "received your submission",
    "thanks for applying",
    "your application to",
    "your application for",
    "application received",
)

# Transactional mail that arrives from a tracked company's domain but says nothing about
# an application — portal logins, password resets, job alerts. Matching the domain is not
# enough to make these interesting, and they otherwise fill the inbox and fire Telegram.
NOISE_PATTERNS = (
    "verification code",
    "verify your email",
    "verify your account",
    "confirm your email",
    "one-time password",
    "one time passcode",
    "security code",
    "sign-in attempt",
    "sign in attempt",
    "new sign-in",
    "login attempt",
    "reset your password",
    "password reset",
    "password has been changed",
    "your otp",
    "two-factor",
    "job alert",
    "jobs you may",
    "recommended jobs",
    "new jobs matching",
    "unsubscribe from job",
)

_EMAIL_RE = re.compile(r"[\w.+-]+@([\w-]+\.[\w.-]+)")


def extract_domain(from_header: str) -> str | None:
    """Pull the domain out of a From header like 'Careers <no-reply@dbs.com>'."""
    m = _EMAIL_RE.search(from_header or "")
    return m.group(1).lower() if m else None


def domain_matches(sender_domain: str, company_domains: list[str]) -> bool:
    """True if sender_domain equals or is a subdomain of any tracked company domain."""
    sd = (sender_domain or "").lower()
    for cd in company_domains:
        cd = cd.lower().strip()
        if not cd:
            continue
        if sd == cd or sd.endswith("." + cd):
            return True
    return False


def looks_like_confirmation(subject: str, snippet: str) -> bool:
    text = f"{subject or ''} {snippet or ''}".lower()
    return any(p in text for p in CONFIRMATION_PATTERNS)


def looks_like_noise(subject: str, snippet: str) -> bool:
    """Transactional mail from a tracked domain that isn't about an application.

    Callers must test ``looks_like_confirmation`` first: a genuine confirmation can also
    ask you to verify your email address, and the confirmation reading has to win.
    """
    text = f"{subject or ''} {snippet or ''}".lower()
    return any(p in text for p in NOISE_PATTERNS)


# --- picking *which* application an email is about -------------------------------------
#
# With several open roles at one employer, the company match alone isn't enough. Two
# signals separate them: the requisition id carried in the posting URL (near-conclusive
# when it appears), and how much of the role title shows up in the email text.

_TOKEN_RE = re.compile(r"[a-z0-9]+")

# Words too common across job ads to distinguish two roles at the same company.
_GENERIC_TOKENS = frozenset({
    "the", "and", "for", "with", "new", "job", "jobs", "role", "roles", "position",
    "programme", "program", "graduate", "grad", "intern", "internship", "full", "time",
    "apply", "application", "applications", "opportunity", "career", "careers", "team",
    "singapore", "sgp", "asia", "pacific", "apac",
})

# A posting URL's id is usually 4+ digits ("higher.gs.com/roles/170769"); shorter runs are
# more often years or office numbers.
_REF_RE = re.compile(r"\d{4,}")


def title_tokens(title: str) -> set[str]:
    """Distinctive lowercase words from a role title."""
    return {
        t for t in _TOKEN_RE.findall((title or "").lower())
        if len(t) >= 3 and t not in _GENERIC_TOKENS
    }


def title_match_score(title: str, text: str) -> float:
    """Fraction of a title's distinctive words present in ``text`` (0.0 - 1.0)."""
    tokens = title_tokens(title)
    if not tokens:
        return 0.0
    lowered = (text or "").lower()
    return sum(1 for t in tokens if t in lowered) / len(tokens)


# --- pulling a role and employer out of a confirmation email ---------------------------
#
# Used when a confirmation arrives from a sender we don't track yet, so the application can
# be created from the email instead of being typed in by hand.

# Ordered: the more specific phrasing has to be tried before the looser one.
_TITLE_PATTERNS = (
    r"thank you for (?:your interest and )?applying (?:to|for)(?: the)?\s+(.+)",
    r"thanks for applying (?:to|for)(?: the)?\s+(.+)",
    r"we(?:'ve| have) received your application (?:to|for)(?: the)?\s+(.+)",
    r"your application (?:to|for)(?: the)?\s+(.+)",
    r"application (?:received|submitted)(?:\s*[:\-–]\s*)(.+)",
    r"application for(?: the)?\s+(.+)",
)

# Trailing noise on an extracted title: "… at Acme", "… position", "… has been received".
# Parenthesised suffixes are KEPT — real titles carry them ("Test Engineer Intern (AI)").
_TITLE_TAIL_RE = re.compile(
    r"\s+(?:at|with|@)\s+.+$"
    r"|\s+(?:position|role|opening|vacancy|req(?:uisition)?)\b.*$"
    r"|\s+(?:has|have|had|was|were|is|are)\s+been\s+\w+.*$"
    r"|\s+(?:has|have|was|were|is|are)\s+\w+ed\b.*$",
    re.IGNORECASE,
)

# Function-mailbox words that aren't part of the employer's name.
_SENDER_NOISE_RE = re.compile(
    r"\b(?:recruit(?:ing|ment)?|careers?|talent(?:\s+acquisition)?|hiring|jobs?|hr|people"
    r"|no[\s-]?reply|do[\s-]?not[\s-]?reply|notifications?|team|via|support|mailer|info)\b",
    re.IGNORECASE,
)

_DISPLAY_NAME_RE = re.compile(r"^\s*\"?([^\"<]+?)\"?\s*<")


def extract_role_title(
    subject: str, snippet: str = "", company: Optional[str] = None
) -> Optional[str]:
    """Best-effort role title from a confirmation email, or None if it names no role.

    ``company`` is used to reject "Thank you for applying to Sea!", where the thing after
    "applying to" is the employer, not a job.
    """
    for source in (subject or "", snippet or ""):
        low = source.lower()
        for pat in _TITLE_PATTERNS:
            m = re.search(pat, low)
            if not m:
                continue
            # Slice the ORIGINAL text so the title keeps its capitalisation.
            title = source[m.start(1) : m.end(1)]
            # Confirmations often run on: "... Analyst. We'll be in touch."
            # Deliberately not split on "|" — real titles use it ("Audit | New Analyst").
            title = re.split(r"[.!?\n]|\s[–—]\s", title)[0]
            title = _TITLE_TAIL_RE.sub("", title).strip(" ,;:-–—\"'!")
            if not (2 < len(title) <= 120):
                continue
            if company and title.strip().lower() == company.strip().lower():
                continue  # that's the employer, not the role
            return title
    return None


def company_from_sender(from_header: str, domain: str) -> str:
    """Employer name from the From display name, falling back to the domain."""
    m = _DISPLAY_NAME_RE.match(from_header or "")
    if m:
        name = _SENDER_NOISE_RE.sub("", m.group(1))
        name = re.sub(r"\s{2,}", " ", name).strip(" -|,·•")
        if len(name) > 1 and not _EMAIL_RE.search(name):
            return name
    # "careers.tiktok.com" -> "Tiktok": drop the public suffix and any leading label.
    parts = [p for p in (domain or "").split(".") if p]
    if not parts:
        return "Unknown"
    label = parts[-2] if len(parts) >= 2 else parts[0]
    # Handle "gs.com.sg" style: skip well-known second-level suffixes.
    if label in {"com", "co", "org", "net", "gov", "edu"} and len(parts) >= 3:
        label = parts[-3]
    return label.replace("-", " ").title()


def url_ref_ids(url: str) -> set[str]:
    return set(_REF_RE.findall(url or ""))


def ref_in_text(url: str, text: str) -> bool:
    """True if a requisition id from the posting URL appears in the email."""
    lowered = (text or "").lower()
    return any(ref in lowered for ref in url_ref_ids(url))
