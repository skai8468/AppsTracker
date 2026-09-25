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
    # Apple's subject is only "Thanks for your interest in Apple."; the proof is the body's
    # "We just received your resume for the following role: ...".
    "received your resume",
    "received your cv",
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

# Free mail providers. Anyone can write from these, so the domain says nothing about who
# is hiring: saved against one company, gmail.com would hand that company every Gmail
# sender there is, the user's own address included.
WEBMAIL_DOMAINS = frozenset({
    "gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "live.com", "msn.com",
    "yahoo.com", "yahoo.com.sg", "ymail.com", "icloud.com", "me.com", "mac.com",
    "aol.com", "proton.me", "protonmail.com", "gmx.com",
})

_EMAIL_RE = re.compile(r"[\w.+-]+@([\w-]+\.[\w.-]+)")


# Second-level labels that sit under a country code: "tech.gov.sg", "dbs.com.sg".
_SECOND_LEVEL_LABELS = frozenset({"com", "co", "org", "net", "gov", "edu"})


def registrable_domain(domain: str) -> str:
    """The employer-level part of a sender domain: "email.apple.com" -> "apple.com".

    Confirmations come from bulk-mail subdomains, while recruiters write from the bare
    domain. Tracking the subdomain Apple's confirmation came from would have missed every
    later email from an Apple recruiter.
    """
    parts = [p for p in (domain or "").lower().strip().split(".") if p]
    if len(parts) <= 2:
        return ".".join(parts)
    keep = 3 if parts[-2] in _SECOND_LEVEL_LABELS else 2
    return ".".join(parts[-keep:])


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


def is_webmail_domain(domain: str) -> bool:
    """True for free mail providers, whose domain identifies no employer."""
    return _domain_in(domain, WEBMAIL_DOMAINS)


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
    # Two-letter words now count (see title_tokens), so their filler has to be named.
    "of", "in", "to", "at", "an", "or", "on", "by", "as", "is", "we", "be",
})

# A posting URL's id is a run of four or more digits ("higher.gs.com/roles/170769",
# Keppel's "..._10016290"); shorter runs are office numbers and the like. Four digits
# also admits years, which url_ref_ids has to filter out itself.
_REF_RE = re.compile(r"\d{4,}")


# "P&R", "R&D", "M&A": one role word written as two letters. Joined before tokenising,
# because single letters are dropped. Only single letters join, so "Project & Change"
# stays two words.
_AMPERSAND_ACRONYM_RE = re.compile(r"\b([a-z])\s?&\s?([a-z])\b")


def title_tokens(title: str) -> set[str]:
    """Distinctive lowercase words from a role title.

    Two-letter words count: "IT", "AI", "HR" and "UX" are often all that tells two
    internships apart. Dropping them left Keppel's "Intern, P&R (Jan - May 2027)" with
    only its intake dates to compare, a hair short of matching any other role in that
    intake.
    """
    text = _AMPERSAND_ACRONYM_RE.sub(r"\1\2", (title or "").lower())
    return {
        t for t in _TOKEN_RE.findall(text)
        if len(t) >= 2 and t not in _GENERIC_TOKENS
    }


def role_tokens(title: str, company: str = "") -> set[str]:
    """A title's distinctive words, without the employer's own name.

    Shopee writes itself into every title ("Shopee - Product Manager Intern, Order
    Operations"), so its name matched between any two Shopee roles and made unrelated
    ones look alike.
    """
    employer = set(_TOKEN_RE.findall((company or "").lower()))
    return {t for t in title_tokens(title) if t not in employer}


def title_match_score(title: str, text: str, company: str = "") -> float:
    """Fraction of a title's distinctive words present in ``text`` (0.0 - 1.0).

    Whole words only: a substring test counts "data" as present in "database".
    """
    tokens = role_tokens(title, company)
    if not tokens:
        return 0.0
    words = set(_TOKEN_RE.findall((text or "").lower()))
    return sum(1 for t in tokens if t in words) / len(tokens)


def role_similarity(a: str, b: str, company: str = "") -> float:
    """How far two role titles agree: shared distinctive words over all of them.

    Symmetric on purpose. The old test asked how much of a tracked title appeared in the
    email, so a new Shopee role sharing an older one's intake ("Spring 2027") scored as
    the same role and was read as a re-confirmation instead of a new application.
    """
    ta, tb = role_tokens(a, company), role_tokens(b, company)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


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
    # Keppel: "Thank you for considering [Keppel Internship Programme 2027] Intern, ...".
    r"thank you for considering(?: the)?\s+(.+)",
    # Apple: "We just received your resume for the following role: 2027 Apple ...".
    r"received your (?:resume|cv|application) for the following"
    r" (?:role|position|job)s?\s*:?\s*(.+)",
    r"received your (?:resume|cv) for(?: the)?\s+(.+)",
    # Workday: "Confirmation of application received for 26WD100994 Intern, ...".
    r"application received for(?: the)?\s+(.+)",
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

# Workday wraps a posting title in its requisition code and the posting's status:
# "26WD100994 Intern, Product Manager [PSET-Access-PM] (Open)". A code has to mix
# letters with a run of four digits, so a year that opens a real title
# ("2027 Software Engineer Program") is left alone.
_REQ_CODE_PREFIX_RE = re.compile(r"^(?=\S*[A-Za-z])(?=\S*\d{4})[A-Za-z0-9-]+\s+")
# Apple appends the posting number: "... Information Systems and Technology 200675982".
# Six digits at least, so a title that ends in its intake year keeps it.
_REQ_CODE_SUFFIX_RE = re.compile(r"\s+\d{6,}$")
_POSTING_STATUS_RE = re.compile(r"\s*\((?:open|closed|filled|evergreen)\)\s*$",
    re.IGNORECASE,
)

