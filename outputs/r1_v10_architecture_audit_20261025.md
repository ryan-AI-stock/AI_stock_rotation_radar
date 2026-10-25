# R1 v1.0 Architecture Audit

- Audit date: 2026-10-25
- Repository: `AI_stock_rotation_radar`
- Target: Evidence-driven, thesis-based, falsifiable Taiwan AI equity research system
- Scope: architecture audit only; no v1.0 implementation or Dashboard migration
- Current production boundary: R1 is challenger/report-only; no automatic trade
- `formal_model_changed=false`
- `trade_decision_changed=false`
- `active_in_trade_decision=false`
- `report_changed=false`

## 1. Executive conclusion

R1 currently has a usable data-acquisition and reporting foundation, but its decision spine is still score-centric. The newly added context and bounded-deliberation modules are useful prototypes, not the requested v1.0 architecture.

Approximate architecture readiness:

| Engine | Current state | Assessment |
|---|---|---|
| A. Evidence Engine | multiple PIT loaders, source timestamps, readiness gates | PARTIAL |
| B. Context Engine | market breadth selloff and per-stock context prototype | PARTIAL |
| C. Thesis Engine | theme bottleneck thesis and scattered evidence only | MISSING |
| D. Hypothesis Engine | four fixed competing hypotheses and one-day history | EARLY PARTIAL |
| E. Relative Opportunity Engine | score-based pair comparison and recommendation guardrails | PARTIAL, NEEDS REFACTOR |
| F. Learning & Audit Engine | price-only forward outcomes and shadow thresholds | EARLY PARTIAL |

The correct migration is incremental. Existing v0.x outputs must remain available while v1.0 engines write to separate versioned stores. The current Dashboard must not switch to v1.0 until Phase 1-4 contracts and readiness gates pass.

## 2. Current repository architecture

### 2.1 Universe and configuration

- `config/r1.json`: original security list, weights, catalyst policy, account holdings and challenger boundary.
- `config/r1_v02_themes.json`: 11 themes, 52 formal-core names plus Discovery names, six-month target list, review cadence.
- `config/r1_v03_score_rubric.json`: quarterly leader and daily score rubric.
- `config/r1_v04_active_pool.json`: active-pool screening policy.
- `config/r1_v05_policy.json`: free-data long-hold advisor score, target-price overlay and report-only recommendation guardrails.
- `config/r1_performance_benchmarks.json`: Ryan actual-account comparison and 00631L benchmark cash-flow ledger.

The universe is version-labelled but not yet represented as an append-only effective-dated membership ledger.

### 2.2 Data acquisition and Evidence-like modules

- Daily official price and chip data: `market_snapshot.py`, `daily_sources.py`, `benchmark_market.py`.
- Official revenue and financial data: `monthly_revenue.py`, `official_financial_snapshot.py`, `financial_quality.py`.
- EPS and target sources: `toalpha_*`, `yahoo_*`, `investing_target_prices.py`, provider import modules.
- Bottleneck and catalyst evidence: `bottleneck_evidence.py`, `catalyst_evidence.py`, `evidence.py`.
- PIT and readiness: `schema.py`, `evidence_readiness.py`, `required_data.py`, `evidence_gap_queue.py`.

Current catalyst evidence contains 104 rows, 100 distinct URLs and 61 source-family labels. Exact duplicate rows are absent, but semantic duplicate events are not identifiable because there is no canonical event identity.

### 2.3 Score and research engines

- Legacy composite logic: `component_scores.py`, `scoring.py`, `weekly_snapshot.py`.
- Current report-only ranking: `v05_rank.py`.
- Theme leadership: `theme_leader_inputs.py`, `theme_review.py`, `theme_policy.py`.
- Active pool: `active_pool.py`.
- Older staged action and rotation research: `staged_action.py`, `portfolio_policy.py`, `rotation.py`, `shadow_rotation.py`.
- Current recommendations: `recommendations.py`, `recommendation_policy_shadow.py`.

These are mostly score/rule engines. They must be retained as supporting metrics or shadow comparisons, not used as the v1.0 decision spine.

