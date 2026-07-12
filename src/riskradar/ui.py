"""읽기 전용 Gradio UI.

캐시(data_status.json + 산출물)만 읽는다. 절대 refresh 하지 않는다.
내부 컬럼명은 데이터 호환성을 위해 유지하고 사용자 화면에서는 쉬운 한국어 표현만 사용한다.
"""
from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import gradio as gr
import pandas as pd

from . import axis_engine, cache_store, interpretation_engine
from . import config as C
from . import aux_config as AC
from . import rate_composition as RC
from . import rate_view as RV
from .context_view import render_credit_context_html, render_rate_context_html
from .display_text import (LABEL_1M, LABEL_3M, LABEL_3Y, LABEL_5Y, LABEL_10Y,
                           aux_name, axis_name, core_name, lens_name, plain_language, state_name)
from .formatting import fmt_change, fmt_pct, fmt_value
from .credit_timeline import (
    build_credit_timeline,
    render_credit_timeline_html,
    render_credit_timeline_markdown,
    render_past_credit_episodes_compact_markdown,
    render_past_credit_episodes_markdown,
)
from .aux_detail_view import render_aux_detail
from .indicator_detail_view import render_indicator_detail
from .relationship_guide import RELATIONSHIP_GUIDE
from .today_view import render_credit_episode_markdown, render_today_markdown, render_today_summary_markdown
from .overview_view import (
    render_core_cards_html, render_credit_range_map_html, render_data_basis_html,
    render_data_health_badge, render_decision_basis_markdown, render_domain_strip_html,
    render_evidence_balance_markdown, render_key_indicator_cards_html,
    render_market_interpretation_html, render_next_checks_html, render_next_checks_markdown,
    render_recent_changes_html, render_recent_changes_markdown, render_remaining_changes_html,
    render_remaining_changes_markdown, render_status_cards_html, render_status_changes_html,
    render_today_one_line_markdown,
)
from .monthly_view import reconstruct_history_from_chart_data, render_monthly_markdown
from .dashboard_snapshot import DashboardSnapshot, load_dashboard_snapshot
from .version import __version__
from .user_copy import render_static_explainer

KST = ZoneInfo(C.APP_TIMEZONE)


