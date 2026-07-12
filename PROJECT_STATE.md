# RiskRadar — Current Project State

## 1. Baseline

Current completed baseline: **v0.8.1**

The v0.8.1 release was validated with:

- 241 passing tests,
- fresh extraction verification,
- synthetic refresh success,
- Gradio `Blocks` creation,
- rate composition output,
- decision ledger generation,
- Telegram sample generation.

The current repository must still be inspected before assuming it exactly matches the release package.

---

## 2. What RiskRadar is

RiskRadar is a macro and corporate-credit risk monitoring system.

It collects data, computes state and change logic, stores versioned cache data, records decision snapshots and a permanent decision ledger, renders a Gradio dashboard, and can send Telegram summaries.

The tool is designed to help the user understand:

- current credit conditions,
- rate conditions,
- volatility conditions,
- recent direction,
- the relationship between important indicators.

It is not intended to produce a single risk score or a deterministic market forecast.

---

## 3. Current architecture at a high level

### Data and refresh

The Python backend is the analytical source of truth.

Major responsibilities include:

- FRED collection,
- transformations,
- core states,
- auxiliary indicators,
- credit episode state machine,
- 30Y rate analysis,
- versioned cache publication,
- decision snapshots/diffs,
- permanent decision ledger,
- pruning,
- Telegram output.

### Cache publication

The system uses versioned cache data and pointer-last activation semantics.

The active pointer should only move after the new version is successfully written.

### Decision history

The permanent decision ledger preserves authoritative stored decision snapshots.

It must not fabricate historical decisions by recomputing old raw data with current logic.

The ledger is intentionally outside ordinary version pruning.

---

## 4. Important completed milestones

### v0.7.0

- change-first first page,
- mobile UI improvements.

### v0.7.1

- 30Y US Treasury analysis,
- same-maturity decomposition context,
- long-rate detail.

### v0.7.2

- recent 90-day corporate-credit timeline,
- past credit records,
- major user-facing wording audit.

### v0.7.3

- permanent decision ledger.

### v0.7.4

- scan-first UI.

### v0.8.0

- numeric information restored to cards,
- state/trend separation,
- dedicated rate tab,
- date-select comparison,
- card/table-first information structure.

### v0.8.1

- broad copy audit,
- CP `하락 전환` summary contradiction fixed,
- HY level labels separated from credit episode labels,
- direct-but-not-overcertain market-impact wording,
- shared copy centralization,
- credit/rate detail placement corrected,
- visual polish and state styling,
- web/Telegram terminology alignment.

---

## 5. Current user-facing state language

### Credit episode process

- 특이 신호 없음
- 상승 조짐
- 상승 확인
- 높은 수준 지속
- 하락 전환
- 신호 해제

### Core HY level concept

The core card is a level regime, not an episode trend.

Use level-oriented wording rather than `상승 신호` wording.

### Rates

Rate cards describe the relevant rate state and recent direction separately.

### Volatility

Volatility state is a warning/state concept, not a generic `평소` concept.

The old generic `평소` wording was rejected because each engine state has a different meaning.

---

## 6. Current Gradio tab structure

Current tabs:

1. 오늘
2. 신용
3. 금리
4. 흐름
5. 비교
6. 설명

### 오늘

Contains the overall summary/overview experience.

Its exact future structure is now under reconsideration.

### 신용

Contains:

- HY−BBB,
- HY/BBB/A/CP credit state displays,
- 90-day credit timeline,
- past credit records,
- BBB/A/CP-related detailed interpretation.

### 금리

Contains:

- rate overview cards,
- curve context,
- 30Y detail,
- real 10Y,
- 10Y−3M,
- same-maturity Treasury/TIPS difference,
- Term Premium.

### 흐름

Shows time-oriented views.

### 비교

Contains latest comparison and date-select comparison.

### 설명

Contains methodology/reference explanations and broader indicators such as NFCI/STLFSI.

---

## 7. Latest accepted product direction

This is the most important current context.

RiskRadar should **not** be optimized mainly as a daily dashboard.

The user may return after several days or weeks.

The first screen should help him rebuild the current market picture quickly.

The core questions are:

1. 지금 어떤 상태인가?
2. 최근 어떤 방향으로 움직였나?
3. 왜 이런 상태인가?

### Accepted

- Reconsider `오늘` as an overview/status concept.
- `현황` is the leading naming candidate.
- Table/card first.
- Prose second.
- Prose should explain relationships not visible from the table.
- The first screen should prioritize state recovery over "what changed today".

### Explicitly rejected

- A daily-priority dashboard.
- A new `오늘 무엇을 볼 것인가` editorial ranking layer.
- Making `새로 달라진 점` the organizing center of the first screen.

### Not yet decided

