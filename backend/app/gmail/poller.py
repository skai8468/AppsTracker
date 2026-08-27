"""Gmail poller: incremental fetch of new mail, match to tracked companies, act.

Flow per poll:
  * Read the stored ``gmail_history_id``. First run just records the current id (no backfill).
  * Use the History API to list message ids added since then.
  * For each new message, pull From / Subject / snippet / date.
  * ``process_message`` decides what to do (pure w.r.t. the DB session, so it's testable):
      - matches a company you APPLIED to + looks like a confirmation  -> flip app to
        ``confirmed`` and queue a "confirmation" notification.
      - matches any tracked company                                   -> store an
        EmailEvent and queue a "company_email" notification for you to classify.
  * Queued notifications are pushed to Telegram (best-effort).

``GMAIL_DRY_RUN=true`` logs matches without changing state or sending notifications.
"""
from __future__ import annotations

import base64
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlmodel import Session, select

from ..config import settings
from ..db import get_setting, session_scope, set_setting
from ..models import (
    Application,
    AppStatus,
    Company,
    EmailEvent,
    Job,
    Notification,
    utcnow,
)
from ..util import slugify
from . import matchers
from .oauth import get_service

log = logging.getLogger(__name__)

HISTORY_KEY = "gmail_history_id"


# --- parsed message shape (decoupled from the Gmail API payload) -----------------------

class ParsedMessage:
    def __init__(
        self,
        message_id: str,
        thread_id: str,
        from_addr: str,
        subject: str,
        snippet: str,
        received_at: Optional[datetime],
    ):
        self.message_id = message_id
        self.thread_id = thread_id
        self.from_addr = from_addr
        self.subject = subject
        self.snippet = snippet
        self.received_at = received_at


def _header(headers: list[dict[str, str]], name: str) -> str:
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def _parse_api_message(msg: dict[str, Any]) -> ParsedMessage:
    payload = msg.get("payload", {})
    headers = payload.get("headers", [])
    internal = msg.get("internalDate")
    received = (
        datetime.fromtimestamp(int(internal) / 1000, tz=timezone.utc)
        if internal
        else None
    )
    return ParsedMessage(
        message_id=msg.get("id", ""),
        thread_id=msg.get("threadId", ""),
        from_addr=_header(headers, "From"),
        subject=_header(headers, "Subject"),
        snippet=msg.get("snippet", ""),
        received_at=received,
    )


# --- core decision logic (testable: takes a session + parsed message) ------------------

def process_message(session: Session, msg: ParsedMessage) -> Optional[Notification]:
    """Match one message to a company and act. Returns a Notification to send, or None."""
    if session.exec(
        select(EmailEvent).where(EmailEvent.gmail_message_id == msg.message_id)
    ).first():
        return None  # already processed

    domain = matchers.extract_domain(msg.from_addr)
    if not domain:
        return None

    is_confirmation = matchers.looks_like_confirmation(msg.subject, msg.snippet)
    is_noise = matchers.looks_like_noise(msg.subject, msg.snippet)

    company = _match_company(session, domain, msg)
    created_from_email = False

    if company is None:
        # Nothing tracked at this domain. A confirmation still means a real application
        # exists, so create it from the email rather than requiring it to be typed in.
        if not (is_confirmation and not is_noise and settings.auto_track_from_email):
            return None
        company = _company_from_email(session, msg, domain)
        created_from_email = True

    # Which application at this company is the email about?
    app = _application_for_company(session, company, msg)

    # A confirmation naming a role we aren't tracking is a NEW application, not a reason to
    # flip an unrelated one — without this, applying twice at one employer would silently
    # re-confirm the first role instead of recording the second.
    if is_confirmation and not is_noise and settings.auto_track_from_email:
        if app is None or _names_an_untracked_role(session, company, msg):
            app = _create_application_from_email(session, company, msg)
            created_from_email = True

    event = EmailEvent(
        gmail_message_id=msg.message_id,
        thread_id=msg.thread_id,
        from_addr=msg.from_addr,
        subject=msg.subject,
        snippet=msg.snippet,
        received_at=msg.received_at,
        matched_company_id=company.id,
        matched_application_id=app.id if app else None,
    )

    if app and is_confirmation and app.status in (
        AppStatus.applied, AppStatus.interested, AppStatus.confirmed
    ):
        app.status = AppStatus.confirmed
        app.last_stage_change_at = utcnow()
        event.classified_stage = AppStatus.confirmed
        event.is_read = True
        session.add(app)
        session.add(event)
        session.commit()
        job = session.get(Job, app.job_id)
        role = job.title if job else msg.subject
        note = Notification(
            type="confirmation",
            payload=(
                f"🆕 New application tracked at {company.name}\n{role}"
                if created_from_email
                else f"✅ Application confirmed at {company.name}\n{role}"
            ),
            ref_email_event_id=event.id,
        )
    elif matchers.looks_like_noise(msg.subject, msg.snippet):
        # Login codes, password resets and job alerts share the company's domain but say
        # nothing about an application. File them read so they neither fill the inbox nor
        # fire Telegram — still stored, so it can be re-classified if this guessed wrong.
        event.is_read = True
        session.add(event)
        session.commit()
        log.info("filed as unrelated: %s | %s", msg.from_addr, msg.subject)
        return None
    else:
        session.add(event)
        session.commit()
        note = Notification(
            type="company_email",
            payload=f"📩 Email from {company.name}\n{msg.subject}",
            ref_email_event_id=event.id,
        )

    session.add(note)
    session.commit()
    session.refresh(note)
    return note


