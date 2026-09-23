import os
from unittest.mock import patch
from riskradar.hub_delivery import send_hub

def test_missing_bridge_configuration_is_noop():
    with patch.dict(os.environ, {"NH_BRIDGE_URL": "", "NH_BRIDGE_KEY": ""}):
        assert send_hub("riskradar", "시장 업데이트", "RiskRadar") is False

def test_non_https_bridge_is_rejected():
    with patch.dict(os.environ, {"NH_BRIDGE_URL": "http://localhost", "NH_BRIDGE_KEY": "x"}):
        assert send_hub("riskradar", "시장 업데이트", "RiskRadar") is False
