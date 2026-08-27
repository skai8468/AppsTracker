"""Declarative, pure matching rules for incoming email — no I/O, easy to unit-test.

Two questions the poller asks of every message:

1. Which tracked company (if any) does the sender domain belong to?
2. Does this look like an application *confirmation* (so we can auto-flip the stage)?

Everything else — interview / offer / reject — is deliberately left for the user to
one-tap classify, because those emails are too free-form to auto-parse reliably.
"""
from __future__ import annotations

import re

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


def url_ref_ids(url: str) -> set[str]:
    return set(_REF_RE.findall(url or ""))


def ref_in_text(url: str, text: str) -> bool:
    """True if a requisition id from the posting URL appears in the email."""
    lowered = (text or "").lower()
    return any(ref in lowered for ref in url_ref_ids(url))
