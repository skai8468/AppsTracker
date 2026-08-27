"""Gmail matcher tests — pure functions, no I/O."""
from __future__ import annotations

from app.gmail import matchers


# --- real confirmations seen in the wild ------------------------------------------------

def test_confirmation_wording_lives_in_the_body_not_the_subject():
    """Citi's subject only says "Thank you for your interest"; the proof is in the snippet."""
    subject = "Thank you for your interest in Citi!"
    snippet = (
        "Dear Shi Kai, Thank you for taking the time to apply for the role of "
        "Services - Full-Time Analyst, Singapore, 2027-26978. We will review"
    )
    assert matchers.looks_like_confirmation(subject, snippet)
    assert matchers.extract_role_title(subject, snippet, "Citi") == (
        "Services - Full-Time Analyst, Singapore, 2027-26978"
    )


def test_bare_interest_wording_is_not_treated_as_a_confirmation():
    """"Thank you for your interest" alone opens plenty of rejections."""
    assert not matchers.looks_like_confirmation(
        "Thank you for your interest in Acme",
        "Unfortunately we will not be moving forward with your application",
    )


def test_titles_keep_dashes_and_pipes():
    """Splitting on dashes truncated "Services - Full-Time Analyst" to "Services"."""
    assert matchers.extract_role_title(
        "Your application for Internal Audit, Technology Audit | New Analyst"
    ) == "Internal Audit, Technology Audit | New Analyst"


def test_assessment_platforms_count_as_shared_senders():
    assert matchers.is_ats_domain("plum.io")
    assert matchers.is_ats_domain("myworkday.com")
    assert not matchers.is_ats_domain("citi.com")


def test_human_resources_is_stripped_from_the_sender_name():
    assert matchers.company_from_sender(
        "Citi Human Resources <citi@myworkday.com>", "myworkday.com"
    ) == "Citi"


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
