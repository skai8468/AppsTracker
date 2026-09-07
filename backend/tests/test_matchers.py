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


# --- employer names as the platforms spell them -----------------------------------------

def test_platform_display_name_identifies_no_employer():
    """"HireVue <no-reply@hirevue.com>" says who sent it, not who is hiring."""
    assert matchers.normalize_company_name("HireVue") == ""
    assert matchers.is_ats_brand_name("HireVue")
    assert not matchers.is_ats_brand_name("J.P. Morgan")


def test_the_same_employer_spelled_two_ways_matches():
    """The tracked name comes from the job posting, the email's from the ATS."""
    assert matchers.company_name_matches("J.P. Morgan", "JPMorganChase")
    assert matchers.company_name_matches("Citi", "Citigroup Global Markets")
    assert matchers.company_name_matches("Acme", "Acme Pte Ltd")
    assert not matchers.company_name_matches("DBS", "OCBC")


def test_short_names_are_not_matched_by_containment():
    """"EY" is a substring of too much to be tested that loosely."""
    assert not matchers.company_name_matches("EY", "Keystone Partners")
    assert matchers.company_name_matches("EY", "EY")


def test_employer_found_in_the_subject_when_the_sender_is_the_platform():
    assert matchers.name_in_text(
        "J.P. Morgan", "Complete your JPMorganChase video interview"
    )
    assert not matchers.name_in_text("DBS", "Complete your JPMorganChase video interview")


# --- interview and assessment invitations -----------------------------------------------

def test_hirevue_invitation_is_read_as_an_interview():
    assert matchers.looks_like_interview("Complete your video interview", "")
    assert matchers.looks_like_interview("Your HireVue is ready", "")
    assert matchers.looks_like_interview("Invitation to complete an online assessment", "")


def test_a_rejection_quoting_the_interview_is_not_an_invitation():
    """Rejections name the stage they are ending, so they match invitation wording."""
    assert not matchers.looks_like_interview(
        "An update on your candidacy",
        "Unfortunately, following your video interview we will not be moving forward.",
    )
    assert matchers.looks_like_rejection("", "we regret to inform you")


def test_assessment_vendors_are_separable_from_other_shared_senders():
    assert matchers.is_assessment_domain("hirevue.com")
    assert matchers.is_assessment_domain("mail.hirevue.com")
    assert not matchers.is_assessment_domain("greenhouse.io")   # an ATS, not a test
    assert matchers.is_ats_domain("greenhouse.io")
