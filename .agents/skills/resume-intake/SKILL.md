---
name: resume-intake
description: Collect or update candidate facts across professions through a contextual interview, record evidence and uncertainty, and obtain explicit human approval of facts and presentation preferences.
---

# Candidate Intake

Follow the shared rules in `AGENTS.md`. Read `references/interview_guide.md` only when choosing follow-up questions. Read `templates/profile.example.yaml`, `templates/preferences.example.yaml`, and both JSON schemas for field shapes and allowed values. Do not treat the example as user data.

## New Profile

1. Check `data/profile.yaml` and `data/profile.draft.yaml` (these may be absent). If either draft exists, **resume it**; do not reset it or copy an example over it.
2. Ask small, conversational batches: basic contact/target role; relevant experience and personal contribution; education; occupational/transferable skills; optional achievements. Ask a single follow-up when a critical detail is missing. Adapt to occupation, career stage, application market and available evidence; do not require projects, employment history or a technical portfolio.
3. Inspect only authorized work samples, documents or portfolios as evidence. Artifacts and team results do not prove individual authorship, responsibility or measured impact. Confirm the human's contribution. For technical work, distinguish tools personally used from those merely present in dependencies.
4. **Choose a theme during intake.** Run `python scripts/cv.py themes`. Tell the human all nine theme IDs, each exact upstream PDF filename in `examples/`, and whether the local preview exists. Do not claim a missing file is available. If previews are missing, give the official v2.8 download links from `examples/README.md`; the human may download and move them into `examples/` unchanged. Do not initiate a download. Suggest suitable themes, then ask the human to select one. Do not assume a theme without consent. Save `data/preferences.draft.yaml` with their selected theme, language and target page count; see the template. Do not confuse presentation preferences with evidence of professional skills or experience.
5. Create/update `data/profile.draft.yaml` following the profile schema. Each record needs a stable `id` and `verification`; each highlight needs its own verification. Highlights currently have no independent ID field. Record evidence references where possible. Use `confirmed` only for facts explicitly confirmed by the human; `inferred` and `needs_review` must never enter the real CV.
6. Record unanswered questions under `open_questions`. Do not invent data to satisfy schema; optional groups can be omitted or empty.
7. Validate BOTH draft files: `python scripts/cv.py validate --kind profile --input data/profile.draft.yaml` and `python scripts/cv.py validate --kind preferences --input data/preferences.draft.yaml`. Correct errors, then run `python scripts/cv.py review`.

## Human Approval

`data/intake-review.yaml` contains SHA-256 hashes of BOTH drafts, summary, unresolved paths, open questions, the **full profile_snapshot**, and **preferences_snapshot** with theme, language and page target. Present it and explain what is inferred/unknown. Ask for factual corrections or **explicit approval**.

- If corrected: update the corresponding DRAFT, run `review --replace`, request review again.
- Any change to either draft after review invalidates that approval; regenerate review and obtain a fresh decision, including language or page-target changes.
- If approved in plain terms: ONLY THEN set `decision: approved`, record reviewer (e.g. `human via chat`) and the actual ISO-8601 timestamp with timezone. Never invent a human decision.
- If unresolved records/questions remain, specifically ask whether to exclude them from the CV; only after agreement set `acknowledge_exclusions: true`.
- Execute `python scripts/cv.py approve` (or `approve --replace` for update).
- If script detects a stale review, edited snapshot, changed baseline or a missing approval, **STOP** and resolve it with the human. Do not bypass checks.

## Profile Updates

Run `python scripts/cv.py begin-update` (only if no in-progress draft). It copies approved facts AND preferences and records both baseline hashes. Ask about _new or changed_ facts, preserve stable IDs, and follow the same review gate before `approve --replace`. Never silently remove older achievements, achievements used in targeted CVs, or confirmed provenance. The CLI backs up the prior approved file on replacement.

See `docs/workflow.md` for record-level confirmation semantics and data limits. Do not assume English or a one-page CV: ask for content language and page target. Confirm the requested PDF page count and record it as `target_pages`. It is a delivery requirement, not merely an upper bound. If the human is unsure, suggest a suitable count based on relevant evidence and obtain their choice. A persistent preferences-only change uses the same dual-draft review gate.

After the gate, hand off to `resume-tailor` and `resume-render`, then `resume-audit`.