def _company_from_email(session: Session, msg: ParsedMessage, domain: str) -> Company:
    """Create a tracked company from a confirmation's sender, reusing one by slug.

    The sender's domain is stored as the tracked domain, so matching works from here on
    without a separate trip to the Add page.
    """
    name = matchers.company_from_sender(msg.from_addr, domain)
    slug = slugify(name)
    # A shared platform's domain is never the employer's, so don't claim it for them.
    tracked_domain = "" if matchers.is_ats_domain(domain) else domain

    existing = session.exec(select(Company).where(Company.slug == slug)).first()
    if existing is not None:
        if tracked_domain and not existing.email_domains:
            existing.email_domains = tracked_domain
            session.add(existing)
            session.commit()
        return existing
    company = Company(name=name, slug=slug, email_domains=tracked_domain)
    session.add(company)
    session.commit()
    session.refresh(company)
    log.info("tracking new company from email: %s (%s)", name, domain)
    return company


def _create_application_from_email(
    session: Session, company: Company, msg: ParsedMessage
) -> Application:
    """Record an application the confirmation email proves exists."""
    title = matchers.extract_role_title(msg.subject, msg.snippet, company.name)
    job = Job(
        source="email",
        source_job_id=msg.message_id,
        # Some confirmations never name the role; the user can fill it in from the app.
        title=title or "Role not specified",
        company_name=company.name,
        company_id=company.id,
        sector=company.sector,
        apply_url="",
    )
    session.add(job)
    session.commit()
    session.refresh(job)

    app = Application(
        job_id=job.id,
        status=AppStatus.confirmed,
        applied_at=msg.received_at or utcnow(),
        notes="Added automatically from a confirmation email.",
    )
    session.add(app)
    session.commit()
    session.refresh(app)
    log.info("tracked new application from email: %s | %s", company.name, job.title)
    return app


def _names_an_untracked_role(
    session: Session, company: Company, msg: ParsedMessage
) -> bool:
    """True when the email names a role none of the company's applications match.

    Only says yes when a role was actually extracted — an unnamed role must never spawn a
    duplicate application for one already tracked.
    """
    title = matchers.extract_role_title(msg.subject, msg.snippet, company.name)
    if not title:
        return False
    jobs = session.exec(
        select(Job)
        .join(Application, Application.job_id == Job.id)
        .where(Job.company_id == company.id)
    ).all()
    text = f"{msg.subject or ''} {msg.snippet or ''}"
    for job in jobs:
        if matchers.title_match_score(job.title, text) >= _TITLE_CONFIDENCE:
            return False
        if matchers.ref_in_text(job.apply_url, text):
            return False
    return True


