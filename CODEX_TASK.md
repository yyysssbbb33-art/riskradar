# RiskRadar v0.8.5 — Deep Indicator Guides Implementation Contract

## 0. Codex execution contract

This file is the implementation contract for the current RiskRadar task.

Before changing code:

1. Read `AGENTS.md` completely.
2. Read `PROJECT_STATE.md` completely.
3. Read this file completely.
4. Inspect `git status` and do not discard unrelated user changes.
5. Confirm the checked-out branch is `codex-riskradar-work`.
6. Confirm the starting application version is `0.8.4`.
7. Inspect the relevant current implementation and tests before editing.

The product direction is already decided. Do not redesign the product, replace the tab structure, add unrelated features, or substitute a different information architecture.

Codex must:

- map this specification to the current code,
- restore the required explanatory depth,
- preserve protected analytical logic,
- add regression tests,
- run the full validation suite,
- create a PR from `codex-riskradar-work` to `main`,
- not merge the PR.

If a requirement cannot be implemented truthfully with currently stored data, do not invent data. Implement a clear fallback and document the limitation in the completion report.

Before opening the PR, remove `CODEX_TASK.md` from the PR diff. This is a temporary implementation contract and must not be merged into `main`.

---

## 1. Objective

RiskRadar v0.8.4 restored the visual structure of the credit and rate tabs and added compact relationship cards.

However, the older per-indicator deep guides were not restored. In earlier versions, opening a guide such as `A등급 기업의 추가 금리(A OAS) 설명` provided a deeper explanation covering:

- what the indicator means,
- why RiskRadar watches it,
- which indicators and macro backgrounds should be checked with it,
- why each companion matters,
- what the currently collected companion indicators are showing,
- how agreement and disagreement should be read,
- how rising, falling, and flat outcomes change the interpretation,
- what cannot be concluded from the indicator alone.

The goal of v0.8.5 is to restore that deep explanatory layer inside the existing detail accordions while preserving the current scan-first default screens.

This is not a new signal-engine release. It is a guide-restoration and interpretation-presentation release.

---

## 2. Historical references to inspect

Inspect the relevant files at these commits:

- v0.7.4: `9b5d3a96986d9208f6e8baa72ab3228080611eb7`
- v0.8.0: `73774efaf58b868bec20e3dc64f54d50002e4e1b`
- v0.8.1: `cd7dde9d08e6ea341cf9ab67beab9c4e506de7f5`
- current base: latest `main`, version `0.8.4`

At minimum, inspect the history and current implementation of:

- `src/riskradar/indicator_detail_view.py`
- `src/riskradar/aux_detail_view.py`
- `src/riskradar/aux_interpretation_cards.py`
- `src/riskradar/interpretation_cards.py`
- `src/riskradar/external_guidance.py`
- `src/riskradar/combo_rules.py`
- `src/riskradar/state_guidance.py`
- `src/riskradar/user_copy.py`
- `src/riskradar/relationship_guide.py`
- `src/riskradar/context_view.py`
- `src/riskradar/ui.py`
- relevant tests under `tests/`

Do not revert old files wholesale. Classify historical content into three groups:

### A. Restore dynamically

Content that can truthfully use currently stored RiskRadar values, changes, states, observation dates, freshness, and data-quality information.

### B. Restore as static background guidance

Useful educational or macro context that RiskRadar does not currently collect or automatically classify, such as FOMC decisions, policy guidance, Treasury-supply background, or major one-off events.

### C. Do not restore

Content that:

- makes unsupported causal claims,
- presents non-collected information as a current result,
- contradicts state/trend/duration distinctions,
- treats OAS as an absolute corporate yield,
- treats Breakeven as pure expected inflation,
- treats Term Premium as a directly additive 30Y decomposition component,
- duplicates the same current-value table repeatedly,
- conflicts with the current product philosophy.

---

## 3. Scope

### 3.1 Credit-tab deep guides

Restore deep guides for:

- `HY_BBB` — HY−BBB relative gap
- `BBBOAS` — BBB OAS
- `AOAS` — A OAS
- `CPSPREAD` — CP Spread

