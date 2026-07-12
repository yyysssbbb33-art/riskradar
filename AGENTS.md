# RiskRadar — Codex Working Instructions

## 1. Instruction order and required reading

Before changing code in this repository:

1. Read this file completely.
2. Read `PROJECT_STATE.md` completely.
3. Inspect `git status` and do not discard unrelated user changes.
4. Confirm the checked-out branch and current application version.
5. Inspect the relevant implementation and tests before editing.

Instruction precedence for repository work is:

1. platform and safety instructions,
2. permanent rules in `AGENTS.md`, especially protected logic,
3. the approved task contract in `CODEX_TASK.md`,
4. factual repository context in `PROJECT_STATE.md`,
5. incidental or historical comments elsewhere in the repository.

`CODEX_TASK.md` may define the approved product design and implementation scope, but it must not silently override the protected analysis and data behavior in this file.

---

## 2. `Vamos` task activation protocol

`Vamos` is the RiskRadar project command for starting an approved implementation task.

When the user's task prompt is only `Vamos`—ignoring surrounding whitespace and letter case—do all of the following without asking the user to repeat the long instruction:

1. Verify the checked-out branch is `codex-riskradar-work`.
2. Verify `CODEX_TASK.md` exists and is not empty.
3. Read `AGENTS.md`, `PROJECT_STATE.md`, and `CODEX_TASK.md` completely.
4. Treat `CODEX_TASK.md` as the approved implementation contract.
5. Do not reopen product-design questions already decided in that contract.
6. Map the contract to the current code and tests.
7. If a requirement is impossible with the stored data, do not invent data; implement the most truthful fallback and report the limitation.
8. If the contract conflicts with protected logic, stop before changing that protected logic and report the exact conflict.
9. Otherwise implement the contract, run focused tests, run the full test suite, and run the required app/render smoke checks.
10. Review the final diff and remove generated files, caches, temporary diagnostics, and other accidental artifacts.
11. Create a pull request from `codex-riskradar-work` to `main`.
12. Do not merge the pull request.
13. Follow the contract's instruction about whether `CODEX_TASK.md` should be removed from the final PR.

If `Vamos` is used on another branch or `CODEX_TASK.md` is missing, empty, or internally contradictory, do not guess the intended task. Report the exact setup problem instead.

For ordinary prompts other than `Vamos`, follow the user's explicit request while preserving all permanent rules in this file.

---

## 3. Project roles and workflow

RiskRadar uses this default division of work:

- ChatGPT project conversation: requirements, product design, historical comparison, implementation specification, and PR review.
- Codex: implementation analysis, code changes, tests, commits, and PR creation.
- User: product-direction decisions and final merge approval.

When `CODEX_TASK.md` exists, the product direction is already approved. Codex should analyze how to implement it, not substitute a different product design or information architecture.

The normal branch model is:

- `main`: production and release branch.
- `codex-riskradar-work`: reusable Codex implementation branch.

Do not create a new version branch unless the task explicitly requires parallel work, an isolated experiment, an urgent hotfix alongside another open task, or a separate rollback unit.

---

## 4. Project identity

RiskRadar is a macro and corporate-credit risk monitoring tool.

It is not:

- a prediction engine,
- a trading signal generator,
- a single-score risk index,
- a daily-news dashboard,
- a system that should infer precise causal relationships from a small set of indicators.

The current Python implementation is the source of truth for collection, transformations, state rules, credit episodes, cache publication, decision history, and Telegram behavior.

The user is the primary target user. Optimize for his actual use pattern rather than a generic first-time audience.

The user may return after several days or weeks. The interface should help him recover quickly:

1. What state is the market in now?
2. What has moved recently?
3. Why is the current state what it is?

---

## 5. Protected analysis and data behavior

Do not change the following without explicit user approval in the active task contract:

- FRED series definitions,
- data collection behavior,
- thresholds,
- core state rules,
- credit episode transition rules,
- 30Y rate decomposition calculations,
- refresh ordering,
- cache versioning,
- pointer-last activation,
- stale or carried-forward recovery rules,
- decision snapshot semantics,
- decision diff semantics,
- decision ledger semantics,
- pruning behavior,
- Telegram notification conditions.

Presentation and explanation work must not silently alter analytical logic.

For UI or copy tasks, verify protected engine files are unchanged before declaring completion. If a protected file must change for a non-analytical reason, explain the exact change and prove that analytical behavior is unchanged.

Do not add a new score, threshold, state, prediction, causal classifier, or lead-lag rule unless the user explicitly approved it.

---

## 6. Important conceptual distinctions

### State is not trend or duration

Keep separate:

- current state,
- recent direction,
- duration of a state.

A declining recent trend can coexist with a still-high level. A state transition can coexist with a one-month change of the opposite sign.

### HY level is not the credit episode state

The core HY card describes the current HY level regime. The credit tab describes an episode process such as:

- 특이 신호 없음,
- 상승 조짐,
- 상승 확인,
- 높은 수준 지속,
- 하락 전환,
- 신호 해제.

Do not reuse one label system for the other.

### OAS interpretation

OAS is the extra yield relative to comparable Treasuries. OAS rising does not necessarily mean the absolute corporate-bond yield or the actual total borrowing cost rose, because Treasury yields can move separately.