def _match_company(
    session: Session, domain: str, msg: Optional[ParsedMessage] = None
) -> Optional[Company]:
    """Find the tracked company an email belongs to.

    Shared recruiting platforms (Yello, Greenhouse, Workday, Oracle) send for many
    employers, so their domain identifies the platform, not the company. Matching those by
    domain would hand the next employer's mail to whoever was tracked first, so they're
    resolved by the sender's display name instead. This also neutralises an ATS domain
    already saved against a company before this rule existed.
    """
    if matchers.is_ats_domain(domain):
        if msg is None:
            return None
        name = matchers.company_from_sender(msg.from_addr, domain)
        return session.exec(
            select(Company).where(Company.slug == slugify(name))
        ).first()

    for company in session.exec(select(Company)).all():
        # Skip any ATS domain saved against a company; it isn't theirs to claim.
        owned = [d for d in company.domain_list() if not matchers.is_ats_domain(d)]
        if matchers.domain_matches(domain, owned):
            return company
    return None


# A title needs at least half its distinctive words in the email before we trust it over
# recency; the requisition-id bonus below is deliberately large enough to clear this alone.
_TITLE_CONFIDENCE = 0.5
_REF_BONUS = 1.0


def _application_for_company(
    session: Session, company: Company, msg: Optional[ParsedMessage] = None
) -> Optional[Application]:
    """Pick which application at ``company`` an email is about.

    With one open application the answer is trivial. With several — the same employer
    running multiple grad roles — recency alone picks wrong roughly as often as it picks
    right, so score each job's title (and the requisition id in its posting URL) against
    the email text, and only override "most recently touched" on a clear, unambiguous win.
    """
    apps = session.exec(
        select(Application)
        .join(Job, Job.id == Application.job_id)
        .where(Job.company_id == company.id)
        .order_by(Application.last_stage_change_at.desc())
    ).all()
    if not apps:
        return None
    most_recent = apps[0]
    if len(apps) == 1 or msg is None:
        return most_recent

    text = f"{msg.subject or ''} {msg.snippet or ''}"
    scored: list[tuple[float, Application]] = []
    for app in apps:
        job = session.get(Job, app.job_id)
        if job is None:
            continue
        score = matchers.title_match_score(job.title, text)
        if matchers.ref_in_text(job.apply_url, text):
            score += _REF_BONUS
        scored.append((score, app))

    if not scored:
        return most_recent
    scored.sort(key=lambda s: s[0], reverse=True)
    best_score, best_app = scored[0]
    runner_up = scored[1][0] if len(scored) > 1 else 0.0
    # A tie means the email doesn't distinguish them — don't guess, fall back to recency.
    if best_score >= _TITLE_CONFIDENCE and best_score > runner_up:
        return best_app
    return most_recent


# --- Gmail API plumbing ---------------------------------------------------------------

def _is_gone(exc: Exception) -> bool:
    """True when Gmail says a message no longer exists (404/410).

    Read off the response rather than catching ``HttpError`` directly so this module
    still imports when the Google client isn't installed.
    """
    status = getattr(getattr(exc, "resp", None), "status", None)
    try:
        return int(status) in (404, 410)
    except (TypeError, ValueError):
        return False


def _list_new_message_ids(service, start_history_id: str) -> tuple[list[str], Optional[str]]:
    ids: list[str] = []
    latest_history = start_history_id
    page_token = None
    while True:
        resp = (
            service.users()
            .history()
            .list(
                userId="me",
                startHistoryId=start_history_id,
                historyTypes=["messageAdded"],
                pageToken=page_token,
            )
            .execute()
        )
        for h in resp.get("history", []):
            latest_history = str(h.get("id", latest_history))
            for added in h.get("messagesAdded", []):
                mid = added.get("message", {}).get("id")
                if mid:
                    ids.append(mid)
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return ids, resp.get("historyId", latest_history)