The existing v0.8.4 credit overview cards, relationship cards, timeline, episode details, and current visual design must remain.

### 3.2 Rate-tab deep guides

Restore deep guides for:

- `DGS30` — 30Y Treasury yield
- `DGS2` — 2Y Treasury yield
- `DFII10` — real 10Y yield
- `T10Y3M` — 10Y−3M relationship
- `BREAKEVEN` — 10Y Breakeven
- `TERMPREM` — 10Y Term Premium

The existing v0.8.4 rate overview, curve panel, relationship cards, 30Y same-maturity decomposition, reference cards, and notes must remain.

### 3.3 Explanation-tab deep guides

Ensure deep guides remain available for:

- `HYOAS`
- `VIX`
- `NFCI`
- `STLFSI`
- all currently supported core indicators
- all user-visible auxiliary indicators

The explanation tab remains a selector-first reference surface. Do not move long prose onto the overview screen.

---

## 4. Required guide structure

Every restored target guide must contain the following sections in this order unless a section is genuinely inapplicable.

### 4.1 현재 데이터

Show only available stored data:

- current value,
- recent approximately one-month change,
- current state or direction,
- observation date,
- freshness or data-quality status when relevant.

Rules:

- Do not fabricate a state for auxiliary series that only have direction data.
- Do not hide different observation dates.
- Weekly data must not appear to be a daily current observation.
- Missing or stale data must be stated explicitly.
- Do not repeat the exact same current-data block multiple times in one guide.

### 4.2 이 지표가 뜻하는 것

Explain in accessible Korean:

- what is measured,
- the unit,
- whether it is a yield, spread, index, relative gap, or model estimate,
- the direct mechanical meaning of an increase or decrease.

### 4.3 왜 중요한가

Explain the exact RiskRadar question answered by the indicator.

Examples:

- A OAS: whether spread widening reaches further inside investment grade.
- HY−BBB: whether widening is more concentrated in lower-credit companies than at the investment-grade boundary.
- CP Spread: whether lower-credit short-term corporate funding costs more than high-credit short-term funding.
- real 10Y: whether inflation-adjusted long-term yield pressure is rising or falling.

Avoid vague phrases when a concrete market segment, yield, or spread can be named.

### 4.4 같이 볼 지표와 배경

List only genuinely relevant companions. For every companion, explain why it matters.

Separate companions into:

#### RiskRadar current data

Indicators already collected and available in the current snapshot.

#### Background to check separately

Macro or policy items that are not current RiskRadar signals, including where relevant:

- FOMC rate decisions,
- policy guidance,
- Treasury-supply background,
- money-market events,
- major one-off market events.

Every non-collected background item must explicitly say:

> RiskRadar가 자동 판정하는 현재 데이터가 아니라 배경을 확인할 때 보는 항목입니다.

Do not infer a current FOMC stance from unrelated stored series.

### 4.5 현재 함께 보는 지표의 결과

For collected companions, show a compact current-results block containing:

- companion name,
- current value,
- recent change,
- state or direction where available,
- observation date or a clear differing-date note.

This block must be generated dynamically from the current snapshot.

Rules:

- Do not duplicate a full table already visible immediately above.
- Use a compact responsive card or table format.
- If unavailable, state `현재 확인 불가` rather than silently omitting the item.
- Label weekly observations as weekly or show their observation date clearly.

### 4.6 지금 조합을 어떻게 읽는가

Generate a current combination interpretation based only on stored facts.

Support at least:

- main indicator and most companions moving in the same direction,
- main indicator rising while companions do not,
- main indicator falling while companions rise,
- split signals,
- no meaningful movement,
- missing or stale companion data.

Rules:

- Same-time movement is not causality.
- Do not claim lead or lag unless an existing protected rule explicitly supports it.
- Do not create a new score, threshold, state, or prediction.
- Do not collapse disagreement into one overall risk label.

### 4.7 움직임별 해석

Provide concise but substantive educational branches for:

- rise,
- fall,
- limited or flat change,
- agreement with major companions,
- disagreement with major companions.