APP_CSS = r"""
.gradio-container { max-width:1180px !important; }
.rr-app-head { display:flex; align-items:flex-end; justify-content:space-between; gap:12px; margin:2px 0 6px; }
.rr-app-head h1 { margin:0; font-size:clamp(1.65rem,4vw,2.25rem); line-height:1.05; }
.rr-app-head p { margin:4px 0 0; opacity:.72; }
.rr-section { margin:18px 0 6px; }
.rr-compact-section { margin-top:12px; }
.rr-section-title { display:flex; align-items:center; justify-content:space-between; gap:10px; margin-bottom:9px; }
.rr-section-title h2 { margin:0; font-size:1.18rem; line-height:1.2; }
.rr-section-title > span { font-size:.82rem; opacity:.7; }
.rr-count { display:inline-flex; min-width:26px; height:26px; border-radius:999px; align-items:center; justify-content:center; background:var(--background-fill-secondary); font-weight:800; opacity:1 !important; }
.rr-empty, .rr-muted, .rr-quiet-line, .rr-info-box { border:1px solid var(--border-color-primary); border-radius:12px; padding:11px 12px; margin:7px 0; }
.rr-muted, .rr-quiet-line { opacity:.78; background:var(--background-fill-secondary); }
.rr-info-box { font-size:.86rem; line-height:1.55; opacity:.84; background:var(--background-fill-secondary); }
.rr-more { margin-top:8px; font-size:.86rem; opacity:.72; }

/* 현황: 상태 복구 중심 */
.rr-data-basis { font-size:.86rem; color:var(--body-text-color-subdued); margin:4px 0 10px; }
.rr-data-warning { border:1px solid color-mix(in srgb, var(--rr-amber, #d68b1f) 52%, var(--border-color-primary)); border-radius:12px; padding:10px 12px; background:color-mix(in srgb, var(--rr-amber, #d68b1f) 8%, var(--background-fill-primary)); color:var(--body-text-color); }
.rr-status-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:12px; }
.rr-status-card { border:1px solid var(--border-color-primary); border-radius:18px; padding:15px; background:var(--background-fill-primary); min-width:0; box-shadow:0 5px 18px rgba(20,32,55,.045); }
.rr-status-kicker { font-size:.78rem; font-weight:900; color:var(--body-text-color-subdued); }
.rr-status-card h2 { margin:5px 0 1px; font-size:1.35rem; letter-spacing:-.03em; }
.rr-status-card p { margin:0; font-size:.86rem; color:var(--body-text-color-subdued); }
.rr-status-value { margin-top:12px; font-size:1.7rem; font-weight:950; letter-spacing:-.04em; }
.rr-status-state { display:inline-flex; margin-top:6px; border-radius:999px; padding:3px 8px; background:color-mix(in srgb, currentColor 7%, transparent); font-weight:900; }
.rr-status-change { margin-top:8px; font-size:.88rem; font-weight:850; color:var(--body-text-color-subdued); }
.rr-status-change span { font-weight:400; opacity:.72; margin-left:3px; }
.rr-status-meta { margin-top:7px; font-size:.8rem; color:var(--body-text-color-subdued); }
.rr-relation-line { margin-top:11px; padding-top:10px; border-top:1px solid var(--border-color-primary); font-size:.86rem; line-height:1.45; }
.rr-interpretation-grid { display:grid; grid-template-columns:2fr 1fr; gap:10px; }
.rr-interpretation-grid > div { border:1px solid var(--border-color-primary); border-radius:14px; padding:12px; background:var(--background-fill-primary); }
.rr-interpretation-grid strong { display:block; margin-bottom:5px; }
.rr-interpretation-grid p { margin:4px 0; line-height:1.48; }
.rr-mini-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:9px; }
.rr-mini-card { border:1px solid var(--border-color-primary); border-radius:14px; padding:12px; background:var(--background-fill-primary); min-width:0; box-shadow:0 5px 18px rgba(20,32,55,.035); }
.rr-change-list { list-style:none; padding:0; margin:8px 0; border:1px solid var(--border-color-primary); border-radius:14px; overflow:hidden; }
.rr-change-list li { display:grid; grid-template-columns:150px minmax(0,1fr); gap:10px; padding:11px 12px; border-bottom:1px solid var(--border-color-primary); }
.rr-change-list li:last-child { border-bottom:none; }
.rr-change-list span { color:var(--body-text-color-subdued); }

/* 구 현황 카드 호환 */
.rr-domain-strip { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:9px; margin:8px 0 16px; }
.rr-domain-card { border:1px solid var(--border-color-primary); border-radius:14px; padding:12px; background:var(--background-fill-primary); min-width:0; }
.rr-domain-card small { display:block; opacity:.65; font-weight:700; margin-bottom:6px; }
.rr-domain-metric { display:flex; align-items:baseline; justify-content:space-between; gap:6px; }
.rr-domain-metric strong { font-size:.9rem; opacity:.72; }
.rr-domain-metric b { font-size:1.18rem; white-space:nowrap; }
.rr-domain-state { margin-top:8px; font-weight:800; font-size:.84rem; line-height:1.25; min-height:2.1em; }
.rr-domain-change { margin-top:6px; font-size:.8rem; font-weight:700; white-space:nowrap; }
.rr-domain-change span { font-weight:400; opacity:.58; margin-left:3px; }

/* 새 변화 사건 카드 */
.rr-event-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:10px; }
.rr-event-card { border:1px solid var(--border-color-primary); border-radius:14px; padding:13px; background:var(--background-fill-primary); min-width:0; }
.rr-event-head { display:flex; justify-content:space-between; gap:8px; font-size:.84rem; }
.rr-event-head span { opacity:.58; }
.rr-event-title { font-size:1.04rem; font-weight:800; margin:10px 0 8px; line-height:1.35; }
.rr-event-path { font-size:.82rem; opacity:.72; line-height:1.45; overflow-wrap:anywhere; }

/* 지속 칩 */
.rr-chip-row { display:flex; gap:8px; flex-wrap:wrap; }
.rr-chip { display:flex; align-items:center; gap:10px; border:1px solid var(--border-color-primary); border-radius:999px; padding:8px 11px; background:var(--background-fill-secondary); }
.rr-chip span { font-size:.84rem; }
.rr-chip strong { font-size:1rem; white-space:nowrap; }

/* 신용 2x2 */
.rr-credit-visual { margin:0; }
.rr-credit-grid-2x2 { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:9px; }
.rr-credit-tile { border:1px solid var(--border-color-primary); border-radius:14px; padding:13px; min-width:0; background:var(--background-fill-primary); }
.rr-credit-tile-hot { border-width:2px; box-shadow:0 4px 14px rgba(0,0,0,.05); }
.rr-credit-tile-quiet { background:var(--background-fill-secondary); }
.rr-credit-tile-head { display:flex; flex-direction:column; gap:2px; }
.rr-credit-tile-head strong { font-size:1.2rem; }
.rr-credit-tile-head small { opacity:.64; }
.rr-credit-tile-value { margin-top:12px; font-size:1.35rem; font-weight:900; }
.rr-credit-tile-state { margin-top:6px; font-weight:800; line-height:1.35; min-height:1.4em; }
.rr-credit-tile-change { margin-top:6px; font-size:.82rem; font-weight:700; }
.rr-credit-tile-change span { opacity:.58; font-weight:400; margin-left:3px; }
.rr-credit-scope { margin:10px 1px 7px; font-size:.9rem; line-height:1.45; }
.rr-credit-lens-line { display:grid; grid-template-columns:auto auto minmax(0,1fr); gap:12px; align-items:center; padding:10px 11px; border-radius:10px; background:var(--background-fill-secondary); font-size:.83rem; }
.rr-credit-lens-line > div:first-child span, .rr-credit-lens-line > div:first-child strong { display:block; }
.rr-credit-lens-line > div:first-child strong { margin-top:2px; font-size:1rem; }
.rr-credit-lens-change { font-weight:800; white-space:nowrap; }
.rr-credit-lens-change span { font-weight:400; opacity:.58; }
.rr-credit-lens-line em { font-style:normal; opacity:.76; text-align:right; }

/* 30년 금리 시각 브리핑 */
.rr-rate-panel { border:1px solid var(--border-color-primary); border-radius:16px; padding:14px; background:var(--background-fill-primary); }
.rr-rate-total { font-size:1.15rem !important; font-weight:900; opacity:1 !important; }
.rr-rate-head { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:10px; margin-bottom:8px; }
.rr-rate-head > div { padding:10px 11px; border-radius:11px; background:var(--background-fill-secondary); }
.rr-rate-head span, .rr-rate-head strong { display:block; }
.rr-rate-head span { font-size:.76rem; opacity:.62; }
.rr-rate-head strong { margin-top:4px; font-size:1.2rem; }
.rr-rate-kicker { font-size:.78rem; opacity:.64; margin:-2px 0 12px; }
.rr-rate-row { margin:12px 0; }
.rr-rate-label { display:flex; align-items:baseline; justify-content:space-between; gap:10px; font-size:.88rem; }
.rr-rate-label strong { white-space:nowrap; }
.rr-rate-label small, .rr-rate-opposite small { display:block; margin-top:2px; font-size:.74rem; opacity:.64; font-weight:400; }
.rr-rate-track { height:8px; border-radius:999px; background:var(--background-fill-secondary); overflow:hidden; margin-top:6px; }
.rr-rate-fill { display:block; height:100%; border-radius:999px; background:currentColor; opacity:.68; }
.rr-rate-up { color:var(--button-primary-background-fill, currentColor); }
.rr-rate-down { color:var(--body-text-color-subdued, currentColor); }
.rr-rate-flat { opacity:.35; }
.rr-rate-opposite { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:8px; margin:10px 0; }
.rr-rate-opposite > div { border:1px solid var(--border-color-primary); border-radius:11px; padding:10px; background:var(--background-fill-secondary); }
.rr-rate-opposite span, .rr-rate-opposite strong { display:block; }
.rr-rate-opposite span { font-size:.8rem; opacity:.68; }
.rr-rate-opposite strong { margin-top:5px; font-size:1rem; }
.rr-rate-conclusion { margin-top:12px; font-weight:800; }
.rr-rate-curve { margin-top:8px; font-size:.82rem; opacity:.72; line-height:1.45; }


/* v0.8.0 공통 숫자 카드·표 */
.rr-metric-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:9px; margin:8px 0 14px; }
.rr-metric-card { border:1px solid var(--border-color-primary); border-radius:14px; padding:13px; background:var(--background-fill-primary); min-width:0; }
.rr-metric-card-hot { border-width:2px; box-shadow:0 4px 14px rgba(0,0,0,.045); }
.rr-metric-card-quiet { background:var(--background-fill-secondary); }
.rr-metric-name { font-weight:900; font-size:1rem; }
.rr-metric-subtitle { font-size:.76rem; opacity:.62; margin-top:2px; min-height:1.2em; }
.rr-metric-value { font-size:1.45rem; font-weight:900; margin:12px 0 5px; }
.rr-metric-state { font-size:.84rem; font-weight:800; min-height:1.3em; }
.rr-metric-change { margin-top:7px; font-size:.84rem; font-weight:800; }
.rr-metric-change span { font-weight:400; opacity:.58; margin-left:3px; }
.rr-panel { border:1px solid var(--border-color-primary); border-radius:16px; padding:14px; margin:12px 0; background:var(--background-fill-primary); }
.rr-curve-pair { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:8px; }
.rr-curve-pair > div { border-radius:11px; padding:11px; background:var(--background-fill-secondary); }
.rr-curve-pair span, .rr-curve-pair strong { display:block; }
.rr-curve-pair span { opacity:.62; font-size:.8rem; }
.rr-curve-pair strong { margin-top:4px; font-size:1.08rem; }
.rr-curve-summary { margin-top:11px; display:flex; justify-content:space-between; gap:10px; align-items:center; }
.rr-technical-term { opacity:.58; font-size:.78rem; white-space:nowrap; }
.rr-table-wrap { width:100%; overflow-x:auto; margin:8px 0 14px; }
.rr-compact-table { width:100%; border-collapse:collapse; font-size:.88rem; }
.rr-compact-table th, .rr-compact-table td { padding:10px 9px; border-bottom:1px solid var(--border-color-primary); text-align:right; }
.rr-compact-table th:first-child, .rr-compact-table td:first-child { text-align:left; }
.rr-compact-table thead th { font-size:.78rem; opacity:.68; }


/* v0.8.4 신용·금리 공통 관계 카드 */
.rr-tab-intro { margin:2px 0 11px; color:var(--body-text-color-subdued); line-height:1.55; }
.rr-context-section { margin:18px 0 16px; }
.rr-context-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:10px; }
.rr-context-card { border:1px solid var(--border-color-primary); border-radius:14px; padding:13px; background:var(--background-fill-primary); min-width:0; box-shadow:0 5px 18px rgba(20,32,55,.045); }
.rr-context-domain-credit { border-top:3px solid color-mix(in srgb, var(--rr-amber, #d68b1f) 72%, transparent); }
.rr-context-domain-rate { border-top:3px solid color-mix(in srgb, var(--rr-blue, #4f73d9) 72%, transparent); }
.rr-context-kicker { color:var(--body-text-color-subdued); font-size:.76rem; font-weight:800; }
.rr-context-card h3 { margin:4px 0 10px; font-size:1rem; letter-spacing:-.015em; }
.rr-context-metrics { border-top:1px solid var(--border-color-primary); }
.rr-context-metric { display:grid; grid-template-columns:minmax(0,1fr) auto auto; gap:9px; align-items:center; padding:8px 0; border-bottom:1px solid var(--border-color-primary); font-size:.82rem; }
.rr-context-metric div { min-width:0; }
.rr-context-metric strong, .rr-context-metric small { display:block; }
.rr-context-metric small { margin-top:2px; color:var(--body-text-color-subdued); font-weight:400; }
.rr-context-metric span, .rr-context-metric b { white-space:nowrap; }
.rr-context-reading { margin-top:10px; line-height:1.5; font-size:.87rem; }
.rr-context-caution { margin-top:9px; padding-top:8px; border-top:1px dashed var(--border-color-primary); color:var(--body-text-color-subdued); font-size:.78rem; line-height:1.45; }

/* 두 전문 탭의 핵심 카드 문법을 동일하게 맞춘다. */
.rr-credit-grid-2x2, .rr-rate-overview-grid { gap:9px; margin:8px 0 14px; }
.rr-credit-tile, .rr-metric-card { border-radius:14px; padding:13px; }
.rr-credit-tile-head strong, .rr-metric-name { font-size:1rem; font-weight:900; }
.rr-credit-tile-head small, .rr-metric-subtitle { font-size:.76rem; opacity:.62; min-height:1.2em; }
.rr-credit-tile-value, .rr-metric-value { font-size:1.45rem; margin:12px 0 5px; }
.rr-credit-tile-state, .rr-metric-state { font-size:.84rem; min-height:1.3em; }
.rr-credit-tile-change, .rr-metric-change { margin-top:7px; font-size:.84rem; }

/* v0.8.1 Visual Polish: 차분한 금융 대시보드 색 체계 */
.gradio-container {
  --rr-blue:#4f73d9;
  --rr-purple:#7b67c8;
  --rr-amber:#d68b1f;
  --rr-red:#cf5b5b;
  --rr-teal:#2f9a8a;
  --rr-green:#3a9565;
  --rr-slate:#718096;
  background:color-mix(in srgb, var(--background-fill-secondary) 38%, var(--background-fill-primary));
}
.rr-app-head { padding:10px 2px 4px; }
.rr-app-head h1 { letter-spacing:-.035em; }
.rr-app-head strong { color:var(--rr-blue); font-size:.82rem; }
.rr-section-title h2 { letter-spacing:-.02em; }
.rr-section-title > span, .rr-muted, .rr-info-box { color:var(--body-text-color-subdued); }

.rr-domain-card, .rr-event-card, .rr-credit-tile, .rr-metric-card, .rr-core-card, .rr-panel, .rr-rate-panel {
  box-shadow:0 5px 18px rgba(20,32,55,.045);
  transition:border-color .16s ease, box-shadow .16s ease, transform .16s ease;
}
.rr-domain-card:hover, .rr-event-card:hover, .rr-credit-tile:hover, .rr-metric-card:hover, .rr-core-card:hover {
  transform:translateY(-1px);
  box-shadow:0 8px 24px rgba(20,32,55,.075);
}
.rr-domain-credit { border-top:3px solid color-mix(in srgb, var(--rr-amber) 72%, transparent); }
.rr-domain-rate { border-top:3px solid color-mix(in srgb, var(--rr-blue) 72%, transparent); }
.rr-domain-vol { border-top:3px solid color-mix(in srgb, var(--rr-purple) 72%, transparent); }

.rr-state-quiet { border-color:color-mix(in srgb, var(--rr-slate) 24%, var(--border-color-primary)); }
.rr-state-watch {
  border-color:color-mix(in srgb, var(--rr-amber) 58%, var(--border-color-primary));
  background:linear-gradient(145deg, color-mix(in srgb, var(--rr-amber) 9%, var(--background-fill-primary)), var(--background-fill-primary) 62%);
}
.rr-state-hot {
  border-color:color-mix(in srgb, var(--rr-red) 64%, var(--border-color-primary));
  background:linear-gradient(145deg, color-mix(in srgb, var(--rr-red) 10%, var(--background-fill-primary)), var(--background-fill-primary) 64%);
}
.rr-state-easing {
  border-color:color-mix(in srgb, var(--rr-teal) 58%, var(--border-color-primary));
  background:linear-gradient(145deg, color-mix(in srgb, var(--rr-teal) 9%, var(--background-fill-primary)), var(--background-fill-primary) 64%);
}
.rr-state-done {
  border-color:color-mix(in srgb, var(--rr-green) 55%, var(--border-color-primary));
  background:linear-gradient(145deg, color-mix(in srgb, var(--rr-green) 8%, var(--background-fill-primary)), var(--background-fill-primary) 64%);
}
.rr-state-watch .rr-domain-state, .rr-state-watch .rr-core-state, .rr-state-watch .rr-credit-tile-state, .rr-state-watch .rr-metric-state { color:var(--rr-amber); }
.rr-state-hot .rr-domain-state, .rr-state-hot .rr-core-state, .rr-state-hot .rr-credit-tile-state, .rr-state-hot .rr-metric-state { color:var(--rr-red); }
.rr-state-easing .rr-domain-state, .rr-state-easing .rr-core-state, .rr-state-easing .rr-credit-tile-state, .rr-state-easing .rr-metric-state { color:var(--rr-teal); }
.rr-state-done .rr-domain-state, .rr-state-done .rr-core-state, .rr-state-done .rr-credit-tile-state, .rr-state-done .rr-metric-state { color:var(--rr-green); }

.rr-domain-metric b, .rr-credit-tile-value, .rr-metric-value, .rr-core-value { letter-spacing:-.035em; }
.rr-domain-state, .rr-credit-tile-state, .rr-metric-state, .rr-core-state {
  display:inline-flex;
  width:fit-content;
  align-items:center;
  border-radius:999px;
  padding:3px 7px;
  background:color-mix(in srgb, currentColor 7%, transparent);
}
.rr-domain-state { margin-top:8px; }
.rr-core-state { max-width:58%; }
.rr-credit-tile-change, .rr-metric-change, .rr-core-change, .rr-domain-change { color:var(--body-text-color-subdued); }
.rr-credit-scope {
  border-left:3px solid color-mix(in srgb, var(--rr-amber) 55%, transparent);
  padding:8px 10px;
  background:color-mix(in srgb, var(--rr-amber) 5%, transparent);
  border-radius:0 10px 10px 0;
}
.rr-credit-lens-line { border:1px solid color-mix(in srgb, var(--rr-amber) 22%, var(--border-color-primary)); }
.rr-chip { box-shadow:0 3px 10px rgba(20,32,55,.035); }
.rr-chip strong { color:var(--rr-blue); }
.rr-event-card { border-left:4px solid color-mix(in srgb, var(--rr-blue) 68%, transparent); }
.rr-event-title { letter-spacing:-.015em; }
.rr-count { color:var(--rr-blue); background:color-mix(in srgb, var(--rr-blue) 10%, var(--background-fill-secondary)); }

.rr-compact-table { border:1px solid var(--border-color-primary); border-radius:12px; overflow:hidden; }
.rr-compact-table thead th {
  background:color-mix(in srgb, var(--rr-blue) 7%, var(--background-fill-secondary));
  color:var(--body-text-color-subdued);
  opacity:1;
}
.rr-compact-table tbody tr:last-child th, .rr-compact-table tbody tr:last-child td { border-bottom:none; }
.rr-compact-table tbody tr:hover { background:color-mix(in srgb, var(--rr-blue) 4%, transparent); }
.rr-rate-fill.rr-rate-up, .rr-rate-up .rr-rate-fill { color:var(--rr-amber); }
.rr-rate-fill.rr-rate-down, .rr-rate-down .rr-rate-fill { color:var(--rr-teal); }
.rr-curve-pair > div:first-child { border-left:3px solid color-mix(in srgb, var(--rr-purple) 60%, transparent); }
.rr-curve-pair > div:last-child { border-left:3px solid color-mix(in srgb, var(--rr-blue) 60%, transparent); }
.rr-technical-term { padding:3px 7px; border-radius:999px; background:var(--background-fill-secondary); }

.rr-detail-accordion { border-radius:14px !important; overflow:hidden; }
.rr-detail-accordion > * { border-color:color-mix(in srgb, var(--rr-blue) 14%, var(--border-color-primary)) !important; }

/* 핵심 6개: desktop 3x2, mobile 2x3 */
.rr-core-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:10px; margin:8px 0 10px; }
.rr-core-card { border:1px solid var(--border-color-primary); border-radius:14px; padding:12px; min-width:0; background:var(--background-fill-primary); }
.rr-core-card-hot { border-width:2px; box-shadow:0 4px 14px rgba(0,0,0,.045); }
.rr-core-card-quiet { background:var(--background-fill-secondary); }
.rr-core-head { display:flex; justify-content:space-between; gap:6px; align-items:flex-start; }
.rr-core-head > strong { font-size:.96rem; }
.rr-core-state { font-size:.74rem; text-align:right; line-height:1.25; }
.rr-core-value { font-size:1.45rem; font-weight:900; margin:11px 0 3px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.rr-core-change { font-size:.86rem; font-weight:700; }
.rr-core-change small { font-weight:400; opacity:.62; margin-left:4px; }
.rr-core-spark { font-family:monospace; letter-spacing:.5px; font-size:.83rem; opacity:.58; overflow:hidden; white-space:nowrap; margin-top:8px; }

/* 오늘의 핵심 2개 */
.rr-brief-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px; margin:18px 0; align-items:start; }

/* 확인 포인트 */
.rr-next-list { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:9px; }
.rr-next-item { display:flex; gap:10px; align-items:flex-start; border-top:2px solid var(--border-color-primary); padding:10px 3px 2px; }
.rr-next-num { display:flex; align-items:center; justify-content:center; width:25px; height:25px; border-radius:999px; background:var(--background-fill-secondary); font-weight:900; flex:0 0 auto; }
.rr-next-item strong, .rr-next-item small { display:block; }
.rr-next-item small { opacity:.68; margin-top:3px; line-height:1.4; }

/* 최근 90일 */
.rr-timeline { margin:8px 0; }
.rr-timeline-list { display:flex; flex-direction:column; }
.rr-timeline-row { display:grid; grid-template-columns:86px 48px minmax(0,1fr); gap:9px; align-items:start; padding:11px 0; border-bottom:1px solid var(--border-color-primary); }
.rr-timeline-row time { font-size:.8rem; opacity:.68; padding-top:2px; }
.rr-market-badge { display:inline-flex; justify-content:center; padding:3px 7px; border-radius:999px; background:var(--background-fill-secondary); font-size:.77rem; font-weight:900; }
.rr-timeline-event strong, .rr-timeline-event small { display:block; }
.rr-timeline-event small { margin-top:3px; opacity:.64; font-size:.79rem; }

@media (max-width:760px) {
  .rr-status-grid { grid-template-columns:1fr; }
  .rr-interpretation-grid { grid-template-columns:1fr; }
  .rr-mini-grid { grid-template-columns:repeat(2,minmax(0,1fr)); }
  .rr-change-list li { grid-template-columns:1fr; gap:4px; }
  .rr-domain-strip { grid-template-columns:repeat(3,minmax(0,1fr)); gap:6px; }
  .rr-domain-card { padding:10px 8px; }
  .rr-domain-metric { display:block; }
  .rr-domain-metric strong { font-size:.72rem; }
  .rr-domain-metric b { display:block; margin-top:2px; font-size:1rem; }
  .rr-domain-state { font-size:.74rem; min-height:2.4em; }
  .rr-domain-change { font-size:.72rem; }
  .rr-event-grid, .rr-next-list, .rr-brief-grid { grid-template-columns:1fr; }
  .rr-core-grid { grid-template-columns:repeat(2,minmax(0,1fr)); gap:8px; }
  .rr-core-card { padding:10px; }
  .rr-core-head { flex-direction:column; }
  .rr-core-state { text-align:left; }
  .rr-core-value { font-size:1.25rem; margin-top:8px; }
  .rr-core-change small { display:none; }
  .rr-timeline-row { grid-template-columns:76px 42px minmax(0,1fr); gap:6px; }
  .rr-chip { flex:1 1 calc(50% - 8px); justify-content:space-between; min-width:145px; }
  .rr-credit-lens-line { grid-template-columns:auto auto; }
  .rr-credit-lens-line em { grid-column:1 / -1; text-align:left; }
  .rr-metric-grid { grid-template-columns:repeat(2,minmax(0,1fr)); gap:7px; }
  .rr-metric-card { padding:11px; }
	  .rr-metric-value { font-size:1.25rem; }
	  .rr-curve-summary { align-items:flex-start; flex-direction:column; }
	}
@media (max-width:420px) {
  .rr-mini-grid, .rr-metric-grid, .rr-context-grid { grid-template-columns:1fr; }
}
"""