### 2.4 Context and deliberation prototypes

- `transition_layer.py`: broad market/universe selloff detection and pullback candidate research.
- `context_event_layer.py`: distinguishes broad selloff, official deterioration and confirmed catalyst states.
- `deliberation_layer.py`: compares four fixed hypotheses and stores a dated output.

Strengths:

- Broad selloff is not automatically treated as company deterioration.
- One official negative fact does not automatically trigger a sale.
- Supporting evidence URLs and contradictions are retained.

Limitations:

- Context is not yet decomposed into MARKET/THEME/COMPANY/VALUATION/FLOW_POSITIONING with explicit peer and theme relative returns.
- Hypotheses are hard-coded conclusions rather than entities linked to claims.
- Confidence is rule-derived without a claim graph.
- Only one dated deliberation snapshot currently exists.
- No company thesis object or causal-chain state is consulted.

### 2.5 Portfolio and benchmark tracking

- `actual_account.py` and `actual_transactions.json`: Ryan account state.
- `performance_comparison.py`: Ryan actual scope versus 00631L buy-and-hold.
- Current Dashboard separates recommendations from confirmed fills.

This can be reused, but R1 Research Portfolio, 0050, Cash and Candidate Equal Weight do not yet exist as fully separate benchmark ledgers.

### 2.6 Snapshot, outcome and history

- Weekly snapshots are append-only by date.
- Daily-source partitions preserve dates.
- Target-price, consensus and valuation histories exist.
- `forward_outcomes.py` computes close-to-close 5/20/60/130-observation returns for weekly-score rows.
- Current outcome ledger has 704 rows: 68 READY and 636 PENDING as of 2026-10-22.

This is not yet Decision Snapshot evaluation. It does not restore context, thesis, hypotheses, counter-evidence, invalidation or challenger state, and it does not classify reasoning errors.

### 2.7 Dashboard and publication

Existing tabs:

1. R1 Dashboard
2. R1每日訊號資料庫
3. R1實際交易紀錄
4. R1績效每日比較
5. R1每日換倉建議

Reusable capabilities:

- precise range publishing and readback validation;
- actual holding highlighting;
- actual/benchmark NAV display;
- Chinese display layer;
- no-auto-trade wording and transaction/account separation.

The home-page information architecture is not v1.0 compliant. It remains holdings/score/recommendation oriented instead of Market Regime, Theme Map, Portfolio Thesis, Challenger, Evidence and Benchmark oriented.

### 2.8 Schedules

Daily workflow already provides:

- Taiwan-session gate, including unscheduled closure handling;
- bounded retries and source cache;
- tests before materialization;
- daily price/chip/readiness/account/benchmark updates;
- publish and readback;
- durable state commit.

Weekly workflow already provides:

- confirmed week-final gate;
- consensus, target, valuation, revenue, financial and theme refresh;
- append-only weekly snapshot;
- evidence-gap and membership review;
- publish and readback.

Missing schedule responsibilities:

- explicit quarterly universe/thesis review workflow;
- due-date queue for 5/20/60TD Decision Snapshot reviews;
- claim expiry and stale-thesis review;
- controlled model-change-proposal evaluation;
- LLM extraction pipeline with deterministic validation.

## 3. Mapping existing modules to the six engines

| Target engine | Existing modules/data | Disposition |
|---|---|---|
| Evidence | daily sources, official financial/revenue, consensus/target/valuation histories, bottleneck/catalyst CSV, readiness | REFACTOR into a canonical Fact/Event/Claim store; keep collectors |
| Context | market snapshot, transition layer, context event layer, industry state, price/flow fields | MERGE into five-level Context Engine |
| Thesis | theme bottleneck text, bottleneck evidence, Discovery causal-chain text | NEW company-level Thesis Engine; reuse evidence only |
| Hypothesis | deliberation layer, context states | REFACTOR into evidence-linked hypothesis objects and review transitions |
| Relative Opportunity | rotation pair, recommendations, active pool, v05 score | REFACTOR; score becomes supporting metric, pairwise thesis comparison becomes primary |
| Learning & Audit | weekly snapshots, forward outcomes, recommendation shadow | REFACTOR/EXTEND into immutable Decision Snapshots, outcome reviews, error taxonomy and proposals |