These are explanations, not forecasts.

### 4.8 주의사항

Include indicator-specific limits where relevant:

- OAS versus absolute corporate-bond yield,
- relative gap versus absolute level,
- maturity mismatch,
- observation-frequency mismatch,
- model-estimate uncertainty,
- composite-index overlap,
- revision risk,
- inability to infer causality.

---

## 5. Approved companion map

Do not use one generic companion list for every guide.

### 5.1 HY−BBB

Primary companions:

- HY OAS
- BBB OAS
- A OAS
- CP Spread
- VIX

External references:

- NFCI
- STLFSI

Background only:

- FOMC and policy environment
- broad Treasury-yield environment

Required questions:

- Is widening concentrated in HY?
- Is BBB also widening?
- Has A joined the move?
- Is short-term corporate funding also showing stress?
- Is market volatility moving at the same time?

### 5.2 BBB OAS

Primary companions:

- HY OAS
- HY−BBB
- A OAS
- CP Spread

Secondary context:

- VIX
- NFCI
- STLFSI
- Treasury-yield environment

Required questions:

- Is the move limited to HY or reaching the investment-grade boundary?
- Is A OAS also moving?
- Is short-term corporate funding also widening?

### 5.3 A OAS

Primary companions:

- BBB OAS
- HY OAS
- HY−BBB
- CP Spread

Secondary context:

- VIX
- NFCI
- STLFSI
- Treasury-yield environment

Background only:

- FOMC and policy environment

Required questions:

- Has the move spread from lower-credit markets into stronger investment grade?
- Is A moving alone, or with BBB and HY?
- Is the absolute Treasury-rate environment moving differently from the spread?

The A OAS guide must explicitly explain that OAS is the extra yield versus comparable Treasuries, not the total corporate-bond yield.

### 5.4 CP Spread

Primary companions:

- HY OAS
- BBB OAS
- A OAS
- VIX

External references:

- NFCI
- STLFSI

Background only:

- FOMC and policy environment
- money-market or funding-market events not collected by RiskRadar

Required questions:

- Is short-term corporate funding stress moving with bond-market spreads?
- Is the move specific to short-term funding?
- Is equity-market volatility moving at the same time?

### 5.5 30Y Treasury yield

Primary companions:

- real 10Y
- 10Y Breakeven
- 10Y Term Premium
- 2Y Treasury yield
- 10Y−3M
- stored 30Y same-maturity real and inflation-compensation decomposition

Background only:

- FOMC and policy guidance
- Treasury-supply context

Required questions:

- Is the recent 30Y direction shared by real yield?
- Is the nominal-versus-inflation-linked gap moving?
- Is Term Premium moving in the same or opposite direction?
- Are short and long yields moving together or diverging?

### 5.6 2Y Treasury yield

Primary companions:

- 30Y Treasury yield
- 10Y−3M
- real 10Y
- 10Y Breakeven

Background only:

- FOMC rate decisions
- policy guidance

Required questions:

- Is the short end moving with or against the long end?
- Is the move associated with real-yield or inflation-compensation direction?
- Is the curve relationship steepening or flattening in plain language?

### 5.7 Real 10Y

Primary companions:

- 30Y Treasury yield
- 10Y Breakeven
- 10Y Term Premium
- 2Y Treasury yield

Background only:

- FOMC policy environment
- growth and inflation background not directly classified by RiskRadar

Required questions:

- Is inflation-adjusted yield pressure moving with the nominal long yield?
- Is Breakeven moving in the same or opposite direction?
- Is Term Premium reinforcing or offsetting the move?

### 5.8 10Y−3M

Primary companions:

- 2Y Treasury yield
- 30Y Treasury yield
- real 10Y
- 10Y Breakeven

Background only:

- FOMC policy environment
- recession interpretation must remain conditional and non-probabilistic

Required questions:

- Is the relationship becoming more inverted or less inverted?
- Is the change driven by short rates, long rates, or both?
- Do not convert this into a recession probability.

### 5.9 10Y Breakeven

Primary companions:

- real 10Y
- 30Y Treasury yield
- 10Y Term Premium

