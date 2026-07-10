# RiskRadar — Codex Working Instructions

## 1. Read this first

Before doing any work in this repository:

1. Read this file completely.
2. Read `PROJECT_STATE.md` completely.
3. Inspect `git status` and do not discard unrelated user changes.
4. Confirm the current application version from the code.
5. Inspect the relevant implementation and tests before proposing changes.

For UI or product-direction work, do not start coding until the current structure has been inspected and the proposed direction has been approved by the user.

---

## 2. Project identity

RiskRadar is a macro and corporate-credit risk monitoring tool.

It is not:

- a prediction engine,
- a trading signal generator,
- a single-score "risk index",
- a daily-news dashboard,
- a system that should infer precise causal relationships from a few indicators.

The current Python implementation is the source of truth for collection, transformations, state rules, credit episodes, cache publication, decision history, and Telegram behavior.

The user is the primary target user. Optimize for his real use pattern rather than for a generic first-time audience.

---

## 3. Current product philosophy

The user does not necessarily open RiskRadar every day. He may return after several days or weeks.

The first screen should help him quickly recover:

1. What state is the market in now?
2. What has moved recently?
3. Why is the current state what it is?

Optimize for scanability, visibility, and rapid state recovery.

Prefer:

- tables and cards before prose,
- current value + current state + recent change,
- compact comparisons,
- visible hierarchy,
- mobile-first layouts,
- short prose only when it explains relationships that numbers alone do not show.

Avoid:

- long prose before the numbers,
- repeating a table in sentence form,
- a daily "what matters today" editorial layer,
- redundant blocks that show the same state twice,
- feature creep,
- developer jargon in user-facing copy.

Accepted latest direction:

- The first tab should be reconsidered as an overview/status screen rather than a daily screen.
- `현황` is the leading candidate to replace `오늘`, but the final name is not yet approved.
- A table/card summary should come before prose.
- Prose should explain cross-indicator relationships, not restate values.
- The previously suggested "today priority dashboard" direction was explicitly rejected.

Do not implement a new first-tab structure until the user approves the design.

---

## 4. Protected analysis and data behavior

Do not change the following without explicit user approval:

- FRED series definitions,
- data collection behavior,
- thresholds,
- core state rules,
- credit episode transition rules,
- 30Y rate decomposition calculations,
- refresh ordering,
- cache versioning,
- pointer-last activation,
- stale / carried-forward recovery rules,
- decision snapshot semantics,
- decision diff semantics,
- decision ledger semantics,
- pruning behavior,
- Telegram notification conditions.

Presentation changes must not silently alter analytical logic.

When a task is supposed to be UI/copy only, verify that protected engine files are unchanged before declaring completion.

---

## 5. Important conceptual distinctions

### State is not trend

Do not mix:

- current state,
- recent direction,
- duration of a state.

Examples:

- `하락 전환` can coexist with a positive 1-month change.
- A high HY level can coexist with a recent decline.

### HY level state is not the same as credit episode state

The core HY card describes the current level regime.

The credit tab describes an episode process such as:

- 특이 신호 없음
- 상승 조짐
- 상승 확인
- 높은 수준 지속
- 하락 전환
- 신호 해제

Do not reuse one label system for the other.

### OAS interpretation

OAS rising does not necessarily mean the absolute corporate bond yield rises, because Treasury yields can move separately.

Prefer precise wording such as:

- `BBB OAS가 오르면 BBB 기업의 국채 대비 추가 조달비용이 커집니다.`

Avoid claiming that absolute borrowing cost must rise unless the underlying data relationship supports that statement.

### Term Premium interpretation

Use direct but not over-certain language.

Good:

- `Term Premium 상승은 10년·30년 장기금리를 끌어올리는 요인입니다.`

Too weak:

- `장기금리가 높은 상태를 유지하는 힘과 맞을 수 있습니다.`

Too strong:

- `Term Premium이 오르면 30년 금리가 반드시 오릅니다.`

---

## 6. User-facing language rules

Use the following confidence ladder.

### A. Direct mechanical relationship

State it directly.

Examples:

- `HY−BBB가 커지면 HY와 BBB 사이의 금리 격차가 벌어집니다.`
- `CP Spread가 오르면 신용도가 낮은 기업의 단기 조달금리가 우량 기업보다 더 높아집니다.`