## 4. KEEP / REFACTOR / MERGE / DEPRECATE / NEW

### KEEP

- Taiwan trading-session gate and unscheduled-closure logic.
- Official price, chip, monthly-revenue and MOPS financial collectors.
- PIT timestamps and future-data rejection.
- Missing values remain NA; never convert to zero.
- Append-only dated weekly snapshots and dated raw-source partitions.
- Actual-account and confirmed-fill boundary.
- Benchmark cash-flow reconciliation.
- Google Sheets publish/readback verification.
- 11-theme universe as the starting v1.0 universe, with versioned future review.

### REFACTOR

- `schema.py`: from generic lineage to explicit Fact/Event/Claim/Thesis/Hypothesis/Decision contracts.
- catalyst evidence: replace row-level event treatment with canonical event and claim identity.
- `context_event_layer.py`: produce five context levels and relative comparisons.
- `deliberation_layer.py`: consume Thesis and Claim objects; remove direct inference from sparse flags.
- `rotation.py` and `recommendations.py`: use pairwise thesis/opportunity comparison, not total-score gap as the core decision.
- `forward_outcomes.py`: evaluate Decision Snapshots and thesis developments, not only prices.
- Dashboard payload: become a view over v1.0 stores rather than the place where decision logic is assembled.

### MERGE

- `evidence.py` and `catalyst_evidence.py` into one canonical event/claim adapter while preserving legacy readers.
- transition/context/market-signal concepts into Context Engine.
- staged action, portfolio policy and recommendation guardrails into one Portfolio State transition policy.
- provider-specific consensus/target import results behind one normalized evidence interface.

### DEPRECATE, BUT DO NOT DELETE DURING MIGRATION

- total score as the final decision engine;
- full-universe ranking as a rotation trigger;
- P1/P2/P3 wording that implies actionability from incomplete overlays;
- legacy `ADD/TRIM/EXIT` paths not connected to confirmed thesis state;
- current hard-coded deliberation conclusions once the v1.0 Hypothesis Engine is ready.

### NEW

- Fact Store and source-quality registry.
- canonical Event and Claim Graph.
- company Thesis Store and causal-chain edges.
- five-level Context Snapshot.
- Hypothesis Review and conclusion-transition ledger.
- Expectation/Price-in layer.
- pairwise Relative Opportunity Review.
- Portfolio State machine with hysteresis.
- immutable Decision Snapshot.
- 5/20/60TD Outcome Review and Error Taxonomy.
- Model Change Proposal registry and approval workflow.
- effective-dated Universe Version ledger.
- separate R1 Research Portfolio and additional benchmark ledgers.

## 5. Required database/schema changes

Use versioned date partitions or append-only JSONL/Parquet during migration. Do not overwrite current v0.x files.

### 5.1 `facts`

Required fields:

`fact_id, entity, metric, value, unit, period, source_class, source, source_url, source_date, published_at, available_at, retrieved_at, revision_id, supersedes_fact_id, status`

Fact records contain no positive/negative/trade interpretation.

### 5.2 `events`

`event_id, canonical_event_id, event_fingerprint, event_type, scope, direction, horizon, first_seen, last_updated, expiry, status`

Fingerprint must use normalized entity/event/date/subject fields. URL is not event identity.

### 5.3 `claims` and claim edges

`claim_id, event_id, claim_text, supporting_fact_ids, contradicting_fact_ids, source_families, confidence, first_seen, last_updated, expiry, status`

### 5.4 `theses` and causal-chain edges

`thesis_id, ticker, version, effective_from, expected_horizon, thesis_state, key_drivers, key_risks, invalidation_conditions, unknowns, last_updated`

Each causal edge:

`edge_id, thesis_id, from_node, to_node, state(CONFIRMED/INFERENCE/UNKNOWN), supporting_claim_ids, contradicting_claim_ids`