_UI_DATA_COMPATIBLE_VERSIONS = {
    "0.6.1": {"0.6.0", "0.6.1"},
    # v0.6.2는 기존 시장 판정 산출물을 유지하고 권위 있는 decision snapshot/diff를 추가한다.
    "0.6.2": {"0.6.0", "0.6.1", "0.6.2"},
    # v0.7.0은 v0.6.2 판정 산출물을 그대로 읽는 변화 중심 UI다.
    # v0.7.1은 v0.7.0 판정 산출물과 호환하며 동일 만기 금리 구성 artifact를 선택적으로 읽는다.
    "0.7.0": {"0.6.2", "0.7.0"},
    # v0.7.1은 새 금리 구성 artifact가 없으면 해당 패널만 안내문으로 대체한다.
    "0.7.1": {"0.7.0", "0.7.1"},
    # v0.7.2는 기존 신용 엔진 기록을 읽는 UI 계층만 추가한다.
    "0.7.2": {"0.7.0", "0.7.1", "0.7.2"},
    # v0.7.3은 versions 밖의 audit 원장만 추가하며 화면용 캐시 schema는 그대로다.
    "0.7.3": {"0.7.0", "0.7.1", "0.7.2", "0.7.3"},
    # v0.7.4는 화면 전달 방식만 바꾸며 v0.7.x 캐시를 그대로 읽는다.
    "0.7.4": {"0.7.0", "0.7.1", "0.7.2", "0.7.3", "0.7.4"},
    # v0.8.0은 금리 탭·수치 카드·날짜 선택 비교를 추가하지만 캐시 schema는 그대로다.
    "0.8.0": {"0.7.0", "0.7.1", "0.7.2", "0.7.3", "0.7.4", "0.8.0"},
    # v0.8.1은 표현·상세 배치·디자인만 바꾸며 화면용 캐시 schema는 그대로다.
    "0.8.1": {"0.7.0", "0.7.1", "0.7.2", "0.7.3", "0.7.4", "0.8.0", "0.8.1"},
    # v0.8.2와 v0.8.3은 UI·문구·릴리스 일관성 패치이며 화면용 캐시 schema는 그대로다.
    "0.8.2": {"0.7.0", "0.7.1", "0.7.2", "0.7.3", "0.7.4", "0.8.0", "0.8.1", "0.8.2"},
    "0.8.3": {"0.7.0", "0.7.1", "0.7.2", "0.7.3", "0.7.4", "0.8.0", "0.8.1", "0.8.2", "0.8.3"},
    # v0.8.4는 전문 탭의 관계 맥락과 시각 문법만 복원하며 캐시 schema는 그대로다.
    "0.8.4": {"0.7.0", "0.7.1", "0.7.2", "0.7.3", "0.7.4", "0.8.0", "0.8.1", "0.8.2", "0.8.3", "0.8.4"},
}


def _is_compatible_data_code_version(data_version: str, ui_version: str = __version__) -> bool:
    """UI-only 패치가 직전 데이터 산출물과 호환되는지 확인한다."""
    if data_version == ui_version:
        return True
    return data_version in _UI_DATA_COMPATIBLE_VERSIONS.get(ui_version, set())

