"""Declarative, pure matching rules for incoming email — no I/O, easy to unit-test.

Two questions the poller asks of every message:

1. Which tracked company (if any) does the sender belong to?
2. Does this look like an application *confirmation* or an *interview invitation* (so we
   can auto-flip the stage)?

Offers and rejections are still left for the user to one-tap classify, because those are
too free-form to auto-parse reliably. Interview invitations used to be in that group; they
came back out because the assessment vendors that carry most of them (HireVue and friends)
write one kind of mail only, so the sender alone is close to conclusive. Rejections are
parsed here, but only as a veto — they quote the stage they are ending ("we will not be
progressing you to interview"), so without them the invitation wordings match rejections
just as well.
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
    # Deliberately phrase-level. A bare "thank you for your interest" is just as common in
    # rejections, so only the wordings that state an application was made count.
    "taking the time to apply",
    "time to apply for",
    "apply for the role",
    "applying for the role",
    "applied for the role",
    "interest in joining",
    "successfully received your",
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

# Invitations to sit an interview or an online assessment. Restricted to wordings that
# state a stage is being *offered*: the bare word "interview" is as common in a rejection
# as in an invite, so it is never enough on its own.
INTERVIEW_PATTERNS = (
    "video interview",
    "hirevue",
    "on-demand interview",
    "on demand interview",
    "one-way interview",
    "digital interview",
    "recorded interview",
    "pre-recorded interview",
    "interview invitation",
    "invitation to interview",
    "invitation to an interview",
    "invite you to interview",
    "invited to interview",
    "invited you to interview",
    "would like to interview",
    "schedule your interview",
    "schedule an interview",
    "book your interview",
    "select an interview",
    "interview with our team",
    "online assessment",
    "immersive assessment",
    "game-based assessment",
    "gamified assessment",
    "situational judgement",
    "assessment invitation",
    "invitation to complete",
    "complete your assessment",
    "complete your video",
    "coding challenge",
    "technical assessment",
    "assessment centre",
    "assessment center",
    "phone screen",
    "next stage of the process",
    "next stage of our",
    "next round of",
)

# Vetoes an interview reading — see the module docstring. Never used to auto-set the
# rejected stage: which of these is a real rejection is exactly the free-form judgement
# left to the user.
REJECTION_PATTERNS = (
    "not be moving forward",
    "not moving forward",
    "not be progressing",
    "not progressing",
    "regret to inform",
    "unfortunately",
    "not been successful",
    "were not successful",
    "not be successful",
    "not selected",
    "were not selected",
    "decided not to proceed",
    "unable to proceed",
    "unable to offer",
    "no longer under consideration",
    "other candidates",
    "not shortlisted",
    "will not be taking your application",
)

# Applicant-tracking platforms that send on behalf of many employers. EY mails from
# yello.co and Goldman from oracle.com — neither is the employer's own domain, so storing
# one as a company's tracked domain would make the NEXT employer using that platform match
# the wrong company. Senders here are identified by display name instead.
_APPLICANT_TRACKING_DOMAINS = frozenset({
    "yello.co", "greenhouse.io", "lever.co", "ashbyhq.com", "workable.com",
    "smartrecruiters.com", "jobvite.com", "icims.com", "taleo.net", "brassring.com",
    "kenexa.com", "avature.net", "recruitee.com", "teamtailor.com", "breezy.hr",
    "bamboohr.com", "personio.de", "eightfold.ai", "phenompeople.com", "radancy.com",
    "symphonytalent.com", "successfactors.com", "successfactors.eu", "myworkday.com",
    "myworkdayjobs.com", "workday.com", "oracle.com", "oraclecloud.com", "ultipro.com",
    "silkroad.com", "applytojob.com", "hire.lever.co", "jobs.workable.com",
})

# Assessment and video-interview platforms mail on the employer's behalf too, so they are
# shared senders like the above. They are kept separate because they only ever write about
# one thing: the sender alone is enough to read a message as an interview invitation.
ASSESSMENT_DOMAINS = frozenset({
    "plum.io", "hirevue.com", "codility.com", "hackerrank.com", "karat.com",
    "sparkhire.com", "modernhire.com", "shl.com", "cut-e.com", "criteriacorp.com",
    "testgorilla.com", "pymetrics.com", "vervoe.com", "willo.video",
    "myinterview.com", "talentlens.com", "cappassess.com", "amcat.co",
})

ATS_DOMAINS = _APPLICANT_TRACKING_DOMAINS | ASSESSMENT_DOMAINS

# Assessment vendors that also run a practice product for individuals: HackerRank sends
# contests, streaks and newsletters to anyone with an account, and some of that names big
# employers. For these the sender proves nothing on its own and the wording has to carry
# it — the rest exist only to run interviews an employer commissioned.
_PRACTICE_PLATFORMS = frozenset({
    "hackerrank.com", "codility.com", "shl.com", "testgorilla.com", "amcat.co",
})

_EMAIL_RE = re.compile(r"[\w.+-]+@([\w-]+\.[\w.-]+)")


def extract_domain(from_header: str) -> str | None:
    """Pull the domain out of a From header like 'Careers <no-reply@dbs.com>'."""
    m = _EMAIL_RE.search(from_header or "")
    return m.group(1).lower() if m else None


def _domain_in(domain: str, group: frozenset[str]) -> bool:
    d = (domain or "").lower().strip()
    if not d:
        return False
    # Subdomains too: "mail.yello.co", "e.greenhouse.io".
    return d in group or any(d.endswith("." + g) for g in group)


def is_ats_domain(domain: str) -> bool:
    """True if the domain belongs to a shared recruiting platform, not one employer."""
    return _domain_in(domain, ATS_DOMAINS)


def is_assessment_domain(domain: str) -> bool:
    """True for video-interview / online-assessment vendors."""
    return _domain_in(domain, ASSESSMENT_DOMAINS)


def sender_implies_interview(domain: str) -> bool:
    """True when mail from this domain is an interview step whatever it says.

    Nobody is sent a HireVue link except to sit one, so the sender alone is a usable
    stage signal. Vendors with a consumer side are excluded: a HackerRank contest mail
    naming an employer you track is not an invitation to interview with them.
    """
    return _domain_in(domain, ASSESSMENT_DOMAINS) and not _domain_in(
        domain, _PRACTICE_PLATFORMS
    )


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


def looks_like_rejection(subject: str, snippet: str) -> bool:
    text = f"{subject or ''} {snippet or ''}".lower()
    return any(p in text for p in REJECTION_PATTERNS)


def looks_like_interview(subject: str, snippet: str) -> bool:
    """True for an invitation to an interview or assessment, rejections excluded.

    The veto is not a refinement: a rejection that closes with "thank you for the time you
    put into your video interview" matches INTERVIEW_PATTERNS outright.
    """
    text = f"{subject or ''} {snippet or ''}".lower()
    if any(p in text for p in REJECTION_PATTERNS):
        return False
    return any(p in text for p in INTERVIEW_PATTERNS)


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
    # "…apply for the role of Services – Full-Time Analyst" — most explicit, so first.
    r"appl(?:y|ied|ying) for the (?:role|position) of\s+(.+)",
    r"appl(?:y|ied|ying) (?:to|for)(?: the)? (?:role|position)(?: of)?\s+(.+)",
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

# Function-mailbox words that aren't part of the employer's name. This does the real work
# for shared-ATS senders, where the display name is all we have to identify the employer:
# "EY Talent Attraction and Acquisition Team" has to reduce to "EY".
_SENDER_NOISE_RE = re.compile(
    r"\b(?:recruit(?:ing|ment|er)?|careers?|talent|attraction|acquisition|hiring|hire"
    r"|jobs?|human\s+resources|hr|people\s+team|campus|university\s+relations"
    r"|early\s+careers?|graduate\s+programme|no[\s-]?reply|do[\s-]?not[\s-]?reply|noreply"
    r"|notifications?|team|via|support|mailer|info|admin|onboarding)\b",
    re.IGNORECASE,
)

# Left behind once the words above are removed: "EY and", "Acme &", "- Acme".
_DANGLING_RE = re.compile(r"\s+(?:and|&|\+)\s+|^\s*(?:and|&|\+)\s+|\s+(?:and|&|\+)\s*$",
                          re.IGNORECASE)


# Vendor brands as they appear in a *display* name: "HireVue <no-reply@hirevue.com>".
# These name the platform rather than whoever is hiring, so a name made only of them
# identifies no employer. Oracle and other platform vendors that are also major employers
# in their own right are deliberately absent — applying to them has to keep working.
_ATS_BRAND_TOKENS = frozenset({
    "hirevue", "workday", "myworkday", "greenhouse", "lever", "yello", "ashby",
    "ashbyhq", "workable", "smartrecruiters", "jobvite", "icims", "taleo", "brassring",
    "kenexa", "avature", "recruitee", "teamtailor", "breezy", "bamboohr", "personio",
    "eightfold", "phenom", "phenompeople", "radancy", "symphonytalent", "successfactors",
    "ultipro", "silkroad", "plum", "codility", "hackerrank", "karat", "sparkhire",
    "modernhire", "criteriacorp", "testgorilla", "pymetrics", "vervoe", "willo",
    "myinterview", "cappassess", "amcat",
})

# Legal-form and grouping words that differ between how an employer names itself on a job
# posting and how its platform names it in mail: "J.P. Morgan" vs "JPMorgan Chase & Co.".
_NAME_SUFFIX_TOKENS = frozenset({
    "co", "inc", "ltd", "limited", "llc", "plc", "corp", "corporation", "company",
    "group", "holdings", "holding", "pte", "sdn", "bhd", "sa", "nv", "bv", "ag",
    "gmbh", "spa", "and", "the", "via",
})

# "EY" would be a substring of half the names in any list, so short names have to match
# exactly. Four characters is the shortest that survives the containment test below.
_MIN_NAME_OVERLAP = 4


def normalize_company_name(name: str) -> str:
    """Comparable form of an employer name: lowercase letters and digits only, with
    platform brands and legal-form words dropped.

    An empty result means the name identified no employer at all — "HireVue" reduces to
    nothing, which is how a platform signing its own mail is told apart from a real one.
    """
    return "".join(
        t for t in _TOKEN_RE.findall((name or "").lower())
        if t not in _ATS_BRAND_TOKENS and t not in _NAME_SUFFIX_TOKENS
    )


def is_ats_brand_name(name: str) -> bool:
    """True when a sender's display name is nothing but the platform's own brand."""
    return bool((name or "").strip()) and not normalize_company_name(name)


def company_name_matches(a: str, b: str) -> bool:
    """True when two spellings of an employer name refer to the same employer.

    Platform mail rarely reuses the name from the job posting: the tracked company is
    "J.P. Morgan" and the HireVue invitation signs "JPMorganChase". Comparing slugs for
    equality — the only test there used to be — misses every pair like that.
    """
    na, nb = normalize_company_name(a), normalize_company_name(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    shorter, longer = (na, nb) if len(na) <= len(nb) else (nb, na)
    return len(shorter) >= _MIN_NAME_OVERLAP and shorter in longer


# What a role title may carry beyond the employer's name before it stops being just the
# employer. "JPMorganChase" over "J.P. Morgan" leaves "chase"; "Citigroup" leaves "group".
# A real title leaves something longer — "Analyst" is seven characters.
_MAX_EMPLOYER_TAIL = 6


def title_is_the_employer(title: str, company: str) -> bool:
    """True when an extracted role title is nothing but the employer's own name.

    "Thank you for applying to JPMorganChase" yields "JPMorganChase" as the role, and
    comparing it to the tracked name for equality did not recognise it, because the
    tracked name is "J.P. Morgan". The result was a second application at JPMorgan for a
    role called JPMorganChase, spawned by an assessment email about the first one.
    """
    t, c = normalize_company_name(title), normalize_company_name(company)
    if not t:
        return True
    if not c:
        return False
    if t == c or t in c:
        return True
    # The employer's name with a little left over is another word of the same name.
    return c in t and len(t) - len(c) <= _MAX_EMPLOYER_TAIL


def name_in_text(name: str, text: str) -> bool:
    """True when an employer's name appears in the email, ignoring case and punctuation.

    The last resort for platform-signed mail: HireVue puts its own name in the From header
    and the employer's in the subject ("Complete your JPMorganChase video interview").
    """
    n = normalize_company_name(name)
    if len(n) < _MIN_NAME_OVERLAP:
        return False
    return n in "".join(_TOKEN_RE.findall((text or "").lower()))


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
            # Split on sentence ends only — real titles use both "|" and dashes
            # ("Audit | New Analyst", "Services – Full-Time Analyst, Singapore").
            title = re.split(r"[.!?\n]", title)[0]
            title = _TITLE_TAIL_RE.sub("", title).strip(" ,;:-–—\"'!")
            if not (2 < len(title) <= 120):
                continue
            if company and title_is_the_employer(title, company):
                continue  # that's the employer, not the role
            return title
    return None


def company_from_sender(from_header: str, domain: str) -> str:
    """Employer name from the From display name, falling back to the domain."""
    m = _DISPLAY_NAME_RE.match(from_header or "")
    if m:
        name = _SENDER_NOISE_RE.sub(" ", m.group(1))
        name = _DANGLING_RE.sub(" ", name)
        name = re.sub(r"\s{2,}", " ", name).strip(" -|,·•&+")
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
