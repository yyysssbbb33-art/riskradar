"""Optional Notification Hub delivery. Never break the existing Telegram path."""
import hashlib
import json
import logging
import os
from datetime import datetime
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

LOG = logging.getLogger(__name__)

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
    event = {
        "sourceId": source_id, "eventId": event_id,
        "title": title[:180], "body": message[:5000],
        "severity": "normal"
    }
    request = Request(url, data=json.dumps(event, ensure_ascii=False).encode("utf-8"),
                      headers={"Authorization": "Bearer " + key,
                               "Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(request, timeout=12) as response:
            return response.status == 202
    except Exception as error:
        # Never log secrets, complete private payloads or server response bodies.
        LOG.warning("Notification Hub delivery failed (%s); Telegram delivery is unaffected",
                    type(error).__name__)
        return False