def poll_once() -> dict[str, Any]:
    """Run a single poll. Safe to call from the scheduler or the admin endpoint."""
    service = get_service()
    if service is None:
        return {"status": "gmail_not_configured"}

    with session_scope() as session:
        history_id = get_setting(session, HISTORY_KEY)

        if history_id is None:
            # First run: record the current mailbox state, don't backfill.
            profile = service.users().getProfile(userId="me").execute()
            set_setting(session, HISTORY_KEY, str(profile.get("historyId")))
            return {"status": "initialized", "history_id": profile.get("historyId")}

        try:
            message_ids, new_history = _list_new_message_ids(service, history_id)
        except Exception as exc:  # noqa: BLE001 - e.g. history id too old (404)
            log.warning("history.list failed (%s); reinitializing", exc)
            profile = service.users().getProfile(userId="me").execute()
            set_setting(session, HISTORY_KEY, str(profile.get("historyId")))
            return {"status": "reinitialized"}

        # (id, payload) not ORM rows: the commit below expires session instances.
        notifications: list[tuple[int, str]] = []
        skipped = 0
        for mid in message_ids:
            try:
                msg = (
                    service.users()
                    .messages()
                    .get(
                        userId="me",
                        id=mid,
                        format="metadata",
                        metadataHeaders=["From", "Subject"],
                    )
                    .execute()
                )
            except Exception as exc:  # noqa: BLE001 - narrowed by _is_gone below
                if not _is_gone(exc):
                    # Transient (network, 5xx): bail without advancing the history id so
                    # the message is retried next poll rather than silently dropped.
                    raise
                # The message vanished between history.list and here — deleted, or moved
                # out of the mailbox. Skipping is essential: letting this escape aborts
                # the poll before the history id advances, so every later poll retries the
                # same dead id and the poller wedges permanently.
                log.info("skipping message %s (no longer in mailbox)", mid)
                skipped += 1
                continue
            parsed = _parse_api_message(msg)
            if settings.gmail_dry_run:
                log.info("[dry-run] %s | %s", parsed.from_addr, parsed.subject)
                continue
            note = process_message(session, parsed)
            if note:
                notifications.append((note.id, note.payload))

        if not settings.gmail_dry_run:
            set_setting(session, HISTORY_KEY, str(new_history))

    # Send notifications outside the session scope.
    delivered = _deliver(notifications)
    return {
        "status": "ok",
        "new_messages": len(message_ids),
        "skipped": skipped,
        "notifications": len(notifications),
        "delivered": delivered,
        "dry_run": settings.gmail_dry_run,
    }


def scan_recent(days: int = 30, limit: int = 400) -> dict[str, Any]:
    """One-off sweep of recent mail for confirmations the incremental poll never saw.

    ``poll_once`` only looks forward from the stored history id, so anything that arrived
    before Gmail was connected — or while the poller was broken — is invisible to it. The
    search is narrowed to application-shaped subjects rather than every message in the
    window, which keeps this to a few dozen API calls instead of thousands.
    """
    service = get_service()
    if service is None:
        return {"status": "gmail_not_configured"}

    query = (
        f"newer_than:{days}d "
        "subject:(application OR applying OR applied OR candidature)"
    )
    # (id, payload) not ORM rows -- see _deliver.
    notifications: list[tuple[int, str]] = []
    scanned = skipped = 0

    with session_scope() as session:
        page_token = None
        while scanned < limit:
            resp = (
                service.users()
                .messages()
                .list(userId="me", q=query, maxResults=100, pageToken=page_token)
                .execute()
            )
            for ref in resp.get("messages", []):
                if scanned >= limit:
                    break
                try:
                    msg = (
                        service.users()
                        .messages()
                        .get(
                            userId="me",
                            id=ref["id"],
                            format="metadata",
                            metadataHeaders=["From", "Subject"],
                        )
                        .execute()
                    )
                except Exception as exc:  # noqa: BLE001
                    if not _is_gone(exc):
                        raise
                    skipped += 1
                    continue
                scanned += 1
                note = process_message(session, _parse_api_message(msg))
                if note:
                    notifications.append((note.id, note.payload))
            page_token = resp.get("nextPageToken")
            if not page_token:
                break

    delivered = _deliver(notifications)
    return {
        "status": "ok",
        "scanned": scanned,
        "skipped": skipped,
        "tracked": len(notifications),
        "delivered": delivered,
    }


def _deliver(notifications: list[tuple[int, str]]) -> int:
    """Send queued notifications. Takes (id, payload) pairs, never ORM instances.

    The caller's session has usually committed since these rows were created, and a commit
    expires every object in the session; reading ``note.payload`` after the session closed
    raised DetachedInstanceError and failed the whole poll — silently, because it only
    happened on polls that actually produced a notification.
    """
    if not notifications:
        return 0
    from ..telegram.notify import send_notification

    delivered = 0
    with session_scope() as session:
        for note_id, payload in notifications:
            if send_notification(payload):
                db_note = session.get(Notification, note_id)
                if db_note:
                    db_note.telegram_delivered = True
                    session.add(db_note)
                delivered += 1
        session.commit()
    return delivered


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from ..db import init_db

    init_db()
    print(poll_once())
