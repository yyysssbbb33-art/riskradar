from riskradar.interpretation_cards import get_interpretation_card


def test_all_six_cards_have_eight_sections():
    for key in ["VIX", "HYOAS", "T10Y3M", "DGS30", "DGS2", "DFII10"]:
        card = get_interpretation_card(key)
        for n in range(1, 9):
            assert f"### {n}." in card, (key, n)


def test_t10y3m_card_keeps_nyfed_evidence():
    card = get_interpretation_card("T10Y3M")
    assert "New York Fed" in card
    assert "12개월 뒤 침체 확률" in card


def test_hyoas_card_keeps_series_and_plain_language():
    card = get_interpretation_card("HYOAS")
    assert "추가 금리" in card
