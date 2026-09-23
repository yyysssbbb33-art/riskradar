import os
from unittest.mock import patch
from riskradar.hub_delivery import send_hub, utf8_chunks
from riskradar.telegram_client import send as send_telegram

def test_missing_bridge_configuration_is_noop():
    with patch.dict(os.environ, {"NH_BRIDGE_URL": "", "NH_BRIDGE_KEY": ""}):
        assert send_hub("riskradar", "시장 업데이트", "RiskRadar") is False

def test_non_https_bridge_is_rejected():
    with patch.dict(os.environ, {"NH_BRIDGE_URL": "http://localhost", "NH_BRIDGE_KEY": "x"}):
        assert send_hub("riskradar", "시장 업데이트", "RiskRadar") is False

def test_long_korean_report_is_not_truncated():
    report = "RiskRadar 업데이트\\n" + "미국 국채금리 및 회사채 변화 · " * 250
    parts = utf8_chunks(report)
    assert len(parts) > 1
    assert "".join(parts) == report
    assert all(len(part.encode("utf-8")) <= 2300 for part in parts)

def test_hub_mirror_is_attempted_when_telegram_fails():
    with patch("riskradar.telegram_client.requests.post", side_effect=RuntimeError("telegram down")), \
         patch("riskradar.hub_delivery.send_hub") as mirror:
        assert send_telegram("시장 업데이트", token="token", chat_id="chat") is False
        mirror.assert_called_once()
