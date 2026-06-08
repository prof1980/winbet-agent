#!/usr/bin/env python3
"""
Libero Mail Notifier — SMTP (invio) + IMAP (ricezione) con monitoring automatico.

Funzionalità:
- send_email(): invia email con supporto HTML/plaintext + allegati
- fetch_inbox(): legge le email in arrivo (IMAP)
- monitor_inbox(): loop continuo che controlla nuove email e le parsa
- mark_as_read(): segna email come lette
- search_emails(): cerca per subject/sender/date

Le credenziali sono lette da .env nella root del progetto.
NON stampare mai la password nei log.

Modalità C: monitora automaticamente le risposte e aggiorna il DB WinBet
se l'email contiene comandi (es. "stop", "status", "odds <match>").

Esempio uso:
    from libero_notifier import LiberoNotifier
    n = LiberoNotifier()
    n.send_email("watson.ag@libero.it", "Test", "Ciao da WinBet")
    n.monitor_inbox(callback=my_handler)
"""
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "python-dotenv",
# ]
# ///

from __future__ import annotations

import email
import email.utils
import imaplib
import json
import logging
import os
import re
import smtplib
import ssl
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path
from typing import Callable, Optional

from dotenv import load_dotenv

# Carica .env dalla root del progetto
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")

# ---------------------------------------------------------------------------
# Logging (mai stampare password)
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("libero_notifier")


def _sanitize(text: str) -> str:
    """Rimuove la password dai log."""
    pwd = os.getenv("LIBERO_PASSWORD", "")
    if pwd and pwd in text:
        text = text.replace(pwd, "***REDACTED***")
    return text


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------


@dataclass
class EmailMessage:
    """Rappresenta un'email ricevuta o da inviare."""

    from_addr: str
    to_addr: str
    subject: str
    body: str
    html_body: Optional[str] = None
    attachments: list[str] = field(default_factory=list)  # path ai file
    date: Optional[str] = None
    message_id: Optional[str] = None
    raw: Optional[email.message.Message] = None

    def to_dict(self) -> dict:
        return {
            "from": self.from_addr,
            "to": self.to_addr,
            "subject": self.subject,
            "body": self.body[:500] if self.body else "",
            "date": self.date,
            "message_id": self.message_id,
        }


# ---------------------------------------------------------------------------
# Notifier
# ---------------------------------------------------------------------------


