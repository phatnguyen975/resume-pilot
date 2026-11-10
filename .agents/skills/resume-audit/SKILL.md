---
name: resume-audit
description: Audit a finished RenderCV CV across professions for factual support, relevance, PDF extractability, contact links, visual clipping, readability and human sign-off. Use after every render or meaningful CV edit and before calling a resume final.
---

# CV Audit

## Structural Checks

- `python scripts/cv.py validate --kind resume --input resumes/<name>_cv.yaml`. This is **basic YAML preflight**, not complete RenderCV schema validation.
- `python scripts/cv.py build --input resumes/<name>_cv.yaml` calls the real RenderCV 2.8 engine (authoritative validation) and writes PDF, PNG and `output/<stem>/audit.json`.
- `python scripts/cv.py audit --pdf output/<stem>/resume.pdf` checks pages, extractable text and counts link annotations. Standalone audit defaults to two pages without loading preferences; pass `--max-pages <limit>` explicitly. **A passing report is not an ATS score** and cannot guarantee reliable parsing in every ATS.

## Factual and Visual Checks

1. Check `output/<stem>/audit.json` records the approved theme/language from `data/preferences.yaml` (or an explicit one-time theme override). The preview must look like the selected style. Never switch themes without user approval.
2. Compare every identity detail, role, date, skill, credential, publication, bullet, measurement and link against approved **confirmed** `data/profile.yaml` facts. Flag unsupported assertions. Unconfirmed notes and draft fields are not sources.
3. Inspect **all** output PNG pages, not only the first: clipped/overlapping characters, visual margins, insufficient whitespace, bad page breaks, unreadable body size, misaligned dates, broken special/Vietnamese glyphs.
4. Extract and read PDF text with a local PDF tool or pypdf in `.venv`. The audit report contains statistics, not full text. Confirm section order, name/contact, legibility and that no important text is dropped.
5. Check any links in CV actually refer to the confirmed accounts/projects. The structural script only counts annotations; it cannot prove destinations.
6. Evaluate relevance to the JD without keyword stuffing or unjustified claims. Prioritize evidence appropriate to the profession and career stage; projects are optional, and missing experience must never be invented.
7. Reword/reorder or adjust typography where needed, then **rebuild and re-audit**. Do not sacrifice readable font size merely to force one page. If needed, request a revised preference or authorized one-time page override instead of silently delivering a page count different from the approved target.

## Page Target

Compare the actual PDF page count to approved `target_pages` or a human-authorized one-time target. Build rejects both fewer and more pages and checks preview count and basic PNG headers. Standalone audit checks only its upper bound. A passing build still requires factual and visual review; a correct count does not establish readable layout.

Revise relevant confirmed content and readable layout, rebuild and repeat the audit until the counts match. Do not add filler, blank pages or invented claims, or sacrifice readability. If the target is unsuitable, obtain a revised target before requesting final approval. Report requested and actual counts together.

## Human Approval

If text or image tools are unavailable, disclose the incomplete checks. Ensure artifacts match the latest build; an old PDF does not prove new build success.

Show the PDF and a concise summary of confirmed findings, caveats and open items. Ask the human to review the final result. Without explicit confirmation, report `ready for human review`, not `approved/final`. Do not send/apply anywhere on behalf of the user unless separately requested and authorized. Any later CV edit requires a fresh render, audit and final human review.
