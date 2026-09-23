"""Optional Notification Hub delivery. Never break the existing Telegram path."""
import hashlib
import json
import logging
import os
from datetime import datetime
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

LOG = logging.getLogger(__name__)

def utf8_chunks(text: str, max_bytes: int = 2300) -> list[str]:
    """Keep every Unicode character and fit each body under FCM's 4 KiB data budget."""
    if max_bytes < 4:
        raise ValueError("Chunk budget too small")
    parts, current, size = [], [], 0
    for char in text:
        width = len(char.encode("utf-8"))
        if current and size + width > max_bytes:
            parts.append("".join(current))
            current, size = [], 0
        current.append(char)
        size += width
    if current:
        parts.append("".join(current))
    return parts or [""]


def send_hub(source_id: str, message: str, title: str, *, event_id: str | None = None) -> bool:
    url = os.getenv("NH_BRIDGE_URL", "").strip()
    key = os.getenv("NH_BRIDGE_KEY", "").strip()
    if not url or not key:
        return False
    if not url.startswith("https://"):
        LOG.warning("Notification Hub bridge requires HTTPS")
        return False
    if event_id is None:
        kst_day = datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat()
        signature = hashlib.sha256((kst_day + "\n" + message).encode("utf-8")).hexdigest()[:24]
        event_id = f"{source_id}-{signature}"
    parts = utf8_chunks(message)
    all_accepted = True
    for index, part in enumerate(parts, start=1):
        part_id = event_id if len(parts) == 1 else f"{event_id}:{index}"
        part_title = title if len(parts) == 1 else f"{title} ({index}/{len(parts)})"
        event = {
            "sourceId": source_id, "eventId": part_id,
            "title": part_title[:180], "body": part,
            "severity": "normal", "inboxOnly": index > 1
        }
        request = Request(url, data=json.dumps(event, ensure_ascii=False).encode("utf-8"),
                          headers={"Authorization": "Bearer " + key,
                                   "Content-Type": "application/json"}, method="POST")
        try:
            with urlopen(request, timeout=12) as response:
                if response.status != 202:
                    all_accepted = False
        except Exception as error:
            # Never log secrets, complete private payloads or server response bodies.
            LOG.warning("Notification Hub delivery failed (%s); Telegram delivery is unaffected",
                        type(error).__name__)
            all_accepted = False
    return all_accepted