class LiberoNotifier:
    """Gestisce invio (SMTP) e ricezione (IMAP) email via Libero.

    SMTP: invio email con autenticazione SSL.
    IMAP: lettura inbox con monitoraggio continuo.
    """

    def __init__(self) -> None:
        self.email = os.getenv("LIBERO_EMAIL")
        self.password = os.getenv("LIBERO_PASSWORD")
        self.smtp_host = os.getenv("LIBERO_SMTP_HOST", "smtp.libero.it")
        self.smtp_port = int(os.getenv("LIBERO_SMTP_PORT", "465"))
        self.smtp_ssl = os.getenv("LIBERO_SMTP_SSL", "true").lower() == "true"
        self.imap_host = os.getenv("LIBERO_IMAP_HOST", "imapmail.libero.it")
        self.imap_port = int(os.getenv("LIBERO_IMAP_PORT", "993"))

        if not self.email or not self.password:
            raise ValueError(
                "LIBERO_EMAIL e LIBERO_PASSWORD devono essere settati in .env"
            )

        # Sanitize email per evitare log sporchi
        log.info(f"LiberoNotifier inizializzato per {self.email}")

    # -----------------------------------------------------------------------
    # SMTP - Invio
    # -----------------------------------------------------------------------

    def _connect_smtp(self) -> smtplib.SMTP:
        """Connette al server SMTP Libero."""
        if self.smtp_ssl:
            context = ssl.create_default_context()
            server = smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, context=context, timeout=30)
        else:
            server = smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=30)
            server.starttls(context=ssl.create_default_context())

        server.login(self.email, self.password)
        log.info(f"SMTP connesso a {self.smtp_host}:{self.smtp_port}")
        return server

    def send_email(
        self,
        to: str | list[str],
        subject: str,
        body: str,
        html_body: Optional[str] = None,
        attachments: Optional[list[str]] = None,
        cc: Optional[list[str]] = None,
        bcc: Optional[list[str]] = None,
    ) -> bool:
        """Invia un'email.

        Args:
            to: indirizzo destinatario o lista
            subject: oggetto
            body: corpo testo (plaintext)
            html_body: corpo HTML opzionale
            attachments: lista di path file da allegare
            cc: copia carbone
            bcc: copia carbone nascosta

        Returns:
            True se invio riuscito
        """
        if isinstance(to, str):
            to = [to]
        if cc is None:
            cc = []
        if bcc is None:
            bcc = []
        if attachments is None:
            attachments = []

        # Costruisci messaggio MIME
        msg = MIMEMultipart("alternative")
        msg["From"] = self.email
        msg["To"] = ", ".join(to)
        if cc:
            msg["Cc"] = ", ".join(cc)
        msg["Subject"] = subject
        msg["Date"] = email.utils.formatdate(localtime=True)
        msg["Message-ID"] = email.utils.make_msgid(domain="libero.it")

        # Corpo plaintext
        msg.attach(MIMEText(body, "plain", "utf-8"))

        # Corpo HTML opzionale
        if html_body:
            msg.attach(MIMEText(html_body, "html", "utf-8"))

        # Allegati
        for filepath in attachments:
            if not Path(filepath).exists():
                log.warning(f"Allegato non trovato: {filepath}")
                continue
            with open(filepath, "rb") as f:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header(
                "Content-Disposition",
                f"attachment; filename={Path(filepath).name}",
            )
            msg.attach(part)

        # Destinatari totali
        all_recipients = to + cc + bcc

        try:
            with self._connect_smtp() as server:
                server.sendmail(self.email, all_recipients, msg.as_string())
            log.info(
                f"Email inviata a {', '.join(to)} | subject='{subject}'"
            )
            return True
        except smtplib.SMTPAuthenticationError as e:
            log.error(f"Errore autenticazione SMTP: {e}")
            return False
        except smtplib.SMTPException as e:
            log.error(f"Errore SMTP: {e}")
            return False
        except Exception as e:
            log.error(f"Errore generico invio: {e}")
            return False

    # -----------------------------------------------------------------------
    # IMAP - Ricezione
    # -----------------------------------------------------------------------

    def _connect_imap(self) -> imaplib.IMAP4_SSL:
        """Connette al server IMAP Libero."""
        context = ssl.create_default_context()
        server = imaplib.IMAP4_SSL(self.imap_host, self.imap_port, ssl_context=context, timeout=30)
        server.login(self.email, self.password)
        log.info(f"IMAP connesso a {self.imap_host}:{self.imap_port}")
        return server

    def fetch_inbox(
        self,
        limit: int = 10,
        unseen_only: bool = True,
        since: Optional[datetime] = None,
        folder: str = "INBOX",
    ) -> list[EmailMessage]:
        """Legge le email dalla inbox.

        Args:
            limit: numero massimo di email da leggere
            unseen_only: solo non lette
            since: solo email più recenti di questa data
            folder: cartella IMAP (default INBOX)

        Returns:
            lista di EmailMessage
        """
        messages: list[EmailMessage] = []
        try:
            server = self._connect_imap()
            try:
                status, _ = server.select(folder)
                if status != "OK":
                    log.error(f"Impossibile selezionare {folder}")
                    return messages

                # Costruisci criteri di ricerca
                criteria = []
                if unseen_only:
                    criteria.append("UNSEEN")
                if since:
                    date_str = since.strftime("%d-%b-%Y")
                    criteria.append(f'SINCE {date_str}')

                search_criteria = " ".join(criteria) if criteria else "ALL"
                status, data = server.search(None, search_criteria)
                if status != "OK":
                    log.warning(f"Nessun risultato per criteri: {search_criteria}")
                    return messages

                # Prendi le ultime N email
                mail_ids = data[0].split()
                mail_ids = mail_ids[-limit:] if len(mail_ids) > limit else mail_ids
                mail_ids = list(reversed(mail_ids))  # più recenti prima

                for mail_id in mail_ids:
                    status, msg_data = server.fetch(mail_id, "(RFC822)")
                    if status != "OK":
                        continue
                    raw_email = msg_data[0][1]
                    msg = email.message_from_bytes(raw_email)

                    parsed = self._parse_email(msg)
                    if parsed:
                        parsed.message_id = mail_id.decode() if isinstance(mail_id, bytes) else str(mail_id)
                        messages.append(parsed)

            finally:
                server.close()
                server.logout()

        except imaplib.IMAP4.error as e:
            log.error(f"Errore IMAP: {e}")
        except Exception as e:
            log.error(f"Errore generico IMAP: {e}")

        return messages

    def _parse_email(self, msg: email.message.Message) -> Optional[EmailMessage]:
        """Parsa un'email MIME in EmailMessage."""
        try:
            from_addr = email.utils.parseaddr(msg.get("From", ""))[1]
            to_addr = email.utils.parseaddr(msg.get("To", ""))[1]
            subject = msg.get("Subject", "")
            date = msg.get("Date", "")

            # Decodifica subject se encodato
            decoded_subject = email.header.decode_header(subject)
            subject = "".join(
                [
                    s.decode(c or "utf-8") if isinstance(s, bytes) else s
                    for s, c in decoded_subject
                ]
            )

            # Estrai corpo
            body = ""
            html_body = None
            if msg.is_multipart():
                for part in msg.walk():
                    content_type = part.get_content_type()
                    content_disposition = str(part.get("Content-Disposition", ""))
                    if "attachment" in content_disposition:
                        continue
                    payload = part.get_payload(decode=True)
                    if payload is None:
                        continue
                    charset = part.get_content_charset() or "utf-8"
                    try:
                        text = payload.decode(charset, errors="replace")
                    except LookupError:
                        text = payload.decode("utf-8", errors="replace")
                    if content_type == "text/plain":
                        body = text
                    elif content_type == "text/html":
                        html_body = text
            else:
                payload = msg.get_payload(decode=True)
                if payload:
                    charset = msg.get_content_charset() or "utf-8"
                    try:
                        body = payload.decode(charset, errors="replace")
                    except LookupError:
                        body = payload.decode("utf-8", errors="replace")

            return EmailMessage(
                from_addr=from_addr,
                to_addr=to_addr,
                subject=subject,
                body=body,
                html_body=html_body,
                date=date,
            )
        except Exception as e:
            log.error(f"Errore parsing email: {e}")
            return None

    def mark_as_read(self, message_id: str, folder: str = "INBOX") -> bool:
        """Segna un'email come letta."""
        try:
            server = self._connect_imap()
            try:
                server.select(folder)
                server.store(message_id, "+FLAGS", "\\Seen")
                log.info(f"Email {message_id} segnata come letta")
                return True
            finally:
                server.close()
                server.logout()
        except Exception as e:
            log.error(f"Errore mark_as_read: {e}")
            return False

    def search_emails(
        self,
        subject_pattern: Optional[str] = None,
        from_pattern: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 20,
    ) -> list[EmailMessage]:
        """Cerca email per pattern subject/sender/date."""
        messages = self.fetch_inbox(limit=limit * 2, unseen_only=False, since=since)
        results = []
        for msg in messages:
            if subject_pattern and not re.search(subject_pattern, msg.subject, re.IGNORECASE):
                continue
            if from_pattern and not re.search(from_pattern, msg.from_addr, re.IGNORECASE):
                continue
            results.append(msg)
            if len(results) >= limit:
                break
        return results

    # -----------------------------------------------------------------------
    # Monitoring continuo
    # -----------------------------------------------------------------------

    def monitor_inbox(
        self,
        callback: Callable[[EmailMessage], None],
        interval_seconds: int = 60,
        mark_read: bool = True,
        run_once: bool = False,
    ) -> None:
        """Monitora l'inbox e invoca callback per ogni nuova email non letta.

        Args:
            callback: funzione da chiamare per ogni email ricevuta
            interval_seconds: intervallo di polling (default 60s)
            mark_read: segna come lette dopo l'elaborazione
            run_once: se True, controlla una volta ed esce (per test/cron)
        """
        log.info(f"Avvio monitor inbox (intervallo: {interval_seconds}s)")

        # Track email già processate per evitare duplicati
        processed_ids: set[str] = set()

        while True:
            try:
                messages = self.fetch_inbox(limit=20, unseen_only=True)
                new_count = 0
                for msg in messages:
                    if msg.message_id and msg.message_id in processed_ids:
                        continue
                    processed_ids.add(msg.message_id)
                    new_count += 1

                    log.info(
                        f"Nuova email da {msg.from_addr} | subject='{msg.subject}'"
                    )
                    try:
                        callback(msg)
                    except Exception as e:
                        log.error(f"Errore callback per email {msg.message_id}: {e}")

                    if mark_read and msg.message_id:
                        self.mark_as_read(msg.message_id)

                if new_count == 0:
                    log.debug(f"Nessuna nuova email ({len(messages)} controllate)")

            except KeyboardInterrupt:
                log.info("Monitor fermato da utente")
                break
            except Exception as e:
                log.error(f"Errore monitor: {e}")

            if run_once:
                break
            time.sleep(interval_seconds)


