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