GUIDE_INTRO = r"""
## RiskRadar를 읽는 순서

RiskRadar는 미국 시장을 **주식시장 변동성·기업 신용·경기 흐름·금리 움직임**으로 나눠 봅니다. 하나의 점수로 시장을 단정하지 않고, 현재값·상태·최근 추세를 따로 보여줍니다.

1. **현황**에서 현재 상태와 최근 흐름을 빠르게 봅니다.
2. **신용**에서 HY·BBB·A·CP의 현재값·상태·1개월 변화와 최근 90일 기록을 봅니다.
3. **금리**에서 금리 현황, 단기·장기 금리 관계, 30Y 금리 변화 나눠보기, 장기금리 참고 지표를 봅니다.
4. **흐름**에서 지난 30일 과정과 선택 지표의 원자료 흐름을 봅니다.
5. **비교**에서 최신 지표를 비교하거나 기준일을 직접 골라 같은 날짜의 핵심 6개를 봅니다.
6. **설명**에서 지표별 읽는 법과 관계를 자세히 봅니다.

### 화면의 `상태`와 `최근 추세`

- **상태**: RiskRadar의 지표별 경계 기준에 현재 걸렸는지 보여줍니다.
- **최근 추세**: 실제 약 1개월 동안 어느 방향으로 얼마나 움직였는지 보여줍니다.

따라서 `급격한 상승 없음`이면서도 최근 1개월에는 소폭 상승할 수 있습니다. 둘은 모순이 아닙니다.

### `최근 3년·5년·10년 중 현재 위치` 읽는 법

`상위 18% 구간`은 **위험확률 18%가 아닙니다.** 과거 관측값을 낮은 값부터 높은 값까지 줄 세웠을 때 현재 값이 높은 쪽 18% 안에 있다는 뜻입니다.

`하위 13% 구간`은 현재 값이 낮은 쪽 13% 안에 있다는 뜻입니다.

| 화면 표현 | 실제 계산 | 쉬운 뜻 |
|---|---|---|
| **1개월 변화** | 20개 관측치 전 대비 | 대략 한 달 전보다 얼마나 변했는지 |
| **3개월 변화** | 60개 관측치 전 대비 | 대략 세 달 전보다 얼마나 변했는지 |
| **최근 3년 중 현재 위치** | 최근 공식 자료 3년 안의 상대 위치 | ICE 회사채 계열은 이 범위만 장기 위치처럼 과장하지 않고 표시 |
| **최근 5년 중 현재 위치** | 실제 5년 자료가 충분할 때만 계산 | `상위 18% 구간`, `하위 13% 구간`, `중간 구간` |
| **최근 10년 중 현재 위치** | 실제 10년 자료가 충분할 때만 계산 | 장기적으로 지금 값이 높은 쪽인지 낮은 쪽인지 |

ICE BofA 회사채 계열은 현재 FRED가 제공하는 최근 약 3년 자료만 사용합니다. 따라서 `최근 3년 위치`를 장기 역사나 과거 위기 수준으로 부르지 않습니다.
"""
BOARD_HELP = r"""
### 현재 상황 읽는 법

먼저 **신용등급 낮은 기업의 추가 금리**와 **주식시장 예상 변동성(VIX)**을 봅니다. 주식시장 변동성만 커지는지, 기업들이 회사채를 발행할 때 더 높은 금리를 요구받는지도 같이 확인합니다.

그다음 **30년 미국 국채금리 변화 나눠보기**에서 전체 금리 변화가 `물가 영향을 뺀 30년 금리`와 `일반 국채와 물가연동국채의 금리 차이`로 어떻게 나뉘는지 봅니다. **2년 금리**는 같은 약 1개월 동안 장·단기 금리가 어떻게 움직였는지 확인합니다. **10년 국채를 오래 보유할 때 요구되는 추가 보상과 다른 10년 지표**는 참고 자료로 봅니다. 마지막으로 **10년 금리와 3개월 금리의 관계**는 현재 시장 불안과 따로 떼어 경기 흐름의 배경으로 봅니다.

- `상위 18% 구간`은 위험확률이 아니라 과거 값 중 높은 쪽 18% 안에 있다는 뜻입니다.
- `하위 13% 구간`은 과거 값 중 낮은 쪽 13% 안에 있다는 뜻입니다.
- `지금 뜻`은 현재 지표 하나를 읽는 문장입니다. 전체 시장 결론이 아닙니다.
"""

EASY_GLOSSARY = r"""
### 먼저 이것만 알아두면 됩니다

| 화면 이름 | 쉽게 말하면 | 숫자가 오르면 |
|---|---|---|
| **신용등급 낮은 기업의 추가 금리** | 신용등급이 낮은 기업이 국채보다 더 얹어줘야 하는 금리 | 시장이 신용등급 낮은 기업에 더 높은 금리를 요구함 |
| **투자등급 경계 기업의 추가 금리** | 투자등급 중 가장 낮은 쪽 기업이 더 얹어줘야 하는 금리 | 오르면 BBB 회사채 금리와 BBB 기업의 조달비용이 높아짐 |
| **A등급 기업의 추가 금리** | 투자등급 경계를 넘어 A등급 기업도 더 얹어줘야 하는 금리 | A등급 회사채 금리와 우량 기업의 조달비용도 올라가는지 확인 |
| **기업 신용도에 따른 단기자금 금리 차이** | 신용도가 낮은 기업과 높은 기업의 30일 자금조달 금리 차이 | 신용도가 낮은 기업의 단기 조달금리가 우량 기업보다 더 높아짐 |
| **10년 일반·물가연동 국채금리 차이** | 10년 일반 국채와 물가연동 국채의 금리 차이 | 시장의 물가 기대·물가 위험·채권 수요와 공급 등이 섞인 금리 차이가 커지는 방향 |
| **10년 장기채 추가 보상** | 장기채를 오래 보유하기 위해 시장이 요구하는 추가 보상의 모형 추정치 | 오르면 10년·30년 장기금리를 끌어올리는 요인 |
| **미국 금융시장 전반의 자금 사정** | 여러 시장과 금융기관을 한꺼번에 본 외부 참고 지표 | 전반적으로 돈을 빌리고 위험을 감수하기가 더 어려워지는 방향 |
| **미국 금융시장 전반의 불안** | 여러 금융시장이 함께 불안해지는지 본 외부 참고 지표 | 시장 전반의 불안이 높아지는 방향 |
| **물가 영향을 뺀 10년 금리** | 물가연동 10년 국채에서 계산한 실질금리 | 10년·30년 장기금리를 끌어올리고 장기 자산의 할인율을 높이는 요인 |

`추가 금리`는 기업이 실제로 내는 대출금리 자체가 아닙니다. **같은 기간의 미국 국채보다 회사채가 얼마나 더 높은 금리를 요구받는지**를 뜻합니다.
"""

HISTORY_HELP = r"""
### 지난 30일 흐름 읽는 법

최신 캐시에 이미 들어 있는 **과거 FRED 시계열**로 지난 30일을 즉석에서 다시 구성합니다. 그래서 앱을 오늘 처음 설치했거나 매일 스냅샷을 저장하지 않았어도, 핵심 6개 지표의 한 달 흐름을 바로 볼 수 있습니다. 기업 신용 변화는 최신 캐시에 저장된 HY·BBB·A·CP 경로를 별도로 읽습니다.

**한 달 사이 무엇이 달라졌는지, 한때 크게 움직였다가 되돌아온 것은 무엇인지, 현재 남아 있는 추세는 무엇인지**를 함께 봅니다. 시작값과 현재값만 비교하지 않습니다.

> 날짜는 RiskRadar 저장일이 아니라 **실제 지표 관측일**입니다. 또한 당시 화면을 그대로 보존한 기록이 아니라, **현재 코드 규칙으로 과거 관측일을 다시 읽은 결과**이므로 과거 버전의 판정과는 다를 수 있습니다.
"""

SYNCED_HELP = r"""
### 같은 날짜로 비교

각 지표의 최신 관측일은 다를 수 있습니다. 핵심 6개에 실제 관측값이 모두 있는 날짜를 직접 골라 같은 날짜 기준으로 비교합니다.
"""

SIGNAL_MATRIX_HELP = r"""
### 전체 지표 비교 읽는 법

핵심 6개 지표의 최신값·변화·과거 위치·표시 이유를 한 번에 보는 표입니다. 내부 코드명 대신 사용자용 표현만 보여줍니다.
"""

CHART_HELP = r"""
### 차트 읽는 법

최신값 하나보다 흐름이 중요할 때가 많습니다. 최근 움직임이 급한지 완만한지, 이전 국면과 비교해 지속되는지 확인하세요.
"""


def _days_since(date_str: str) -> int:
    d = pd.to_datetime(date_str).date()
    return (datetime.now(KST).date() - d).days


def _one_line_interpretation(row: pd.Series) -> str:
    key = row["key"]
    code = str(row.get("state_code", ""))
    drop = bool(row.get("drop_flag", False))

    if key == "VIX":
        if code == "calm":
            return "주식시장 예상 변동성은 현재 경계 기준에 걸리지 않았습니다. 회사채 지표가 따로 움직이는지도 같이 봅니다."
        if code == "watch":
            return "주식시장 예상 변동성이 커졌습니다. 며칠 이어지는지와 회사채 시장도 같이 움직이는지 봅니다."
        return "주식시장이 큰 변동성을 가격에 반영하고 있습니다. 하루 급등인지, 회사채 시장까지 함께 움직이는지가 중요합니다."

    if key == "HYOAS":
        if code in ("calm", "neutral"):
            return "신용등급 낮은 기업이 돈을 빌릴 때 요구받는 추가 금리는 아직 크게 벌어지지 않았습니다."
        if code == "watch":
            return "HY 회사채 금리가 높은 수준입니다. BBB와 A등급 회사채 금리도 함께 오르는지 봅니다."
        return "HY 회사채 금리가 매우 높은 수준입니다. BBB·A등급 회사채와 단기 기업자금시장도 함께 움직이는지 봅니다."

    if key == "T10Y3M":
        return f"현재 10년 금리와 3개월 금리의 관계는 '{state_name(code, row.get('state_label'), key=key)}'입니다. 지금의 시장 불안과는 따로 떼어 경기 흐름의 배경으로 봅니다."

    if drop:
        return "금리가 빠르게 내려갔습니다. 좋은 금리인하 기대인지, 경기둔화 우려인지 다른 지표와 함께 봅니다."
    if code == "stable":
        return "최근 금리는 급격한 상승 경계 기준에 걸리지 않았습니다."
    if code == "rise_watch":
        return "최근 금리가 상승 경계 기준에 걸렸습니다. 다른 만기 금리와 물가 관련 움직임을 같이 봅니다."
    return "최근 금리가 빠르게 올랐습니다. 다른 금리와 참고 지표를 함께 봅니다."