# ---------------------------------------------------------------------------
# CLI per test
# ---------------------------------------------------------------------------

def _test_send() -> bool:
    """Test invio email."""
    n = LiberoNotifier()
    return n.send_email(
        to=n.email,
        subject="[WinBet] Test invio",
        body=f"Email di test inviata il {datetime.now().isoformat()}\n\nWinBet funziona!",
    )


def _test_fetch() -> list[EmailMessage]:
    """Test lettura inbox."""
    n = LiberoNotifier()
    messages = n.fetch_inbox(limit=5, unseen_only=False)
    log.info(f"Trovate {len(messages)} email in inbox")
    for m in messages:
        log.info(f"  - Da: {m.from_addr} | Subject: {m.subject}")
    return messages


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Libero Mail Notifier per WinBet")
    sub = parser.add_subparsers(dest="command")

    p_test_send = sub.add_parser("test-send", help="Invia email di test a se stesso")
    p_test_fetch = sub.add_parser("test-fetch", help="Leggi inbox di test")
    p_monitor = sub.add_parser("monitor", help="Avvia monitor continuo")
    p_monitor.add_argument("--interval", type=int, default=60, help="Intervallo polling (s)")

    args = parser.parse_args()

    if args.command == "test-send":
        success = _test_send()
        sys.exit(0 if success else 1)
    elif args.command == "test-fetch":
        _test_fetch()
    elif args.command == "monitor":
        def _default_callback(msg: EmailMessage) -> None:
            log.info(f"[CALLBACK] {msg.subject}: {msg.body[:200]}")

        n = LiberoNotifier()
        n.monitor_inbox(callback=_default_callback, interval_seconds=args.interval)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