Background only:

- inflation data and inflation-risk background
- FOMC inflation communication

Required questions:

- Is nominal long-yield movement accompanied by a wider nominal-versus-inflation-linked gap?
- Is real yield moving in the same or opposite direction?

The guide must state that Breakeven includes inflation expectations and risk or liquidity effects and is not pure expected inflation.

### 5.10 10Y Term Premium

Primary companions:

- 30Y Treasury yield
- real 10Y
- 10Y Breakeven
- 2Y Treasury yield

Background only:

- Treasury supply and demand
- duration risk
- policy uncertainty

Required questions:

- Is estimated extra compensation for holding long duration rising or falling?
- Is it moving with or against the long yield?

The guide must state that Term Premium is a model estimate and is not directly added to the stored 30Y same-maturity decomposition.

### 5.11 HY OAS

Primary companions:

- BBB OAS
- A OAS
- HY−BBB
- CP Spread
- VIX

External references:

- NFCI
- STLFSI

Required questions:

- Is the level high while recent direction is falling?
- Is widening confined to HY or shared across credit grades?
- Is short-term funding or equity volatility moving at the same time?

Keep the distinction between HY level state and credit-episode state.

### 5.12 VIX

Primary companions:

- HY OAS
- BBB OAS
- CP Spread
- NFCI
- STLFSI

Required questions:

- Is equity-market volatility moving with credit spreads?
- Is volatility moving alone?

Do not treat VIX as proof of credit stress or causality.

### 5.13 NFCI and STLFSI

Primary companions:

- HY OAS
- BBB OAS
- A OAS
- CP Spread
- VIX

Requirements:

- Explain that they are broad composite reference indicators.
- Show weekly frequency and observation-date differences clearly.
- Explain overlap and revision risk.
- Do not use them as engine inputs or elevate them into a new overall risk score.

---

## 6. Language and interpretation rules

### 6.1 State, trend, and duration

Do not mix:

- current state,
- recent direction,
- duration of a state.

Examples:

- a high HY level may coexist with a recent decline,
- `하락 전환` may coexist with a positive one-month change.

### 6.2 OAS

OAS is the extra yield versus comparable Treasuries.

Allowed:

- `A OAS가 오르면 A등급 기업이 비슷한 만기의 국채보다 추가로 부담하는 금리 격차가 커집니다.`

Not allowed:

- claiming that OAS rise alone proves the absolute corporate-bond yield rose,
- claiming that actual borrowing cost must have risen without the underlying total-yield data.

### 6.3 HY−BBB

HY−BBB is a relative gap between two credit segments. It is not an absolute stress level by itself.

### 6.4 Breakeven

Do not call it pure expected inflation. Explain that it also reflects inflation risk and liquidity conditions.

### 6.5 Term Premium

Use direct but bounded language:

- `Term Premium 상승은 장기금리를 끌어올리는 요인입니다.`

Do not say:

- it guarantees a 30Y yield rise,
- it is directly added to the stored 30Y same-maturity decomposition.

### 6.6 Correlation and causality

Same-period movement is not causality or lead-lag evidence.

Avoid vague phrases:

- `설명을 지지합니다`
- `잘 맞습니다`
- `방향과 부합합니다`
- `힘과 맞을 수 있습니다`
- `결과가 달라지면`

Prefer naming the actual affected yield, spread, market, or company segment and the actual direction.

---

## 7. UI requirements

- Preserve the v0.8.4 overview screen.
- Preserve current credit and rate cards and relationship cards.
- Put deep explanations inside existing `지표 뜻과 읽는 법` or equivalent detail accordions.
- Do not put long guide prose on the default overview screen.
- Use the current credit and rate visual grammar.
- Keep mobile layouts responsive.
- Do not duplicate the same current-value block repeatedly.
- Use compact tables or cards for current companion results.
- Long educational text may be Markdown inside accordions.
- Ensure reload updates all dynamic deep-guide current-result components.

---

## 8. Architecture guidance

Prefer a centralized guide-definition layer rather than copying large strings directly into `ui.py`.