- final first-tab name,
- final block order,
- whether top three domain cards remain or are replaced by an overview matrix,
- whether mini charts should be added,
- whether `현재 추세` remains as an independent block,
- the final form of `오늘의 해석`.

Do not treat any of these unresolved items as approved implementation.

---

## 8. Leading first-screen concept under discussion

The most promising direction is a summary matrix/card view first, followed by very short relational prose.

Concept example:

| 영역 | 현재 | 상태 | 최근 흐름 |
|---|---|---|---|
| 신용 | HY 4.05%p | 높은 수준 지속 | HY ↑ · CP ↓ |
| 금리 | 30Y 4.99% | 급격한 상승 없음 | 실질 10Y ↑ · TP ↓ |
| 변동성 | VIX 17.4 | 경계 신호 없음 | 1개월 방향 |

Then a short `전체 흐름` section of only 1–2 sentences.

The sentence should explain relationships, for example:

- HY remains high while CP is easing.
- A rise in real yields is partly offset by a fall in Term Premium.
- VIX does not show broad market stress.

The prose must not simply repeat the table.

This concept is not yet approved for implementation.

---

## 9. Important wording principles

### Goal

Be clear, not vague; precise, not over-defensive; direct, not falsely certain.

### Direct mechanical relationship

State directly.

Example:

- `CP Spread가 오르면 신용도가 낮은 기업의 단기 조달금리가 우량 기업보다 더 높아집니다.`

### Effect on another market indicator

Use `요인` or `압력`.

Example:

- `Term Premium 상승은 10년·30년 장기금리를 끌어올리는 요인입니다.`

### Secondary macro outcome

Use conditional wording.

Example:

- `상승이 오래 이어지면 기업의 차입과 투자를 제약할 수 있습니다.`

### Avoid

- 설명을 지지합니다
- 잘 맞습니다
- 방향과 부합합니다
- 부담 확대
- 힘과 맞을 수 있습니다
- 결과가 달라지면

Prefer naming the actual result.

---

## 10. Important bugs and lessons already learned

### CP contradiction

A previous UI summary grouped `하락 전환` with active upward states and could say:

- `CP 하락 전환`
- while also saying `상승 신호가 확인됩니다`

This was fixed in v0.8.1.

Do not reintroduce state grouping that collapses `하락 전환` into `상승 확인` language.

### State vs trend confusion

A positive one-month change does not mean the current state must be an upward state.

A recent decline does not mean a high level regime disappears.

### 30Y overemphasis

A prior UI made the 30Y panel disproportionately large on the first screen.

That was rejected. Detailed 30Y analysis belongs in the rate tab.

### Numbers disappeared in v0.7.4

The scan-first redesign became too verbal.

v0.8.0 restored:

- current value,
- state,
- recent 1-month change.

Do not remove the numbers again in pursuit of a cleaner UI.

### Generic `평소`

A universal normal state was misleading because each indicator's engine state means something different.

Do not restore generic `평소` wording across unrelated domains.

---

## 11. Protected technical areas

Do not change without explicit approval:

- collection,
- FRED series mapping,
- thresholds,
- state rules,
- credit episode transitions,
- 30Y decomposition calculations,
- refresh ordering,
- cache activation semantics,
- decision snapshot semantics,
- decision ledger semantics,
- pruning behavior,
- Telegram notification conditions.

UI/copy work should not modify these areas.

---

## 12. Testing baseline and release discipline

v0.8.1 release validation included:

- 241 passing tests,
- fresh extraction test run,
- synthetic refresh success,
- Gradio app smoke,
- Telegram sample output,
- patch-to-full tree equality.

The next agent should inspect the current repository before assuming the exact same test count.

For every substantial change:

- run focused tests,
- run the full suite,
- review final diff,
- report changed files,
- report whether protected engine files changed,
- test a real render/app path when UI changes.

---

## 13. Known repository hygiene debt

This has been discussed but not executed.

Current v0.8.1 package includes approximately:

- 22 migration documents,
- 36 test files.

Desired direction:

- stop accumulating migration documents,
- preserve regression behavior while consolidating tests by domain,
- reduce README duplication,
- consider a compact `OPERATIONS.md`.

Do not delete tests just because they are old.

Do not claim cleanup is complete.

---

## 14. Immediate next task for Codex

The next Codex task should be analysis-first.

Do not edit files immediately.

Inspect:

- current first-tab render path,
- top three domain cards,
- current `오늘의 해석` implementation,
- `현재 추세`,
- `왜 이렇게 봤나`,
- CSS classes,
- relevant tests.

Then report:

1. current structure,
2. redundant blocks,
3. blocks that should remain,
4. merge/remove candidates,
5. proposed first-screen structure,
6. mobile-first layout,
7. files likely to change,
8. expected test impact.

The user will approve or reject the design before implementation.