### B. Effect on another market indicator

Use words such as `요인`, `압력`, or a clearly conditioned relationship.

Examples:

- `실질 10Y 상승은 장기 국채금리를 끌어올리는 요인입니다.`
- `Term Premium 하락은 장기금리를 낮추는 요인입니다.`

### C. Secondary macroeconomic outcome

Use conditional wording.

Examples:

- `상승이 오래 이어지면 기업의 차입과 투자를 제약할 수 있습니다.`

Avoid these vague patterns when a concrete result can be stated:

- `설명을 지지합니다`
- `잘 맞습니다`
- `방향과 부합합니다`
- `부담이 넓어집니다`
- `힘과 맞을 수 있습니다`
- `결과가 달라지면`

Prefer naming the actual affected item:

- which yield,
- which spread,
- whose borrowing cost,
- which market segment,
- which direction.

Keep shared user-facing copy centralized in the existing copy layer, especially `src/riskradar/user_copy.py`, when practical.

---

## 7. UI principles

The current visual grammar is:

1. indicator name,
2. current value,
3. current state,
4. recent change.

Preserve consistency across cards.

Design priorities:

- quiet cards should stay visually quiet,
- active states should stand out without painting the entire interface red,
- status color should have a clear role,
- domain color should remain secondary,
- color must not be the only carrier of meaning,
- mobile layouts should remain readable without horizontal scrolling where possible,
- tables should usually stay compact; three columns is a useful mobile guideline, not a hard rule.

Do not add a visualization merely because it looks impressive. It must improve state recovery or comparison.

Mini charts have been discussed but not approved.

---

## 8. Current tab responsibilities

Current baseline tabs are:

- 오늘
- 신용
- 금리
- 흐름
- 비교
- 설명

Current responsibility split:

### 신용

- HY−BBB
- BBB
- A
- CP
- credit episode state/timeline/history

### 금리

- 30Y
- 2Y
- real 10Y
- 10Y−3M
- same-maturity Treasury/TIPS difference
- Term Premium

### 설명

- NFCI
- STLFSI
- broader reference explanations

Do not move rate details back into the credit tab.

---

## 9. Repository hygiene

The repository currently contains accumulated migration documents and many version-named test files.

This cleanup has been discussed but has not yet been executed.

Do not claim repository cleanup is complete.

For future work:

- do not create a migration document for every small version,
- do not create a new version-named test file by default,
- prefer domain-based test modules,
- preserve regression behavior before deleting or consolidating tests,
- do not remove old tests merely because the filename contains an old version,
- avoid generated caches, `__pycache__`, `.pytest_cache`, `.pyc`, `.pyo`, or temporary artifacts in release packages,
- never add secrets.

---

## 10. Testing rules

Before finishing a change:

1. Run focused tests for the changed area.
2. Run the full test suite.
3. Report exact passed / failed counts.
4. Do not weaken tests merely to make them pass.
5. Distinguish obsolete copy expectations from real functional regressions.
6. For UI changes, run a real app/render smoke test where practical.
7. For release work, verify the final packaged artifact from a fresh extraction.

Current v0.8.1 release baseline was 241 passing tests.

If the current repository differs from that number, inspect the repository before assuming a regression.

---

## 11. Git and change discipline

Before editing:

- inspect `git status`,
- identify unrelated user changes,
- do not reset or discard them.

During work:

- keep the scope narrow,
- avoid opportunistic refactors outside the approved task,
- do not add dependencies without a clear need and user approval.

Before completion:

- review the final diff,
- list changed files,
- state whether any protected engine logic changed,
- report tests and smoke checks,
- mention unresolved issues honestly.

---

## 12. Immediate next product task

Do not code immediately.

First inspect the current implementation of the first tab, especially:

- top three domain cards,
- `오늘의 해석` or equivalent summary area,
- `현재 추세`,
- `왜 이렇게 봤나`,
- related CSS,
- related tests.

Then propose:

1. what should remain,
2. what is redundant,
3. what should be merged,
4. what should move,
5. what should be renamed,
6. a mobile-first first-tab layout.

The leading product direction is:

- overview/status first,
- table/card first,
- 1–2 sentences only for cross-indicator relationships,
- no daily-priority editorial dashboard.

Wait for user approval before implementing the first-tab redesign.
