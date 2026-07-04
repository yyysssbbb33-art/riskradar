from riskradar.interpretation_cards import get_interpretation_card


def test_t10y3m_card_has_all_eight_sections():
    card = get_interpretation_card("T10Y3M")
    for n in range(1, 9):
        assert f"### {n}." in card
    assert "New York Fed" in card
    assert "12개월 뒤 침체 확률" in card


def test_hyoas_card_has_all_eight_sections():
    card = get_interpretation_card("HYOAS")
    for n in range(1, 9):
        assert f"### {n}." in card
    assert "추가 금리 보상" in card
    assert "BAMLH0A0HYM2" in card


def test_unfinished_indicator_returns_placeholder():
    card = get_interpretation_card("VIX")
    assert "준비 중" in card