### 5.5 `context_snapshots`

`date, ticker, market_context, theme_context, company_context, valuation_context, flow_positioning_context, primary_context, secondary_context, confidence, evidence_ids, unknowns`

### 5.6 `hypothesis_reviews`

`review_id, date, ticker, hypothesis_id, supporting_claim_ids, counter_claim_ids, missing_evidence, confidence, previous_conclusion, transition, reason`

### 5.7 `relative_opportunity_reviews`

`date, holding_ticker, challenger_ticker, dimension_results, rotation_advantage, evidence_ids, counter_evidence_ids, unknowns, confidence, state`

### 5.8 `decision_snapshots`

Append-only and immutable:

`snapshot_id, date, ticker, context_snapshot_id, thesis_id/version, portfolio_state, hypothesis_review_ids, supporting_evidence, counter_evidence, unknowns, confidence, invalidation, expected_horizon, challenger, rotation_state, next_observation`

### 5.9 `outcome_reviews`

`snapshot_id, horizon_td, due_date, review_date, stock_return, theme_relative_return, market_relative_return, thesis_edge_results, classification, error_types, unresolved_fields`

### 5.10 `model_change_proposals`

`proposal_id, created_at, evidence_window, error_pattern, proposed_change, affected_contract, historical_validation, out_of_sample_validation, stability_check, approval_status`

### 5.11 `universe_versions`

`universe_version, effective_date, theme_id, ticker, action, reason, evidence_ids, approved_by`

## 6. Dashboard reuse and replacement plan

Reuse:

- actual holdings and confirmed account values;
- benchmark NAV section;
- Google formatting/publish/readback infrastructure;
- separate raw history tabs.

Replace home-page order only after Phase 4:

1. MARKET REGIME
2. 11 THEME MAP
3. PORTFOLIO THESIS AND STATE
4. 3-5 PAIRWISE CHALLENGERS
5. SUPPORT / COUNTER / UNKNOWN / NEXT OBSERVATION
6. ACTUAL / R1 RESEARCH / 0050 / 00631L / CASH / EQUAL-WEIGHT BENCHMARKS

Old scores remain on a research/supporting-metrics tab, not the home-page decision hierarchy.

## 7. Largest data gaps

1. No unified fact store with revision identity and supersession.
2. No semantic event deduplication or canonical event identity.
3. No Claim Graph or standardized source-quality taxonomy.
4. No company-level thesis, causal chain, invalidation and unknown ledger for the 52 formal names.
5. No complete theme-basket/peer-group context series.
6. No market-expectation observation. Target price is too sparse to substitute for expectations.
7. Strict identifiable-institution target coverage remains only 8/52; EPS consensus is incomplete and 4W/12W history is immature.
8. No reliable general-news ingestion and no validated LLM claim-extraction route.
9. Only one current deliberation-history date; no learning sample exists yet.
10. Existing forward outcomes validate weekly score rows by price only, not decisions or causal chains.

## 8. Largest technical risks

- Git-based append operations can conflict when daily, weekly and manual workflows overlap.
- `latest.json` files can hide stale dependencies unless every consumer verifies exact dates or approved carry-forward semantics.
- Semantic event deduplication is difficult without stable entity/event normalization.
- LLM output is nondeterministic; it must never directly write accepted facts.
- Large nested JSON snapshots will become slow and hard to migrate without explicit schema versions.
- A Dashboard-generated recommendation currently depends on several independently dated sources; lineage must be frozen into each Decision Snapshot.
- Current weekly workflow is already long and source-heavy; v1.0 evaluation should use separate bounded jobs instead of extending one monolith.

## 9. Largest model risks

- Narrative overfitting: constructing a persuasive thesis after observing price.
- Confirmation bias: collecting more supporting than contradicting evidence.
- Survivorship and hindsight bias in universe updates.
- Treating multiple media relays as independent confirmation.
- Treating price reaction as proof of causal correctness.
- Regime dependence: rules learned during an AI bull cycle may fail in a different market.
- Self-modification feedback: recent errors could trigger unstable rule changes.
- Excessive state transitions causing the same overtrading that v1.0 is meant to prevent.
- Sparse target/EPS data creating false confidence in names with better coverage.

