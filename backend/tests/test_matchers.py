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


def test_webmail_providers_identify_no_employer():
    assert matchers.is_webmail_domain("gmail.com")
    assert matchers.is_webmail_domain("outlook.com")
    assert not matchers.is_webmail_domain("tiktok.com")
    assert not matchers.is_ats_domain("gmail.com")      # separate rule, same treatment


# --- Workday: the employer is the mailbox, not the display name -------------------------
#
# Both from real mail. Razer's confirmation had no display name and was dropped; Autodesk's
# was filed under a company called "AutoNotification workday" with no role.

RAZER_FROM = "razer@myworkday.com"
AUTODESK_FROM = "AutoNotification workday <autodesk@myworkday.com>"
AUTODESK_SUBJECT = (
    "Confirmation of application received for 26WD100994 Intern, Product Manager "
    "[PSET-Access-PM] (Open)"
)


def test_a_workday_tenant_names_the_employer_when_nothing_else_does():
    assert matchers.company_from_sender(RAZER_FROM, "myworkday.com") == "Razer"


def test_a_notification_mailbox_name_gives_way_to_the_tenant():
    assert matchers.company_from_sender(AUTODESK_FROM, "myworkday.com") == "Autodesk"


def test_a_generic_platform_mailbox_names_nobody():
    """"interviews@hirevue.com" must not become a company called Interviews."""
    name = matchers.company_from_sender(
        "HireVue <interviews@hirevue.com>", "hirevue.com"
    )
    assert matchers.is_ats_brand_name(name)


def test_the_mailbox_is_never_read_at_an_employers_own_domain():
    """At acme.com the mailbox is a person, not the employer."""
    assert matchers.company_from_sender("jane@acme.com", "acme.com") == "Acme"


def test_workday_confirmation_title_loses_its_code_and_status():
    assert matchers.extract_role_title(AUTODESK_SUBJECT, "", "Autodesk") == (
        "Intern, Product Manager [PSET-Access-PM]"
    )


def test_a_year_opening_a_title_is_not_mistaken_for_a_code():
    assert matchers.extract_role_title(
        "Application received for 2027 Software Engineer Program"
    ) == "2027 Software Engineer Program"


def test_razer_confirmation_title():
    assert matchers.extract_role_title(
        "We've got your application for Product Developer Intern !", "", "Razer"
    ) == "Product Developer Intern"


# --- Apple: the proof is in the body, and the title carries the posting number ----------

APPLE_FROM = "Apple Worldwide Recruiting <appleworldwiderecruiting@email.apple.com>"
APPLE_SUBJECT = "Thanks for your interest in Apple."
APPLE_SNIPPET = (
    "Hi Leong, We just received your resume for the following role: 2027 Apple "
    "Internship - Information Systems and Technology 200675982. Thanks for thinking of "
    "us. Here's what happens next"
)


def test_apples_resume_receipt_is_a_confirmation():
    assert matchers.looks_like_confirmation(APPLE_SUBJECT, APPLE_SNIPPET)


def test_apples_title_loses_its_posting_number():
    assert matchers.extract_role_title(APPLE_SUBJECT, APPLE_SNIPPET, "Apple") == (
        "2027 Apple Internship - Information Systems and Technology"
    )


def test_worldwide_recruiting_is_a_mailbox_not_the_employer():
    assert matchers.company_from_sender(APPLE_FROM, "email.apple.com") == "Apple"


def test_a_title_ending_in_its_intake_year_keeps_it():
    assert matchers.extract_role_title(
        "Thank you for applying to Graduate Programme 2027"
    ) == "Graduate Programme 2027"


def test_registrable_domain():
    assert matchers.registrable_domain("email.apple.com") == "apple.com"
    assert matchers.registrable_domain("apple.com") == "apple.com"
    assert matchers.registrable_domain("tech.gov.sg") == "tech.gov.sg"
    assert matchers.registrable_domain("careers.dbs.com.sg") == "dbs.com.sg"


# --- comparing roles at one employer ----------------------------------------------------

def test_the_employers_name_is_not_part_of_the_role():
    assert matchers.role_tokens(
        "Shopee - Product Manager Intern, Order Operations", "Shopee"
    ) == {"product", "manager", "order", "operations"}


def test_title_words_are_matched_whole():
    """"data" must not count as present in "database"."""
    assert matchers.title_match_score("Data Analyst", "Database Analyst role") == 0.5


def test_a_generic_posting_is_not_the_same_role_as_a_specific_one():
    """Real titles: every distinctive word of the first is inside the second."""
    generic = "Shopee - Product Management Intern - Shopee (Spring 2027)"
    specific = "Shopee - Product Management Intern, Regional Logistics (Spring 2027)"
    assert matchers.role_similarity(generic, specific, "Shopee") < 0.8


def test_role_similarity_is_symmetric():
    a, b = "Software Engineer Intern (Spring 2027)", "Software Engineer Intern"
    assert matchers.role_similarity(a, b) == matchers.role_similarity(b, a)