A reasonable implementation may include:

- static metadata describing meaning, importance, companions, background items, movement branches, and cautions,
- reusable rendering functions for core, auxiliary, and lens guides,
- dynamic snapshot readers for current companion results,
- current-combination interpretation helpers,
- small UI wiring changes.

Reuse current formatting and naming helpers where practical.

Do not create a parallel state engine.

Do not silently change shared copy used by Telegram unless the task genuinely requires it and the change is explicitly documented.

---

## 9. Protected logic

Do not change without explicit user approval:

- FRED series definitions,
- data collection behavior,
- thresholds,
- core state rules,
- credit episode transition rules,
- 30Y rate-decomposition calculations,
- refresh ordering,
- cache versioning semantics,
- pointer-last activation,
- stale or carried-forward recovery rules,
- decision snapshot semantics,
- decision diff semantics,
- decision ledger semantics,
- pruning behavior,
- Telegram notification conditions.

No new score, threshold, prediction model, recession probability, or causal classifier may be introduced.

Before completion, inspect the diff and explicitly verify that protected engine files and behavior were not changed.

---

## 10. Version and documentation

After successful implementation, bump the product version to `0.8.5` consistently in:

- `src/riskradar/version.py`
- `pyproject.toml`
- README current version heading and release section
- UI data compatibility mapping
- changelog or release notes where the repository currently maintains them

README must state that v0.8.5 restores per-indicator deep explanatory guides while preserving the v0.8.4 default screens and analytical logic.

The v0.8.5 UI must remain compatible with at least v0.8.2, v0.8.3, v0.8.4, and v0.8.5 data-code versions where the existing schema supports that compatibility.

---

## 11. Required tests

Add regression tests covering at least:

1. Every target guide contains the required major sections:
   - current data,
   - meaning,
   - importance,
   - companion indicators and background,
   - current companion results,
   - current combination reading,
   - movement branches,
   - cautions.

2. A OAS includes:
   - BBB and HY context,
   - credit-grade breadth explanation,
   - OAS-versus-total-yield caution,
   - FOMC as background only, not a current automatic result.

3. Rate guides include:
   - real yield,
   - Breakeven,
   - Term Premium,
   - long and short rate relationships.

4. FOMC and other non-collected background items are never rendered as current RiskRadar results.

5. Prohibited OAS claims do not appear.

6. Breakeven is not described as pure expected inflation.

7. Term Premium is not treated as a directly additive 30Y decomposition component.

8. v0.8.4 overview and relationship cards remain present.

9. NFCI and STLFSI remain visible in the explanation surface.

10. Data-code compatibility for v0.8.2 through v0.8.5 remains valid.

11. Reload wiring updates dynamic deep-guide components.

12. Missing, stale, and weekly companion data are rendered truthfully.

---

## 12. Validation

Run:

- focused tests for the new guide rendering,
- `pytest -q` for the full suite,
- Gradio `build_app()` Blocks smoke,
- repository-hygiene checks,
- `git diff` inspection for protected logic,
- desktop and mobile visual verification if a browser is available.

Do not report visual verification if only component construction was tested.

---

## 13. Definition of done

The task is complete only when:

- the target guides have the required deep structure,
- current companion results are dynamic and truthful,
- non-collected background is clearly separated,
- current v0.8.4 default screens remain intact,
- no protected analytical logic changes,
- version and README are consistent,
- full tests and Gradio smoke pass,
- temporary files and generated artifacts are absent,
- `CODEX_TASK.md` is removed from the final PR diff,
- a PR from `codex-riskradar-work` to `main` is opened,
- the PR is not merged.

---

## 14. Completion report format

Codex's final report and PR body must include:

1. Summary
2. Historical content restored
3. Historical content intentionally not restored and why
4. Indicator-by-indicator companion mapping implemented
5. How dynamic current results and static background guidance are separated
6. Changed files
7. Tests and exact result count
8. Protected logic verification
9. Browser or screenshot verification status
10. Remaining limitations
11. PR link

Do not declare completion only from a successful test count. Confirm the specification against the actual diff first.
