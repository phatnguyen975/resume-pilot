# Workflow and Data

## Data Sources

| File                          | Meaning                                                       |
| ----------------------------- | ------------------------------------------------------------- |
| `data/profile.draft.yaml`     | Candidate facts under review, not a source for real CV claims |
| `data/preferences.draft.yaml` | Theme, locale and page target awaiting approval               |
| `data/intake-review.yaml`     | Full snapshots, hashes, summary and human decision            |
| `data/profile.yaml`           | Promoted profile; only confirmed content may supply CV claims |
| `data/preferences.yaml`       | Promoted presentation settings, not professional evidence     |
| `resumes/*_cv.yaml`           | Selected and edited content in the RenderCV model             |
| `output/<stem>/`              | PDF, PNG previews and audit.json                              |

Profile and preferences have separate JSON Schemas. Review is checked in code; there is currently no review JSON Schema file. Only `python scripts/cv.py approve` promotes drafts. Never create approved files by copying or editing them directly.

## Verification

- `confirmed`: explicitly confirmed by the human; eligible for CV selection.
- `needs_review`: incomplete or awaiting a decision.
- `inferred`: suggested by an artifact but not human-confirmed.

Candidate identity has an overall status. Each record has a stable `id` and `verification`; each highlight has its own status. **Highlights currently have no independent ID**: refer to the parent ID and highlight position/content. A confirmed highlight inside an unconfirmed record is not eligible.

Record status covers factual fields such as role, dates, summary, tools and description. Separate uncertain claims into individually marked highlights or leave the record unconfirmed. Never hide uncertainty inside a confirmed free-text field. `notes` and `summary_notes` are context, not independently approved CV claims. `target_roles` describes goals, not positions already held.

`evidence` contains source references, such as `human:interview` or related record IDs. The CLI does not verify their truth or all cross-references. Artifacts support the interview; they do not replace human confirmation.

## Profession Coverage

Supported groups: `skills`, `experience`, `projects`, `education`, `certifications`, `awards`, `publications`, `volunteering`, `languages`, `additional`. Omit or leave empty irrelevant groups. Projects, GitHub accounts, quantified achievements and employment history are not universal requirements.

- `skills.category` is free text: occupational skills, methods, tools or transferable skills supported by examples.
- `projects` can represent academic, business, creative or community work. Optional `technologies` records relevant technologies/tools; omit when irrelevant.
- Generic groups, including publications, support `title`, `organization`, `date`, `url`, `description` and `highlights`. Dedicated author, DOI and other specialized metadata fields are not currently modeled. Preserve confirmed details in description/highlights when appropriate; do not add unsupported keys or infer metadata.
- RenderCV section names and ordering depend on the profession, evidence and audience; they need not mirror profile group names.

## Gate 1: Intake Review

1. Complete and validate both drafts. Obtain a theme, content language/locale and page target.
2. Generate review. Present the full snapshots, unresolved items and proposed exclusions. Readable sections are fine, but provide access to all details.
3. Obtain explicit approval of both drafts or corrections. Silence, continued conversation or approval of a single part does not approve the whole review.
4. For corrections edit drafts and run `review --replace`; obtain fresh approval. Do not edit snapshots directly.
5. After approval record `decision: approved`, an accurate reviewer description such as `human via chat`, and the actual ISO-8601 time with timezone. Set `acknowledge_exclusions: true` only after explicit agreement to exclude unresolved information.
6. Run `approve`. Excluded items may remain unconfirmed in the promoted profile for later work; they still cannot enter a CV.

Hashes detect changes after review, not the identity of the approver. The agent must not fabricate approval metadata.

For updates, `begin-update` copies profile/preferences and records baseline hashes. Resume active drafts rather than overwriting them without consent. After a fresh review use `approve --replace`. The current CLI checks baselines, backs up the old profile and archives canonical draft/review files under `data/history/`. Do not claim transaction guarantees for the two approved files or a separate complete backup of every preferences version.

## Presentation and Build

Preferences support nine themes, the locales enumerated in the schema and a target page count from one to four. Example values are not human decisions. New locales outside the schema or changes to the data model require coordinated code and test changes.

Build passes approved theme/locale as RenderCV CLI overrides without editing source YAML. The agent writes the prose in the requested language; locale handles labels and dates. `target_pages` specifies the human-approved page count for the delivered PDF.

The agent must compare the rendered count with this target, select and edit relevant confirmed content, adjust readable typography/spacing and rebuild. Repeat factual, structural and visual checks after changes until the count matches. Do not fill pages with invented content, repetition or blank pages, or compress text into an unreadable layout. If the target is unsuitable for the available evidence, explain why and obtain a revised target before delivery.

Current CLI checks reject excessive pages but do not reject fewer pages or automatically fit content. The agent must explicitly check equality between the PDF page count and `target_pages`; a passing CLI report alone does not establish compliance.

A human-authorized one-time page target replaces the stored target only for that CV. The CLI's `--max-pages` flag supplies its upper-bound check; the agent must still check the actual count against the agreed target. Persistent target changes use the dual-draft review gate. A one-time override does not edit preferences.

| Check layer | Scope                                                                                                            |
| ----------- | ---------------------------------------------------------------------------------------------------------------- |
| Automated   | YAML preflight, real render, page count, text statistics, link count and presence of PNG output                  |
| Agent       | Claim traceability, full extracted text, every preview, exact page-target match, link destinations and relevance |
| Human       | PDF and unresolved issues before final approval                                                                  |

`audit.json` stores statistics/warnings and the build's theme/locale, **not full extracted text**. Read text with a local PDF tool or pypdf in `.venv`; do not upload it elsewhere without authorization.

Use unique YAML stems: builds share an output directory when stems match even across subdirectories. On build failure inspect diagnostics and artifacts; old output is not proof of a successful new build.

## Gate 2: PDF Review

Present the PDF, requested and actual page counts, findings and incomplete checks. Resolve any page-count mismatch before requesting final approval. Until the human explicitly approves, label it **ready for human review**. Any later edit needs a fresh render, audit and approval. Approval does not authorize job submission. No automated check guarantees ATS acceptance, truthfulness or visual quality.
