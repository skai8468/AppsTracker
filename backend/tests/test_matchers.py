"""Gmail matcher tests — pure functions, no I/O."""
from __future__ import annotations

from app.gmail import matchers


def test_extract_domain():
    assert matchers.extract_domain("Careers <no-reply@dbs.com>") == "dbs.com"
    assert matchers.extract_domain("hr@global-bank.com.sg") == "global-bank.com.sg"
    assert matchers.extract_domain("not an email") is None


def test_domain_matches_exact_and_subdomain():
    assert matchers.domain_matches("dbs.com", ["dbs.com"])
    assert matchers.domain_matches("careers.dbs.com", ["dbs.com"])
    assert not matchers.domain_matches("dbsfake.com", ["dbs.com"])
    assert not matchers.domain_matches("dbs.com", ["ocbc.com"])


def test_confirmation_detection():
    assert matchers.looks_like_confirmation("We have received your application", "")
    assert matchers.looks_like_confirmation("Re: role", "Thank you for applying to Acme")
    assert not matchers.looks_like_confirmation(
        "Interview invitation", "We'd like to schedule a call"
    )