# Function-mailbox words that aren't part of the employer's name. This does the real work
# for shared-ATS senders, where the display name is all we have to identify the employer:
# "EY Talent Attraction and Acquisition Team" has to reduce to "EY".
_SENDER_NOISE_RE = re.compile(
    r"\b(?:recruit(?:ing|ment|er)?|careers?|talent|attraction|acquisition|hiring|hire"
    r"|jobs?|human\s+resources|hr|people\s+team|campus|university\s+relations"
    r"|early\s+careers?|graduate\s+programme|no[\s-]?reply|do[\s-]?not[\s-]?reply|noreply"
    r"|auto[\s-]?notifications?|notifications?|team|via|support|mailer|info|admin"
    r"|onboarding|interviews?|assessments?|candidates?|applications?|system|hello"
    r"|contact|alerts?|updates?|worldwide)\b",
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
            title = _REQ_CODE_PREFIX_RE.sub("", title)
            title = _REQ_CODE_SUFFIX_RE.sub("", _POSTING_STATUS_RE.sub("", title)).strip()
            if not (2 < len(title) <= 120):
                continue
            if company and title_is_the_employer(title, company):
                continue  # that's the employer, not the role
            return title
    return None


_LOCAL_PART_RE = re.compile(r"([\w.+-]+)@")


def _clean_sender_name(raw: str) -> str:
    """A sender name with the mailbox boilerplate removed, or "" if nothing is left."""
    name = _SENDER_NOISE_RE.sub(" ", raw)
    name = _DANGLING_RE.sub(" ", name)
    name = re.sub(r"\s{2,}", " ", name).strip(" -|,·•&+")
    return name if len(name) > 1 and not _EMAIL_RE.search(name) else ""


def _tenant_name(from_header: str, domain: str) -> str:
    """The mailbox name on a shared platform, as an employer name, or "" if none.

    Only on shared platforms: at an employer's own domain the mailbox is a person or a
    team ("jane@acme.com"), never the employer.
    """
    if not is_ats_domain(domain):
        return ""
    local = _LOCAL_PART_RE.search(from_header or "")
    if not local:
        return ""
    name = _clean_sender_name(re.sub(r"[._+-]+", " ", local.group(1)))
    if not (name and normalize_company_name(name)):
        return ""
    # "hp", "dbs": a short mailbox name is an acronym, and "Hp" reads as a typo.
    return name.upper() if len(name) <= 3 else name.title()


def company_from_sender(from_header: str, domain: str) -> str:
    """Employer name from the From header, falling back to the domain.

    Readings in order: the display name, then (on shared platforms only) the mailbox
    name, then the domain. Workday mails as ``<tenant>@myworkday.com`` and the tenant is
    the employer. Razer's confirmation came from ``razer@myworkday.com`` with no display
    name at all, and Autodesk's signed itself "AutoNotification workday"; both reduced to
    the platform, so Razer's was dropped and Autodesk's was filed under a company named
    after the notification mailbox. HP's "Workday HRHPI <hp@myworkday.com>" was filed as
    "Workday HRHPI": a name the platform signs itself can carry the tenant's HR
    decoration, and there the mailbox name is the employer.
    """
    tenant = _tenant_name(from_header, domain)
    m = _DISPLAY_NAME_RE.match(from_header or "")
    if m:
        signed = _clean_sender_name(m.group(1))
        # The platform's own brand is never part of the employer's name: "Keppel Workday".
        name = " ".join(w for w in signed.split() if w.lower() not in _ATS_BRAND_TOKENS)
        # A display name that is only the platform's brand says nothing about who is
        # hiring, so the mailbox name gets a chance before the domain does.
        if name and normalize_company_name(name):
            if tenant and name != signed:
                # Signed by the platform. When the mailbox name sits inside what is left
                # ("hp" in "HRHPI"), the rest is HR decoration and the mailbox is the
                # employer; otherwise the display name is ("Keppel" over "KeppelHR").
                shown = normalize_company_name(name)
                box = normalize_company_name(tenant)
                if box in shown and len(box) < len(shown):
                    return tenant
            return name
    if tenant:
        return tenant
    # "careers.tiktok.com" -> "Tiktok": drop the public suffix and any leading label.
    parts = [p for p in (domain or "").split(".") if p]
    if not parts:
        return "Unknown"
    label = parts[-2] if len(parts) >= 2 else parts[0]
    # Handle "gs.com.sg" style: skip well-known second-level suffixes.
    if label in _SECOND_LEVEL_LABELS and len(parts) >= 3:
        label = parts[-3]
    return label.replace("-", " ").title()


# A four-digit run that reads as a year is the intake, not an id. Keppel's job links carry
# it in the slug ("...Programme-2027--Intern--AI-Platform--Jan---May-2027-_10016290"),
# and every other 2027-intake Keppel confirmation "matched" that link's application
# and was filed under it.
_YEAR_RE = re.compile(r"(?:19|20)\d{2}")


def url_ref_ids(url: str) -> set[str]:
    return {
        ref for ref in _REF_RE.findall(url or "")
        if not (len(ref) == 4 and _YEAR_RE.fullmatch(ref))
    }


def ref_in_text(url: str, text: str) -> bool:
    """True if a requisition id from the posting URL appears in the email.

    Whole numbers only: as a substring, "4548" would be found inside "145480".
    """
    ids = url_ref_ids(url)
    return bool(ids) and bool(ids & set(_REF_RE.findall(text or "")))