## 10. Phase 1-6 implementation plan

### Phase 1 — Evidence Foundation

Deliverables:

- canonical schemas and source registry;
- adapters from existing official, catalyst, bottleneck, consensus and target data;
- event fingerprint/dedup and claim records;
- PIT/future-data/lineage validators;
- append-only evidence partitions and migration manifest.

Expected files:

- NEW `r1_v1/schema.py`, `fact_store.py`, `event_store.py`, `claim_store.py`, `source_registry.py`, `evidence_adapters.py`.
- NEW `config/r1_v10_sources.json`, `config/r1_v10_event_taxonomy.json`.
- NEW `data/r1_v1/facts/`, `events/`, `claims/`, `manifests/`.
- Tests for PIT, revision lineage, semantic dedup, source-family independence and replay determinism.

Acceptance:

- every important event resolves to sources and facts;
- ten media relays produce one canonical event;
- zero accepted future-data violations;
- legacy files remain unchanged.

### Phase 2 — Context + Thesis

Deliverables:

- MARKET/THEME/COMPANY/VALUATION/FLOW_POSITIONING context snapshots;
- theme basket and peer comparison;
- 52 company thesis templates with versioned causal chains, invalidation and unknowns;
- evidence-to-edge linkage.

Expected files:

- NEW `context_engine.py`, `theme_baskets.py`, `thesis_store.py`, `causal_chain.py`.
- NEW `config/r1_v10_thesis_contract.json` and company thesis seeds under `data/r1_v1/theses/`.
- REFACTOR adapters from `transition_layer.py`, `industry_state.py`, `bottleneck_evidence.py`.

Acceptance:

- every important conclusion traces to context and causal edges;
- every thesis has invalidation and unknown fields;
- inference is not displayed as confirmed fact.

### Phase 3 — Hypothesis Engine

Deliverables:

- event/anomaly review triggers;
- 2-4 competing hypotheses;
- supporting/counter/missing evidence links;
- previous/new conclusion comparison;
- event horizon and impact scope.

Expected files:

- NEW `hypothesis_engine.py`, `hypothesis_policy.py`, `expectation_layer.py`.
- REFACTOR `context_event_layer.py` and `deliberation_layer.py` into compatibility wrappers.

Acceptance:

- every material judgement has at least one alternative hypothesis and counter-evidence field;
- conclusions cannot be emitted from unlinked narrative text;
- rerunning the same frozen inputs gives identical structured output.

### Phase 4 — Relative Opportunity + Portfolio State

Deliverables:

- holding-versus-challenger comparison across thesis, earnings visibility, expectations, valuation, catalysts, risk and context;
- rotation advantage categories;
- portfolio-state machine and hysteresis;
- separate R1 Research Portfolio ledger.

Expected files:

- NEW `relative_opportunity.py`, `portfolio_state.py`, `hysteresis.py`, `research_portfolio.py`.
- REFACTOR `rotation.py`, `recommendations.py`, `portfolio_policy.py`.
- KEEP v05 score as supporting metric only.

Acceptance:

- every rotation review is a named holding/challenger pair;
- rank movement alone cannot change portfolio state;
- state changes need two independent evidence families or one approved thesis-breaking claim;
- no automated fill or account mutation.

### Phase 5 — Memory + 5/20/60TD Evaluation

Deliverables:

- immutable Decision Snapshots;
- maturity queue by Taiwan trading day;
- price, relative-return and thesis-edge reviews;
- outcome classification and error taxonomy;
- full historical replay from stored evidence IDs.

Expected files:

- NEW `decision_snapshot.py`, `review_queue.py`, `outcome_review.py`, `error_taxonomy.py`.
- REFACTOR `forward_outcomes.py` to retain its price diagnostics but evaluate v1.0 snapshots separately.
- NEW daily snapshot and outcome-review workflow steps or a separate bounded workflow.

