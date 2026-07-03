"""refresh CLI.

GitHub Actions(또는 수동)가 호출한다.
환경변수: FRED_API_KEY, TELEGRAM_*, CACHE_BACKEND(+HF_* if hf_dataset).
성공/부분성공이면 exit 0, 실패면 exit 1.
"""
from __future__ import annotations

import json
import logging
import sys

from riskradar.refresh_service import run_refresh

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s %(message)s")


def main() -> int:
    status = run_refresh(notify=True)
    print(json.dumps(status, ensure_ascii=False, indent=2))
    return 0 if status.get("status") in ("success", "partial_success") else 1


if __name__ == "__main__":
    sys.exit(main())
