# Web Failure Research

Use this workflow only when embedded and verified local rules do not explain the
first causal error.

## Research sequence

1. Preserve the complete local log and isolate the first causal message.
2. Call `prepare_failure_research` with the application, stage, and focused error text.
3. Search the returned official-documentation queries first.
4. Extract only directly relevant evidence:
   - page title and URL;
   - product and version;
   - a short explanatory passage;
   - a paraphrased cause;
   - bounded recovery actions stated or supported by the source.
5. Search official vendor communities only when documentation is insufficient.
6. Use independent forums or blogs only as hypotheses and label them accordingly.
7. Call `evaluate_failure_research` with all candidates.
8. Reproduce the failure on a preserved artifact and test one bounded action.
9. Rerun the smallest valid gate, such as rebuild, Model Checker, mesh check,
   Abaqus datacheck, or a short solver job.
10. Preview `record_verified_failure_rule`; commit only after checking the sources,
    action, approval boundary, and before/after evidence.

## Source hierarchy

1. Official product documentation, API references, release notes, and knowledge base.
2. Official vendor community posts from staff or verified experts.
3. Peer-reviewed technical literature where applicable.
4. Independent forums, blogs, and videos.

Prefer information matching the installed product release. When only an older or
newer release is available, record the version mismatch explicitly.

## Evidence rules

- Store URLs, titles, product versions, and short excerpts; do not copy whole pages.
- Keep source claims separate from locally observed facts.
- A plausible explanation is not a verified recovery.
- Require local before/after evidence before promotion.
- Mark solutions that alter geometry, material, contact, loads, constraints,
  stabilization, or solver formulation as approval-required.
- Do not bypass authentication, paywalls, robots controls, or licensing restrictions.

## Updating knowledge

`evaluate_failure_research` creates `candidate-unverified` knowledge. It must not
be loaded as an active diagnostic rule.

`record_verified_failure_rule` changes it to `verified` and appends it to a local
JSON registry with an idempotency key. Pass that registry through
`diagnose_cae_failure.knowledge_paths` to reuse the learned rule.