Acceptance:

- any historical conclusion can be restored exactly;
- 5/20/60TD reviews run only when due;
- thesis correctness and timing correctness are separate;
- unresolved evidence stays unresolved.

### Phase 6 — Controlled Learning

Deliverables:

- aggregated error patterns;
- versioned MODEL_CHANGE_PROPOSAL only;
- historical/out-of-sample/stability gates;
- human approval record.

Expected files:

- NEW `learning_engine.py`, `proposal_registry.py`, `proposal_validation.py`.
- NEW `data/r1_v1/model_change_proposals/`.

Acceptance:

- no code/config/weight changes occur automatically;
- every proposal cites a sufficient evidence window and error pattern;
- recent 3-5 observations cannot approve a change;
- approved changes create a new R1 version rather than overwrite v1.0 history.

## 11. Migration risks and controls

1. **Two models mixed together** — write v1.0 to `r1_v1` and `data/r1_v1`; legacy v0.x remains read-only input/supporting metrics.
2. **Current Dashboard broken** — do not change the published home page until Phase 4 acceptance; use local/hidden payload validation first.
3. **R1 daily publication failure** — introduce each engine behind optional paths and readiness manifests; current publication remains the fallback.
4. **C6/V4-D contamination** — no imports from v1.0 into C6/V4-D packages or workflows; no shared config mutation.
5. **Historical rewrite** — append-only IDs, schema version, content checksum and migration manifest.
6. **LLM hallucination** — LLM output enters a quarantine claim queue; deterministic validators and evidence IDs are required before acceptance.
7. **Event double counting** — canonical event fingerprint and source-family independence tests.
8. **Overfitting** — freeze v1.0 contracts before outcome-based tuning; proposals require out-of-sample and stability checks.

## 12. Protection of current systems

- No changes to V4-D formal rules, data, Dashboard or workflows.
- No changes to C6 research logic, data, Dashboard or workflows.
- R1 v0.x continues publishing until v1.0 Phase 4 is accepted.
- New stores and modules use the `r1_v1` namespace.
- Every phase includes compatibility tests against current R1 publication.
- Formal flags remain false throughout architecture and shadow stages.
- A separate user approval is required before any Dashboard cutover or active recommendation-policy replacement.

## 13. Final gap statement

### Already completed and reusable

- official daily/weekly acquisition routes;
- PIT timestamps and basic future-data exclusion;
- missing-value NA policy;
- 11-theme starting universe;
- actual portfolio and 00631L comparison accounting;
- source readiness and publication gates;
- append-only weekly/raw histories;
- initial market-wide selloff detection;
- initial competing-hypothesis prototype;
- publish/readback and closure-aware schedules.

### Partially completed

- Evidence Engine;
- Context Engine;
- Hypothesis Engine;
- pairwise rotation comparison;
- historical snapshots;
- forward price outcomes;
- universe version labels;
- benchmark framework.

### Completely missing as v1.0 contracts

- canonical Fact Layer;
- canonical Event/Claim Graph and semantic dedup;
- standardized source-quality registry;
- 52 company Thesis objects and causal-chain edges;
- explicit invalidation/unknown ledgers;
- complete five-level Context Engine;
- Expectation/Price-in layer;
- thesis-driven Relative Opportunity Engine;
- hysteresis-backed Portfolio State machine;
- immutable Decision Snapshot contract;
- thesis-aware 5/20/60TD evaluation;
- Error Taxonomy;
- controlled Learning Engine and MODEL_CHANGE_PROPOSAL registry;
- separate R1 Research Portfolio, 0050, Cash and Candidate Equal Weight ledgers.

## 14. Audit decision

R1 v1.0 should proceed, but Phase 1 must be approved before implementation. The immediate architectural priority is not a smarter Dashboard or another score. It is a canonical, PIT-safe Fact/Event/Claim foundation with semantic deduplication. Without that foundation, later thesis and reasoning output would be polished narrative over inconsistent evidence.

No implementation phase was started by this audit.