def _board_df(matrix: pd.DataFrame) -> pd.DataFrame:
    """현재 상황 탭의 첫 화면용 압축 표.

    해석 문장과 판정 근거는 아래 상세 아코디언에서 보여주고, 첫 화면에는
    사용자가 지금 상태를 빠르게 훑는 데 필요한 값만 남긴다.
    """
    rows = []
    for _, r in matrix.iterrows():
        rows.append({
            "지표": core_name(str(r["key"])),
            "상태": state_name(str(r.get("state_code", "")), str(r.get("state_label", "")), drop=bool(r.get("drop_flag", False)), key=str(r.get("key", ""))),
            "최신값": fmt_value(r["latest_value"], r["value_unit"]),
            LABEL_1M: fmt_change(r["change_20obs"], r["change_unit"]),
            LABEL_3M: fmt_change(r["change_60obs"], r["change_unit"]),
            LABEL_3Y: fmt_pct(r.get("percentile_3y")),
            LABEL_5Y: fmt_pct(r.get("percentile_5y")),
            LABEL_10Y: fmt_pct(r.get("percentile_10y")),
            "관측일": r["latest_observed_date"],
        })
    return pd.DataFrame(rows)


def _synced_df(arts: dict) -> pd.DataFrame:
    s = arts["synced_snapshot"]
    if s.empty:
        return pd.DataFrame([{"안내": "모든 지표가 함께 존재하는 공통 기준일이 아직 없습니다."}])
    rows = []
    for _, r in s.iterrows():
        key = str(r["key"])
        series = C.SERIES[key]
        rows.append({
            "공통 기준일": r["synced_date"],
            "지표": core_name(key),
            "값": fmt_value(r["value"], series.value_unit),
            LABEL_1M: fmt_change(r["change_20obs"], series.change_unit),
            LABEL_3M: fmt_change(r["change_60obs"], series.change_unit),
            "상태": state_name(str(r.get("state_code", "")), str(r.get("state_label", "")), drop=bool(r.get("drop_flag", False)), key=str(r.get("key", ""))),
        })
    return pd.DataFrame(rows)


def _history_table(history: pd.DataFrame, key: str) -> pd.DataFrame:
    if history.empty:
        return pd.DataFrame([{"안내": "지난 30일을 다시 구성할 과거 시계열이 없습니다."}])
    d = history.loc[history["key"] == key].copy()
    if d.empty:
        return pd.DataFrame([{"안내": f"{core_name(key)}의 지난 30일 기록이 없습니다."}])
    d = d.sort_values("snapshot_at_kst")
    reconstructed = "history_source" in d.columns and d["history_source"].astype(str).eq("reconstructed").any()
    if "state_code" in d.columns:
        d["상태"] = [state_name(str(c), str(l), drop=bool(drop), key=key) for c, l, drop in zip(d["state_code"], d["state_label"], d["drop_flag"])]
    else:
        d["상태"] = d["state_label"]
    d["최신값"] = [fmt_value(v, u) for v, u in zip(d["latest_value"], d["value_unit"])]
    d[LABEL_1M] = [fmt_change(v, u) for v, u in zip(d["change_20obs"], d["change_unit"])]
    d[LABEL_3M] = [fmt_change(v, u) for v, u in zip(d["change_60obs"], d["change_unit"])]
    if "percentile_3y" not in d.columns:
        d["percentile_3y"] = None
    if "percentile_5y" not in d.columns:
        d["percentile_5y"] = None
    if "percentile_10y" not in d.columns:
        d["percentile_10y"] = None
    d[LABEL_3Y] = [fmt_pct(v) for v in d["percentile_3y"]]
    d[LABEL_5Y] = [fmt_pct(v) for v in d["percentile_5y"]]
    d[LABEL_10Y] = [fmt_pct(v) for v in d["percentile_10y"]]
    d["빠르게 내림"] = ["⚠︎" if x else "" for x in d["drop_flag"]]
    d["지표"] = core_name(key)
    d["state_reason"] = d["state_reason"].astype(str).map(plain_language)
    if reconstructed:
        return d[[
            "snapshot_date", "지표", "상태", "최신값", LABEL_1M, LABEL_3M,
            LABEL_3Y, LABEL_5Y, LABEL_10Y, "빠르게 내림", "state_reason",
        ]].rename(columns={
            "snapshot_date": "관측일",
            "state_reason": "왜 이렇게 표시됐나",
        })
    return d[[
        "snapshot_date", "snapshot_at_kst", "지표", "상태",
        "최신값", "latest_observed_date", LABEL_1M, LABEL_3M, LABEL_3Y, LABEL_5Y, LABEL_10Y,
        "빠르게 내림", "state_reason",
    ]].rename(columns={
        "snapshot_date": "저장일",
        "snapshot_at_kst": "저장시각(KST)",
        "latest_observed_date": "관측일",
        "state_reason": "왜 이렇게 표시됐나",
    })


def _signal_matrix_df(matrix: pd.DataFrame) -> pd.DataFrame:
    """최신 지표 비교용 모바일 3열 표."""
    rows = []
    for _, r in matrix.iterrows():
        state = state_name(str(r.get("state_code", "")), str(r.get("state_label", "")), drop=bool(r.get("drop_flag", False)), key=str(r.get("key", "")))
        change_1m = fmt_change(r["change_20obs"], r["change_unit"])
        change_3m = fmt_change(r["change_60obs"], r["change_unit"])
        rows.append({
            "지표": core_name(str(r["key"])),
            "현재": f"{fmt_value(r['latest_value'], r['value_unit'])} · {state}",
            "최근 변화": f"1개월 {change_1m} · 3개월 {change_3m}",
        })
    return pd.DataFrame(rows)


def _signal_matrix_detail_df(matrix: pd.DataFrame) -> pd.DataFrame:
    """최신 지표 비교의 과거 위치·관측일 상세 3열 표."""
    rows = []
    for _, r in matrix.iterrows():
        positions = []
        if pd.notna(r.get("percentile_3y")):
            positions.append(f"3년 {fmt_pct(r.get('percentile_3y'))}")
        if pd.notna(r.get("percentile_5y")):
            positions.append(f"5년 {fmt_pct(r.get('percentile_5y'))}")
        if pd.notna(r.get("percentile_10y")):
            positions.append(f"10년 {fmt_pct(r.get('percentile_10y'))}")
        rows.append({
            "지표": core_name(str(r["key"])),
            "과거 위치": " · ".join(positions) if positions else "비교 불가",
            "관측일": str(r.get("latest_observed_date", "-")),
        })
    return pd.DataFrame(rows)


def _common_date_choices(chart_data: pd.DataFrame, *, max_dates: int | None = None) -> list[str]:
    """핵심 6개에 실제 관측값이 모두 존재하는 날짜 목록."""
    if chart_data is None or chart_data.empty or not {"date", "key"}.issubset(chart_data.columns):
        return []
    d = chart_data.loc[chart_data["key"].astype(str).isin(C.SERIES_ORDER), ["date", "key"]].copy()
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    d = d.loc[d["date"].notna()].drop_duplicates(["date", "key"])
    counts = d.groupby("date")["key"].nunique()
    dates = counts.loc[counts >= len(C.SERIES_ORDER)].index.sort_values(ascending=False)
    if max_dates is not None:
        dates = dates[:max_dates]
    return [pd.Timestamp(x).date().isoformat() for x in dates]


def _date_cards_html(chart_data: pd.DataFrame, selected_date: str | None) -> str:
    """선택한 공통 관측일의 핵심 6개를 2×3 카드로 보여준다."""
    if not selected_date:
        return '<div class="rr-empty">선택할 수 있는 공통 관측일이 없습니다.</div>'
    if chart_data is None or chart_data.empty:
        return '<div class="rr-empty">날짜별 지표 데이터를 읽을 수 없습니다.</div>'
    d = chart_data.copy()
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    target = pd.Timestamp(selected_date)
    d = d.loc[(d["date"] == target) & d["key"].astype(str).isin(C.SERIES_ORDER)].copy()
    if d.empty:
        return '<div class="rr-empty">선택한 날짜의 공통 지표가 없습니다.</div>'
    rows = []
    for key in C.SERIES_ORDER:
        hit = d.loc[d["key"].astype(str) == key]
        if hit.empty:
            continue
        r = hit.iloc[-1]
        spec = C.SERIES[key]
        rows.append({
            "key": key,
            "latest_value": r.get("value"),
            "value_unit": spec.value_unit,
            "change_20obs": r.get("change_20obs"),
            "change_unit": spec.change_unit,
            "state_code": r.get("state_code", ""),
            "state_label": r.get("state_label", ""),
            "drop_flag": bool(r.get("drop_flag", False)),
        })
    return render_core_cards_html(pd.DataFrame(rows), pd.DataFrame(), changes_only=False)


def _history_plot_data(history: pd.DataFrame, key: str) -> pd.DataFrame:
    if history.empty:
        return pd.DataFrame(columns=["날짜", "최신값"])
    d = history.loc[history["key"] == key, ["snapshot_date", "latest_value"]].copy()
    if d.empty:
        return pd.DataFrame(columns=["날짜", "최신값"])
    d["날짜"] = pd.to_datetime(d["snapshot_date"])
    d["최신값"] = d["latest_value"]
    return d[["날짜", "최신값"]].sort_values("날짜")


def _chart_data(arts: dict, key: str) -> pd.DataFrame:
    c = arts.get("chart_data", pd.DataFrame())
    if c is None or c.empty or "key" not in c.columns:
        return pd.DataFrame(columns=["날짜", "값"])
    d = c[c["key"] == key][["date", "value"]].copy()
    d["날짜"] = pd.to_datetime(d["date"], errors="coerce")
    d["값"] = pd.to_numeric(d["value"], errors="coerce")
    return d[["날짜", "값"]].dropna().sort_values("날짜")


def _chart(arts: dict, key: str):
    return gr.LinePlot(
        value=_chart_data(arts, key), x="날짜", y="값",
        title=f"{core_name(key)} 원자료 흐름",
    )



