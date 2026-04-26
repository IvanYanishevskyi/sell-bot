from __future__ import annotations

import imaplib
import re
from dataclasses import dataclass
from email import message_from_bytes
from email.message import Message
from email.policy import default
from html import unescape


@dataclass
class InboxMessage:
    uid: str
    subject: str
    from_email: str
    message_id: str
    body_text: str


class ImapOrderReader:
    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        port: int = 993,
        folder: str = "INBOX",
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.folder = folder

    def fetch_unseen(self, limit: int = 10) -> list[InboxMessage]:
        conn = imaplib.IMAP4_SSL(self.host, self.port)
        try:
            conn.login(self.username, self.password)
            status, _ = conn.select(self.folder)
            if status != "OK":
                return []

            status, data = conn.uid("search", None, "UNSEEN")
            if status != "OK" or not data or not data[0]:
                return []

            uids = [u.decode("utf-8") for u in data[0].split()]
            messages: list[InboxMessage] = []

            for uid in uids[-limit:]:
                status, payload = conn.uid("fetch", uid, "(BODY.PEEK[])")
                if status != "OK" or not payload:
                    continue

                raw_bytes = self._extract_raw_bytes(payload)
                if not raw_bytes:
                    continue

                msg = message_from_bytes(raw_bytes, policy=default)
                messages.append(
                    InboxMessage(
                        uid=uid,
                        subject=str(msg.get("Subject", "")).strip(),
                        from_email=str(msg.get("From", "")).strip(),
                        message_id=str(msg.get("Message-ID", "")).strip(),
                        body_text=self._extract_body_text(msg),
                    )
                )
            return messages
        finally:
            conn.logout()

    def mark_seen(self, uid: str) -> None:
        conn = imaplib.IMAP4_SSL(self.host, self.port)
        try:
            conn.login(self.username, self.password)
            status, _ = conn.select(self.folder)
            if status != "OK":
                return
            conn.uid("store", uid, "+FLAGS", "(\\Seen)")
        finally:
            conn.logout()

    @staticmethod
    def _extract_raw_bytes(payload: list[tuple[bytes, bytes] | bytes]) -> bytes:
        for part in payload:
            if isinstance(part, tuple) and len(part) > 1 and isinstance(part[1], bytes):
                return part[1]
        return b""

    def _extract_body_text(self, msg: Message) -> str:
        plain_parts: list[str] = []
        html_parts: list[str] = []

        if msg.is_multipart():
            for part in msg.walk():
                disposition = (part.get("Content-Disposition") or "").lower()
                if "attachment" in disposition:
                    continue
                content_type = part.get_content_type()
                if content_type == "text/plain":
                    plain_parts.append(self._part_content(part))
                elif content_type == "text/html":
                    html_parts.append(self._part_content(part))
        else:
            content_type = msg.get_content_type()
            if content_type == "text/plain":
                plain_parts.append(self._part_content(msg))
            elif content_type == "text/html":
                html_parts.append(self._part_content(msg))

        if plain_parts:
            return "\n".join(p for p in plain_parts if p).strip()
        if html_parts:
            html = "\n".join(h for h in html_parts if h)
            return self._html_to_text(html)
        return ""

    @staticmethod
    def _part_content(part: Message) -> str:
        try:
            content = part.get_content()
        except Exception:
            payload = part.get_payload(decode=True) or b""
            charset = part.get_content_charset() or "utf-8"
            try:
                return payload.decode(charset, errors="replace")
            except LookupError:
                return payload.decode("utf-8", errors="replace")

        if isinstance(content, bytes):
            charset = part.get_content_charset() or "utf-8"
            try:
                return content.decode(charset, errors="replace")
            except LookupError:
                return content.decode("utf-8", errors="replace")
        return str(content)

    @staticmethod
    def _html_to_text(html: str) -> str:
        text = re.sub(r"<br\\s*/?>", "\n", html, flags=re.IGNORECASE)
        text = re.sub(r"</p>", "\n", text, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = unescape(text)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n\s*\n+", "\n", text)
        return text.strip()