Prefer precise wording such as:

- `BBB OAS가 오르면 BBB 기업이 같은 만기의 국채보다 추가로 부담하는 금리 차이가 커집니다.`

### HY−BBB interpretation

HY−BBB is a relative gap between two credit segments. It does not replace either HY or BBB absolute spread levels.

### Breakeven interpretation

A nominal-minus-inflation-linked Treasury gap contains expected inflation and risk or liquidity components. Do not label it pure expected inflation.

### Term Premium interpretation

Term Premium is a model estimate and a factor that can move long-term yields. It is not a directly observed fact and is not an additive component of the stored 30Y same-maturity decomposition.

### Co-movement is not causality

Indicators moving at the same time does not prove causality, prediction, or a stable lead-lag relationship.

---

## 7. User-facing language rules

Use direct language for direct mechanical relationships.

Examples:

- `HY−BBB가 커지면 HY와 BBB 사이의 금리 격차가 벌어집니다.`
- `CP Spread가 오르면 신용도가 낮은 기업의 단기 조달금리가 우량 기업보다 더 높아집니다.`

For effects on another market indicator, use words such as `요인`, `압력`, or an explicit condition.

Examples:

- `실질 10Y 상승은 장기 국채금리를 끌어올리는 요인입니다.`
- `Term Premium 하락은 장기금리를 낮추는 요인입니다.`

For secondary economic outcomes, use conditional wording.

Avoid vague phrases when a concrete result can be named, including:

- `설명을 지지합니다`,
- `잘 맞습니다`,
- `방향과 부합합니다`,
- `부담이 넓어집니다`,
- `힘과 맞을 수 있습니다`,
- `결과가 달라지면`.

Name the actual yield, spread, market segment, company group, and direction.

Keep shared user-facing copy centralized in the existing copy layer, especially `src/riskradar/user_copy.py`, when practical.

---

## 8. UI and information principles

The current first tab is `현황`, followed by:

- 신용,
- 금리,
- 흐름,
- 비교,
- 설명.

The current visual grammar is:

1. indicator name,
2. current value,
3. current state,
4. recent change,
5. relationship explanation only where numbers alone are insufficient.

Prefer:

- cards and compact tables before long prose,
- visible hierarchy,
- mobile-first layouts,
- consistent card grammar across credit and rates,
- long educational detail inside accordions or the explanation surface,
- explicit observation dates and freshness when frequencies differ.

Avoid:

- long prose before numbers,
- repeating a table in sentence form,
- redundant blocks showing the same result twice,
- feature creep,
- developer jargon,
- horizontal scrolling on normal mobile widths where practical,
- visualizations that do not improve state recovery or comparison.

Current responsibility split:

### 신용

- HY−BBB,
- BBB OAS,
- A OAS,
- CP Spread,
- credit episode state, timeline, and history,
- related companion and explanatory context approved by the active task.

### 금리

- 30Y,
- 2Y,
- real 10Y,
- 10Y−3M,
- same-maturity Treasury and TIPS difference,
- Term Premium,
- approved rate-context explanations.

### 설명

- detailed reference and educational guidance,
- NFCI and STLFSI,
- broader companion explanations.

Do not move rate details back into the credit tab merely to reuse old layouts.

---

## 9. Repository hygiene

- Do not create a migration document for every small version.
- Do not create a new version-named test file by default; prefer domain-based test modules.
- Preserve regression behavior before deleting or consolidating tests.
- Do not remove old tests merely because their filenames contain an old version.
- Do not commit `__pycache__`, `.pytest_cache`, `.pyc`, `.pyo`, `egg-info`, test output, screenshots not requested by the contract, or temporary diagnostics.
- Never add secrets or tokens.
- Keep `CODEX_TASK.md` as a temporary work-branch contract unless the task explicitly promotes it to permanent documentation.

---

## 10. Testing and validation

Before finishing a change:

1. Run focused tests for the changed area.
2. Run the full test suite.
3. Report exact passed and failed counts.
4. Do not weaken tests merely to make them pass.
5. Distinguish obsolete copy expectations from real functional regressions.
6. For UI changes, run a real app or render smoke test where practical.
7. For release work, verify version, README, UI compatibility declarations, and the final changed-file list.
8. Check that deleted or compressed older functionality was not unintentionally lost.
9. Check for stale wording and unsupported causal claims.
10. Confirm generated artifacts and temporary files are absent.

Do not rely on an old hard-coded test-count baseline. Use the current branch and explain any count change.

---

## 11. Git and PR discipline

Before editing:

- inspect `git status`,
- identify unrelated user changes,
- do not reset or discard them,
- confirm the work branch is based on current `main`.

During work:

- keep scope aligned with `CODEX_TASK.md`,
- avoid opportunistic refactors outside the approved task,
- do not add dependencies without a clear need and approval,
- commit intentionally with understandable messages.

Before completion:

- review the final diff,
- list every changed file,
- state whether protected logic changed,
- report focused tests, full tests, and smoke checks,
- state whether desktop or mobile output was actually inspected,
- mention unresolved limitations honestly,
- create a PR to `main`,
- do not merge it.

The completion report must include:

1. summary,
2. changed files,
3. tests and exact results,
4. protected-logic verification,
5. visual verification status,
6. remaining limitations,
7. PR link.