def _frames_from_chart_data(chart_data: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """기존 캐시의 chart_data를 3축/조합 엔진 입력 프레임으로 복원한다."""
    if chart_data is None or chart_data.empty or "key" not in chart_data.columns:
        return {}
    frames: dict[str, pd.DataFrame] = {}
    for key, group in chart_data.groupby("key", sort=False):
        frame = group.copy()
        if "date" in frame.columns:
            frame["date"] = pd.to_datetime(frame["date"])
            frame = frame.sort_values("date")
        frames[str(key)] = frame.reset_index(drop=True)
    return frames


def _readings_need_branch_upgrade(readings: list[dict] | None) -> bool:
    """v0.4.4 이전 캐시의 checks에는 결과별 branches가 없다."""
    if not readings:
        return True
    for reading in readings:
        for check in reading.get("checks") or []:
            if not check.get("branches"):
                return True
    return False


def _today_context_with_fallback(data_quality: dict | None, arts: dict,
                                 aux_df: pd.DataFrame) -> dict:
    """옛 캐시에도 오늘의 해석을 표시한다.

    v0.4 이전/초기 v0.4 캐시에는 data_quality.json의 axes/readings가 없을 수 있다.
    이 경우 UI가 이미 읽은 chart_data와 aux_signal_matrix로 같은 규칙 엔진을
    즉석 실행한다. refresh는 하지 않으며 원격 데이터도 새로 가져오지 않는다.
    """
    dq = dict(data_quality or {})
    need_axes = not dq.get("axes")
    need_readings = _readings_need_branch_upgrade(dq.get("readings"))
    if not (need_axes or need_readings):
        return dq

    frames = _frames_from_chart_data(arts.get("chart_data", pd.DataFrame()))
    if not frames:
        return dq

    if need_axes:
        try:
            dq["axes"] = axis_engine.composite_view(frames).to_dict()
        except Exception:
            pass

    if need_readings:
        try:
            aux = {}
            aux_status = {}
            if aux_df is not None and not aux_df.empty:
                for _, row in aux_df.iterrows():
                    key = str(row.get("key", ""))
                    if not key:
                        continue
                    aux[key] = SimpleNamespace(direction=str(row.get("direction", "확인 불가")))
                    aux_status[key] = str(row.get("staleness_label", "unknown"))
            dq["readings"] = [
                reading.to_dict()
                for reading in interpretation_engine.read_all(
                    frames, aux, aux_status=aux_status
                )
            ]
        except Exception:
            pass
    return dq

def _aux_status_df(aux_df: pd.DataFrame) -> pd.DataFrame:
    """함께 볼 지표 수집 상태를 사용자용 진단 표로 보여준다."""
    cols = ["역할", "지표", "FRED 시리즈", "수집 상태", "사용 중인 관측일", "자료 범위", "최신성", "오류 내용"]
    if aux_df is None or aux_df.empty:
        return pd.DataFrame(columns=cols)
    rows = []
    status_map = {
        "ok": "정상 수집",
        "carried_forward": "과거 마지막 성공값 사용",
        "failed": "수집 실패",
    }
    fresh_map = {
        "normal": "최신",
        "delayed": "업데이트 지연",
        "stale": "오래된 자료 · 현재 해석에서 제외",
    }
    for _, r in aux_df.iterrows():
        key = str(r.get("key", ""))
        layer = str(r.get("layer", "confirmation"))
        role = {"confirmation": "확인 지표", "external": "외부 참고", "legacy": "운영 진단용"}.get(layer, layer)
        history_range = "-"
        if pd.notna(r.get("history_start")) or pd.notna(r.get("history_end")):
            history_range = f"{r.get('history_start') or '?'} ~ {r.get('history_end') or '?'}"
        rows.append({
            "역할": role,
            "지표": aux_name(key),
            "FRED 시리즈": str(r.get("series_id", "-")),
            "수집 상태": status_map.get(str(r.get("fetch_status", "failed")), str(r.get("fetch_status", "확인 불가"))),
            "사용 중인 관측일": str(r.get("latest_date", "-")) if pd.notna(r.get("latest_date")) else "-",
            "자료 범위": history_range,
            "최신성": fresh_map.get(str(r.get("staleness_label", "unknown")), "확인 불가"),
            "오류 내용": plain_language(str(r.get("error", ""))) if str(r.get("error", "")) not in {"", "nan", "None"} else "-",
        })
    return pd.DataFrame(rows, columns=cols)




def _decision_tracking_markdown(snapshot: DashboardSnapshot) -> str:
    snap = snapshot.decision_snapshot or {}
    diff = snapshot.decision_diff or {}
    if not snap:
        return (
            "**권위 있는 판정 기록:** 아직 없음\n\n"
            "v0.6.2 첫 성공 배치부터 새로 시작합니다. 이전 캐시는 현재 규칙으로 백필하지 않습니다."
        )

    schemas = snap.get("schemas") or {}
    summary = diff.get("summary") or {}
    status_map = {
        "cold_start": "직전 비교 대상 없음 (정상적인 최초 기록)",
        "ok": "비교 가능",
        "schema_boundary": "판정 기준 경계 — 해당 영역 비교 보류",
        "partial_schema_boundary": "일부 영역만 비교 가능",
    }
    lines = [
        f"- **판정 스냅샷 포맷:** `v{snap.get('snapshot_format_version', '확인 불가')}`",
        f"- **핵심 상태 규칙:** `{schemas.get('core_state', '확인 불가')}`",
        f"- **신용 범위·지속 규칙:** `{schemas.get('credit_episode', '확인 불가')}`",
        f"- **함께 볼 지표 방향 규칙:** `{schemas.get('aux_direction', '확인 불가')}`",
        f"- **직전 비교 대상:** `{diff.get('previous_cache_version') or '없음'}`",
        f"- **비교 상태:** `{status_map.get(str(diff.get('status')), str(diff.get('status') or '확인 불가'))}`",
        f"- **탐지 결과:** 시장 변화 `{summary.get('market', 0)}` · 데이터 상태 변화 `{summary.get('data_quality', 0)}` · 복구 공백 경계 `{summary.get('recovery_gap', 0)}` · 판정 기준 경계 `{summary.get('schema_boundary', 0)}`",
    ]

    events = (diff.get("market_transitions") or []) + (diff.get("recovery_gap_events") or [])
    if events:
        lines += ["", "**이번 비교에서 기록된 주요 사건**"]
        for event in events[:8]:
            lines.append(f"- {plain_language(str(event.get('message', '')))}")
    elif diff.get("status") == "cold_start":
        lines += ["", "첫 권위 있는 스냅샷이므로 이번 배치는 변화 비교를 하지 않습니다."]
    else:
        lines += ["", "시장 판정 변화는 기록되지 않았습니다."]
    return "\n".join(lines)

def _data_generation_info(status: dict | None, data_quality: dict | None) -> dict[str, str]:
    """활성 데이터가 언제·어떤 코드로 만들어졌는지 사용자용으로 정리한다."""
    status = status or {}
    data_quality = data_quality or {}
    active = str(status.get("active_cache_version") or "확인 불가")
    code = status.get("code_version") or data_quality.get("code_version")
    code_text = str(code) if code else "기록되지 않음 (구버전 데이터)"
    generated = status.get("last_refresh_finished_at") or status.get("last_success_at")
    if not generated and active not in {"", "확인 불가", "None"}:
        try:
            generated = datetime.strptime(active, "%Y-%m-%dT%H-%M-%SKST").strftime("%Y-%m-%d %H:%M KST")
        except ValueError:
            generated = None
    return {
        "active_cache_version": active,
        "generated_at": str(generated or "확인 불가"),
        "code_version": code_text,
        "code_version_missing": "yes" if not code else "no",
    }


def _data_status_summary(snapshot: DashboardSnapshot, store) -> tuple[str, str]:
    generation = _data_generation_info(snapshot.status, snapshot.data_quality)
    dataset_name = str(getattr(store, "repo_id", "로컬 저장소"))
    ice = (snapshot.data_quality or {}).get("ice_history_policy") or {}
    company_window = ice.get("company_bond_window", "확인 불가")
    long_claims = "사용하지 않음" if ice.get("long_history_claims") is False else "확인 필요"
    summary = (
        f"- **현재 화면 코드 버전:** `{__version__}`\n"
        f"- **활성 데이터 버전:** `{generation['active_cache_version']}`\n"
        f"- **마지막 데이터 생성 시각:** `{generation['generated_at']}`\n"
        f"- **데이터 생성 코드 버전:** `{generation['code_version']}`\n"
        f"- **읽고 있는 데이터 저장소:** `{dataset_name}`\n"
        f"- **이 화면이 Dataset을 다시 읽은 시각:** `{snapshot.loaded_at_kst}`\n"
        f"- **ICE 회사채 비교 범위:** `{company_window}`\n"
        f"- **ICE 회사채 5년·10년 장기 위치 주장:** `{long_claims}`\n"
        f"- **신용 노드 기록 행:** `{len(snapshot.credit_node_history)}` · **변화 흐름 기록:** `{len(snapshot.credit_episodes)}`"
    )

    warnings: list[str] = []
    if snapshot.load_errors:
        warnings.append(
            "⚠️ **일부 부속 데이터를 읽는 과정에서 오류가 있었습니다.**  "
            + "  \n".join(f"- `{e}`" for e in snapshot.load_errors)
        )
    data_quality_failed = any(e.startswith("data_quality.json 읽기 실패") for e in snapshot.load_errors)
    if generation["code_version_missing"] == "yes" and not data_quality_failed:
        warnings.append(
            "⚠️ **활성 데이터는 존재하지만 생성 코드 버전이 기록돼 있지 않습니다.** "
            "구버전 캐시일 수 있습니다. 최신 배치를 실행한 직후에도 이 문구가 남는다면, "
            "아래의 `이 화면이 Dataset을 다시 읽은 시각`과 활성 데이터 버전이 실제로 데이터 업데이트됐는지 먼저 확인하세요."
        )
    elif (
        generation["code_version_missing"] == "no"
        and not _is_compatible_data_code_version(str(generation["code_version"]))
    ):
        warnings.append(
            "⚠️ 화면 코드와 마지막 배치 코드 버전이 다릅니다. "
            "GitHub 배치가 최신 코드를 실행하는지 확인하세요."
        )
    return summary, "\n\n".join(warnings)


def _loaded_banner(snapshot: DashboardSnapshot) -> str:
    active = snapshot.status.get("active_cache_version", "확인 불가")
    return (
        f"**현재 화면이 읽고 있는 데이터:** `{active}`  ·  "
        f"**Dataset 재조회 시각:** `{snapshot.loaded_at_kst}`\n\n"
        "아래 버튼은 FRED 수집을 실행하지 않고, **HF Dataset의 최신 활성 캐시를 다시 읽습니다.**"
    )


def _dynamic_payload(snapshot: DashboardSnapshot, selected_key: str, store) -> dict:
    arts = snapshot.arts
    aux_df = snapshot.aux_df
    frames = _frames_from_chart_data(arts.get("chart_data", pd.DataFrame()))
    # 저장된 원본 metadata와 UI fallback 결과를 분리한다.
    effective_dq = _today_context_with_fallback(snapshot.data_quality, arts, aux_df)
    today_summary_md = render_today_summary_markdown(effective_dq, aux_df)
    today_md = render_today_markdown(effective_dq, aux_df)
    credit_md = render_credit_episode_markdown(effective_dq)
    credit_timeline = build_credit_timeline(snapshot.credit_node_history, snapshot.credit_episodes)
    credit_timeline_md = render_credit_timeline_markdown(credit_timeline)
    credit_timeline_html = render_credit_timeline_html(credit_timeline)
    past_credit_episodes_md = render_past_credit_episodes_markdown(credit_timeline)
    past_credit_episodes_compact_md = render_past_credit_episodes_compact_markdown(credit_timeline)
    monthly_md = render_monthly_markdown(
        snapshot.history, aux_df, snapshot.credit_node_history,
        (effective_dq.get("credit_episode") or {}),
    )
    details = {
        key: plain_language(render_indicator_detail(
            arts["signal_matrix"].loc[arts["signal_matrix"]["key"].astype(str) == key].iloc[-1],
            effective_dq,
            _one_line_interpretation(
                arts["signal_matrix"].loc[arts["signal_matrix"]["key"].astype(str) == key].iloc[-1]
            ),
            frames=frames,
            aux_df=aux_df,
            matrix=arts["signal_matrix"],
        ))
        for key in C.SERIES_ORDER
        if not arts["signal_matrix"].loc[arts["signal_matrix"]["key"].astype(str) == key].empty
    }
    aux_details = {
        key: plain_language(render_aux_detail(
            aux_df.loc[aux_df["key"].astype(str) == key].iloc[-1],
            aux_df=aux_df,
            matrix=arts["signal_matrix"],
        ))
        for key in AC.VISIBLE_AUX_ORDER
        if aux_df is not None and not aux_df.empty
        and not aux_df.loc[aux_df["key"].astype(str) == key].empty
    }
    summary_md, warning_md = _data_status_summary(snapshot, store)
    history_source_md = f"**현재 30일 데이터 기준:** {snapshot.history_source}"
    if snapshot.history_error:
        history_source_md += f"\n\n⚠️ {snapshot.history_error}"
    core_cards_all = render_core_cards_html(
        arts["signal_matrix"], arts.get("chart_data", pd.DataFrame()), changes_only=False
    )
    common_dates = _common_date_choices(arts.get("chart_data", pd.DataFrame()))
    selected_common_date = common_dates[0] if common_dates else None
    return {
        "banner": _loaded_banner(snapshot),
        "data_health": render_data_health_badge(snapshot.status, snapshot.data_quality, snapshot.decision_diff, snapshot.load_errors),
        "data_basis": render_data_basis_html(snapshot.status, arts["signal_matrix"], aux_df, snapshot.load_errors),
        "status_cards": render_status_cards_html(effective_dq, arts["signal_matrix"], aux_df, snapshot.rate_composition),
        "market_interpretation": render_market_interpretation_html(effective_dq, arts["signal_matrix"], aux_df, snapshot.rate_composition),
        "key_indicator_cards": render_key_indicator_cards_html(effective_dq, arts["signal_matrix"], aux_df),
        "status_changes_html": render_status_changes_html(snapshot.decision_diff),
        "decision_basis": render_decision_basis_markdown(snapshot.decision_snapshot, effective_dq),
        "today_one_line": render_today_one_line_markdown(effective_dq),
        "domain_strip": render_domain_strip_html(effective_dq, arts["signal_matrix"]),
        "recent_changes": render_recent_changes_markdown(snapshot.decision_diff),
        "recent_changes_html": render_recent_changes_html(snapshot.decision_diff),
        "rate_composition": RC.render_markdown(snapshot.rate_composition),
        "rate_scan_html": RC.render_scan_html(snapshot.rate_composition),
        "rate_overview_html": RV.render_rate_overview_cards_html(arts["signal_matrix"]),
        "rate_curve_html": RV.render_rate_curve_html(snapshot.rate_composition),
        "rate_reference_html": RV.render_rate_reference_cards_html(arts["signal_matrix"], aux_df),
        "rate_change_table_html": RV.render_rate_change_table_html(snapshot.rate_composition),
        "rate_notes_html": RV.render_rate_notes_html(snapshot.rate_composition),
        "remaining_changes": render_remaining_changes_markdown(snapshot.decision_snapshot, effective_dq),
        "remaining_changes_html": render_remaining_changes_html(
            snapshot.decision_snapshot, effective_dq, arts["signal_matrix"], aux_df
        ),
        "next_checks": render_next_checks_markdown(effective_dq, snapshot.decision_snapshot),
        "next_checks_html": render_next_checks_html(effective_dq, snapshot.decision_snapshot),
        "evidence_balance": render_evidence_balance_markdown(effective_dq, aux_df),
        "core_cards_all": core_cards_all,
        "credit_map": render_credit_range_map_html(effective_dq, arts["signal_matrix"], aux_df),
        "credit_context_html": render_credit_context_html(effective_dq, arts["signal_matrix"], aux_df),
        "rate_context_html": render_rate_context_html(arts["signal_matrix"], aux_df, snapshot.rate_composition),
        "board": _board_df(arts["signal_matrix"]),
        "details": details,
        "aux_details": aux_details,
        "today_summary": today_summary_md,
        "today": today_md,
        "credit": credit_md,
        "credit_timeline": credit_timeline_md,
        "credit_timeline_html": credit_timeline_html,
        "past_credit_episodes": past_credit_episodes_md,
        "past_credit_episodes_compact": past_credit_episodes_compact_md,
        "history_source": history_source_md,
        "monthly": monthly_md,
        "history": snapshot.history,
        "history_plot": _history_plot_data(snapshot.history, selected_key),
        "history_table": _history_table(snapshot.history, selected_key),
        "synced": _synced_df(arts),
        "common_dates": common_dates,
        "selected_common_date": selected_common_date,
        "date_cards_html": _date_cards_html(arts.get("chart_data", pd.DataFrame()), selected_common_date),
        "matrix": _signal_matrix_df(arts["signal_matrix"]),
        "matrix_detail": _signal_matrix_detail_df(arts["signal_matrix"]),
        "charts": {key: _chart_data(arts, key) for key in C.SERIES_ORDER},
        "chart_data": arts.get("chart_data", pd.DataFrame()),
        "status_summary": summary_md,
        "status_warning": warning_md,
        "aux_status": _aux_status_df(aux_df),
        "status_json": snapshot.status,
        "data_quality_json": snapshot.data_quality,
        "decision_tracking": _decision_tracking_markdown(snapshot),
        "decision_snapshot_json": snapshot.decision_snapshot,
        "decision_diff_json": snapshot.decision_diff,
    }


def _static_guide_card(key: str) -> str:
    if key == "HY_BBB":
        return render_static_explainer(key, lens_name("HY_BBB"))
    if key in AC.AUX_SERIES:
        return render_static_explainer(key, aux_name(key))
    return render_static_explainer(key, core_name(key))


def build_app():
    store = cache_store.get_store()
    try:
        snapshot = load_dashboard_snapshot(store)
    except Exception as e:
        with gr.Blocks(title="RiskRadar") as demo:
            gr.Markdown(f"# RiskRadar\n\n저장된 데이터를 아직 읽을 수 없습니다: `{e}`")
        return demo

    default_key = "HYOAS" if "HYOAS" in C.SERIES_ORDER else C.SERIES_ORDER[0]
    choices = [(core_name(k), k) for k in C.SERIES_ORDER]
    guide_choices = (
        choices
        + [(lens_name("HY_BBB"), "HY_BBB")]
        + [(aux_name(k), k) for k in AC.VISIBLE_AUX_ORDER]
    )
    initial = _dynamic_payload(snapshot, default_key, store)

    with gr.Blocks(title="RiskRadar") as demo:
        gr.HTML(
            f'<div class="rr-app-head"><div><h1>RiskRadar</h1>'
            f'<p>현재 상태와 최근 흐름을 빠르게 봅니다.</p></div>'
            f'<strong>v{__version__}</strong></div>'
        )
        data_health_component = gr.Markdown(initial["data_health"])
        reload_button = gr.Button("↻ 최신 데이터 불러오기", variant="secondary")
        with gr.Accordion("관리·진단", open=False):
            with gr.Accordion("불러온 데이터 정보", open=False):
                loaded_banner = gr.Markdown(initial["banner"])
            status_summary_component = gr.Markdown(initial["status_summary"])
            status_warning_component = gr.Markdown(initial["status_warning"])
            with gr.Accordion("판정 기록·변화 진단", open=False):
                decision_tracking_component = gr.Markdown(initial["decision_tracking"])
                with gr.Accordion("판정 스냅샷·diff 원본", open=False):
                    decision_snapshot_json_component = gr.JSON(initial["decision_snapshot_json"])
                    decision_diff_json_component = gr.JSON(initial["decision_diff_json"])
            with gr.Accordion("함께 볼 지표 수집 상태", open=False):
                aux_status_component = gr.Dataframe(initial["aux_status"], wrap=True, interactive=False)
            with gr.Accordion("원본 상태 정보", open=False):
                status_json_component = gr.JSON(initial["status_json"])
                data_quality_json_component = gr.JSON(initial["data_quality_json"])

        with gr.Tab("현황"):
            data_basis_component = gr.HTML(initial["data_basis"])
            status_cards_component = gr.HTML(initial["status_cards"])
            market_interpretation_component = gr.HTML(initial["market_interpretation"])
            key_indicator_cards_component = gr.HTML(initial["key_indicator_cards"])
            status_changes_component = gr.HTML(initial["status_changes_html"])

            with gr.Accordion("판정 근거 자세히 보기", open=False, elem_classes="rr-detail-accordion"):
                decision_basis_component = gr.Markdown(initial["decision_basis"])

        with gr.Tab("신용"):
            gr.Markdown("## 신용 현황")
            gr.HTML('<div class="rr-tab-intro">회사채 OAS는 비슷한 만기의 국채 대비 추가 금리입니다. 현재 수준·최근 변화·어느 등급과 시장까지 같은 방향이 나타나는지를 함께 봅니다.</div>')
            credit_map_component = gr.HTML(initial["credit_map"])
            credit_context_component = gr.HTML(initial["credit_context_html"])
            credit_timeline_component = gr.HTML(initial["credit_timeline_html"])
            with gr.Accordion("지난 신용 변화", open=False, elem_classes="rr-detail-accordion"):
                past_credit_episodes_component = gr.Markdown(initial["past_credit_episodes_compact"])
            with gr.Accordion("현재 신용 상태 자세히", open=False, elem_classes="rr-detail-accordion"):
                credit_component = gr.Markdown(initial["credit"])
            with gr.Accordion("지표 뜻과 읽는 법", open=False, elem_classes="rr-detail-accordion"):
                with gr.Accordion(f"{lens_name('HY_BBB')} 설명", open=False, elem_classes="rr-detail-accordion"):
                    gr.Markdown(_static_guide_card("HY_BBB"))
                credit_aux_detail_components = {}
                for key in ("BBBOAS", "AOAS", "CPSPREAD"):
                    with gr.Accordion(f"{aux_name(key)} 설명", open=False, elem_classes="rr-detail-accordion"):
                        credit_aux_detail_components[key] = gr.Markdown(
                            initial["aux_details"].get(key, "현재 데이터를 읽을 수 없습니다.")
                        )

        with gr.Tab("금리"):
            gr.Markdown("## 금리 현황")
            gr.HTML('<div class="rr-tab-intro">현재 금리 수준과 최근 변화를 먼저 보고, 단기·장기 관계와 실질금리·물가 관련 금리 차이·Term Premium의 방향을 따로 확인합니다.</div>')
            rate_overview_component = gr.HTML(initial["rate_overview_html"])
            rate_curve_component = gr.HTML(initial["rate_curve_html"])
            rate_context_component = gr.HTML(initial["rate_context_html"])

            gr.Markdown("## 30Y 금리 변화 나눠보기")
            rate_scan_component = gr.HTML(initial["rate_scan_html"])
            with gr.Accordion("약 3개월까지 비교", open=False, elem_classes="rr-detail-accordion"):
                rate_change_table_component = gr.HTML(initial["rate_change_table_html"])

            gr.Markdown("## 장기금리 참고")
            gr.Markdown("아래 지표는 30Y 금리 구성에 직접 더하는 값이 아니라 별도로 함께 보는 참고 자료입니다.")
            rate_reference_component = gr.HTML(initial["rate_reference_html"])

            with gr.Accordion("지표 뜻과 읽는 법", open=False, elem_classes="rr-detail-accordion"):
                rate_core_detail_components = {}
                for key in ("DGS30", "DGS2", "DFII10", "T10Y3M"):
                    with gr.Accordion(f"{core_name(key, short=True)} 설명", open=False, elem_classes="rr-detail-accordion"):
                        rate_core_detail_components[key] = gr.Markdown(
                            initial["details"].get(key, "현재 데이터를 읽을 수 없습니다.")
                        )
                rate_aux_detail_components = {}
                for key in ("BREAKEVEN", "TERMPREM"):
                    with gr.Accordion(f"{aux_name(key)} 설명", open=False, elem_classes="rr-detail-accordion"):
                        rate_aux_detail_components[key] = gr.Markdown(
                            initial["aux_details"].get(key, "현재 데이터를 읽을 수 없습니다.")
                        )

                rate_notes_component = gr.HTML(initial["rate_notes_html"])

        with gr.Tab("흐름"):
            monthly_component = gr.Markdown(initial["monthly"])
            with gr.Accordion("지난 30일 읽는 법", open=False):
                gr.Markdown(HISTORY_HELP)
            with gr.Accordion("데이터 설명·주의사항", open=False):
                history_source_component = gr.Markdown(initial["history_source"])

            gr.Markdown("---\n\n## 지표별 흐름")
            selector = gr.Dropdown(choices=choices, value=default_key, label="지표 선택")
            history_state = gr.State(initial["history"])
            chart_data_state = gr.State(initial["chart_data"])
            hist_plot = gr.LinePlot(
                value=initial["history_plot"], x="날짜", y="최신값",
                title="선택 지표의 지난 30일 값 변화",
            )
            with gr.Accordion("현재 제공되는 전체 기간 흐름", open=False):
                selected_chart = gr.LinePlot(
                    value=initial["charts"][default_key], x="날짜", y="값",
                    title="선택 지표의 현재 제공되는 전체 기간 흐름",
                )
            with gr.Accordion("지난 30일 표", open=False):
                hist_table = gr.Dataframe(initial["history_table"], wrap=True, interactive=False)
            with gr.Accordion("지표 뜻과 읽는 법", open=False, elem_classes="rr-detail-accordion"):
                interpretation_card = gr.Markdown(_static_guide_card(default_key))
                gr.Markdown(CHART_HELP)

            def _history_selection(key, history, chart_data):
                history = history if isinstance(history, pd.DataFrame) else pd.DataFrame(history or [])
                chart_data = chart_data if isinstance(chart_data, pd.DataFrame) else pd.DataFrame(chart_data or [])
                return (
                    _static_guide_card(key),
                    _history_plot_data(history, key),
                    _history_table(history, key),
                    _chart_data({"chart_data": chart_data}, key),
                )

            selector.change(
                fn=_history_selection,
                inputs=[selector, history_state, chart_data_state],
                outputs=[interpretation_card, hist_plot, hist_table, selected_chart],
            )

        with gr.Tab("비교"):
            gr.Markdown("## 최신 지표 비교")
            gr.Markdown("각 지표의 최신 관측값을 비교합니다. 지표별 관측일은 다를 수 있습니다.")
            with gr.Accordion("표 읽는 법", open=False):
                gr.Markdown(SIGNAL_MATRIX_HELP)
            matrix_component = gr.Dataframe(initial["matrix"], wrap=True, interactive=False)
            with gr.Accordion("상대 위치·관측일", open=False):
                matrix_detail_component = gr.Dataframe(initial["matrix_detail"], wrap=True, interactive=False)

            gr.Markdown("---\n\n## 같은 날짜로 비교")
            date_selector = gr.Dropdown(
                choices=initial["common_dates"],
                value=initial["selected_common_date"],
                label="기준일",
            )
            date_cards_component = gr.HTML(initial["date_cards_html"])
            gr.Markdown("핵심 6개에 실제 관측값이 모두 있는 날짜만 선택할 수 있습니다.")

            def _date_selection(date, chart_data):
                chart_data = chart_data if isinstance(chart_data, pd.DataFrame) else pd.DataFrame(chart_data or [])
                return _date_cards_html(chart_data, date)

            date_selector.change(
                fn=_date_selection,
                inputs=[date_selector, chart_data_state],
                outputs=date_cards_component,
            )

        with gr.Tab("설명"):
            guide_selector = gr.Dropdown(choices=guide_choices, value=default_key, label="상세 설명을 볼 지표")
            guide_card = gr.Markdown(_static_guide_card(default_key))

            def _guide_card(key):
                return _static_guide_card(key)

            guide_selector.change(fn=_guide_card, inputs=guide_selector, outputs=guide_card)

            with gr.Accordion("시장 전체 참고 지표", open=False, elem_classes="rr-detail-accordion"):
                market_reference_components = {}
                for key in ("NFCI", "STLFSI"):
                    with gr.Accordion(f"{aux_name(key)} 설명", open=False, elem_classes="rr-detail-accordion"):
                        market_reference_components[key] = gr.Markdown(
                            initial["aux_details"].get(key, "현재 데이터를 읽을 수 없습니다.")
                        )

            with gr.Accordion("RiskRadar 읽는 법", open=False, elem_classes="rr-detail-accordion"):
                gr.Markdown(GUIDE_INTRO)

            with gr.Accordion("지표를 함께 보는 법", open=False, elem_classes="rr-detail-accordion"):
                gr.Markdown(plain_language(RELATIONSHIP_GUIDE))

        reload_outputs = [
            data_health_component,
            loaded_banner,
            status_summary_component,
            status_warning_component,
            decision_tracking_component,
            decision_snapshot_json_component,
            decision_diff_json_component,
            aux_status_component,
            status_json_component,
            data_quality_json_component,
            data_basis_component,
            status_cards_component,
            market_interpretation_component,
            key_indicator_cards_component,
            status_changes_component,
            decision_basis_component,
            rate_overview_component,
            rate_curve_component,
            rate_scan_component,
            rate_change_table_component,
            rate_reference_component,
            rate_notes_component,
            credit_map_component,
            credit_context_component,
            rate_context_component,
            credit_timeline_component,
            past_credit_episodes_component,
            credit_component,
            *[credit_aux_detail_components[k] for k in ("BBBOAS", "AOAS", "CPSPREAD")],
            *[rate_core_detail_components[k] for k in ("DGS30", "DGS2", "DFII10", "T10Y3M")],
            *[rate_aux_detail_components[k] for k in ("BREAKEVEN", "TERMPREM")],
            *[market_reference_components[k] for k in ("NFCI", "STLFSI")],
            history_source_component,
            monthly_component,
            history_state,
            chart_data_state,
            hist_plot,
            hist_table,
            selected_chart,
            matrix_component,
            matrix_detail_component,
            date_selector,
            date_cards_component,
        ]

        def _reload_latest(selected_key):
            snap = load_dashboard_snapshot(store)
            payload = _dynamic_payload(snap, selected_key or default_key, store)
            return (
                payload["data_health"],
                payload["banner"],
                payload["status_summary"],
                payload["status_warning"],
                payload["decision_tracking"],
                payload["decision_snapshot_json"],
                payload["decision_diff_json"],
                payload["aux_status"],
                payload["status_json"],
                payload["data_quality_json"],
                payload["data_basis"],
                payload["status_cards"],
                payload["market_interpretation"],
                payload["key_indicator_cards"],
                payload["status_changes_html"],
                payload["decision_basis"],
                payload["rate_overview_html"],
                payload["rate_curve_html"],
                payload["rate_scan_html"],
                payload["rate_change_table_html"],
                payload["rate_reference_html"],
                payload["rate_notes_html"],
                payload["credit_map"],
                payload["credit_context_html"],
                payload["rate_context_html"],
                payload["credit_timeline_html"],
                payload["past_credit_episodes_compact"],
                payload["credit"],
                *[payload["aux_details"].get(k, "현재 데이터를 읽을 수 없습니다.") for k in ("BBBOAS", "AOAS", "CPSPREAD")],
                *[payload["details"].get(k, "현재 데이터를 읽을 수 없습니다.") for k in ("DGS30", "DGS2", "DFII10", "T10Y3M")],
                *[payload["aux_details"].get(k, "현재 데이터를 읽을 수 없습니다.") for k in ("BREAKEVEN", "TERMPREM")],
                *[payload["aux_details"].get(k, "현재 데이터를 읽을 수 없습니다.") for k in ("NFCI", "STLFSI")],
                payload["history_source"],
                payload["monthly"],
                payload["history"],
                payload["chart_data"],
                payload["history_plot"],
                payload["history_table"],
                payload["charts"][selected_key or default_key],
                payload["matrix"],
                payload["matrix_detail"],
                gr.update(choices=payload["common_dates"], value=payload["selected_common_date"]),
                payload["date_cards_html"],
            )

        demo.load(fn=_reload_latest, inputs=[selector], outputs=reload_outputs, queue=False)
        reload_button.click(fn=_reload_latest, inputs=[selector], outputs=reload_outputs, queue=False)

    return demo
