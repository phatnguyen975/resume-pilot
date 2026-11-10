---
name: resume-render
description: Create, edit, validate and render professional CV YAML using RenderCV 2.8 in Resume Pilot. Use for RenderCV sections, themes, locale, fields, CLI rendering and PDF/PNG troubleshooting; not for human intake or unverified factual claims.
---

# CV Rendering

This skill is **locally authored from RenderCV v2.8 documentation**, not a wholesale copy of the official RenderCV agent skill. The official full-detail skill is at https://github.com/rendercv/rendercv-skill/tree/main/skills/rendercv. Pin all behavior to RenderCV **2.8**; do not silently substitute another version.

## Project Workflow

1. Read `AGENTS.md`; use **approved** `data/profile.yaml` as the only factual source.
2. Read approved `data/preferences.yaml` for theme, language and page target. During intake use exact original PDF filenames listed by `python scripts/cv.py themes` in `examples/`; never assume a missing preview is available.
3. Read `.agents/skills/resume-tailor/SKILL.md` for choosing content; do not turn inferred notes, example content or JD requirements into real claims.
4. Write RenderCV YAML in `resumes/master_cv.yaml` or `resumes/targeted/<company>_<role>_cv.yaml`.
5. Run `python scripts/cv.py validate --kind resume --input <file>` for preflight.
6. Run `python scripts/cv.py build --input <file>` (the script calls RenderCV and audits PDF).
7. Read `output/<stem>/audit.json`, inspect PNGs and iterate with `resume-audit`.

Use this project-local procedure to render approved CV content with RenderCV.

## Schema Reference

- Official RenderCV v2.8 JSON Schema (all optional fields, IDE completion): https://raw.githubusercontent.com/rendercv/rendercv/refs/tags/v2.8/schema.json
- Official user guide: https://docs.rendercv.com/user_guide/yaml_input_structure/
- Official CLI reference: https://docs.rendercv.com/user_guide/cli_reference/
- Sample: `templates/rendercv.example.yaml` (fictional, **never** user facts).
- Official schema is intentionally NOT copied to `schemas/` — it has thousands of lines and can drift. **RenderCV's Pydantic validation during render is authoritative**.
- Extra entry keys can be silently ignored by RenderCV. Double-check field spellings against the official schema; a successful render alone does not catch all typos.

## YAML Structure

This fictional snippet illustrates entry shapes, not approved candidate facts. Use the approved profile and preferences when creating a real CV.

```yaml
# yaml-language-server: $schema=https://raw.githubusercontent.com/rendercv/rendercv/refs/tags/v2.8/schema.json
cv:
  name: "Full Name"
  headline: "Operations Analyst"
  location: "City, Country"
  email: "person@example.com"
  phone: "+84901234567" # omit if not confirmed; international format
  website: "https://example.com"
  sections:
    summary: ["Confirmed summary paragraph."]
    skills:
      - label: "Analysis tools"
        details: "Spreadsheets, Python"
    experience:
      - company: "Company"
        position: "Operations Analyst"
        start_date: "2024-01"
        end_date: "present"
        highlights: ["Confirmed accomplishment."]
    projects:
      - name: "Project"
        date: "2025-05"
        summary: "Confirmed project context."
        highlights: ["Confirmed contribution."]
    education:
      - institution: "University"
        area: "Business Administration"
        degree: "BS"
        end_date: "2023-06"
design:
  theme: engineeringresumes
locale:
  language: english
settings: {}
```

Project preflight requires a nonempty `cv.name` and nonempty sections; these are project requirements, distinct from the upstream minimum model. Theme is chosen by the HUMAN during intake, stored in approved `data/preferences.yaml`, then passed as `--design.theme` via `cv.py build`; language similarly uses `--locale.language`. The YAML's design and locale fields are example defaults, not human decisions. RenderCV v2.8 supports: `classic`, `engineeringresumes`, `engineeringclassic`, `harvard`, `sb2nov`, `moderncv`, `ink`, `opal`, `ember`. Do not fabricate other built-in theme names. `python scripts/cv.py build --input FILE --theme harvard` is a one-time override, which NEVER modifies preferences. Prefer legible layout and avoid complex graphics for broadly compatible parsing.

The human chooses the CV content language and target page count; do not assume English or one page. Write prose in the requested language and use the matching locale for labels/dates.

Render, compare actual PDF pages to `target_pages`, adjust relevant confirmed content and readable layout, then rebuild and re-audit until the counts match. Never use filler, blank pages or unsupported facts to reach the target. If it cannot be met appropriately, obtain a revised target from the human.

Build enforces the exact page target but does not automatically fit content. For an authorized one-time target use `--max-pages <n>`; standalone audit uses that flag only as an upper bound. Use unique lowercase snake_case stems ending in `_cv.yaml`. Build rejects output collisions with another source and preserves successful output when a new audit fails; inspect failed artifacts under `output/failed/<stem>/attempt_*/`.

## Entry Types

- Experience: `company`, `position` + `summary`, `location`, dates, `highlights`.
- Education: `institution`, `area` + `degree`, dates, location, `highlights`.
- Normal (projects, awards): `name` + `summary`, dates, `highlights`.
- One-line (skills): `label`, `details`.
- Bullet: `bullet`.
- Text: a simple string.
- Publication: `title`, `authors` + `doi`, `journal`, `url`, `date`.
- Numbered: `number`. Reverse-numbered: `reversed_number`.

Common date fields: `date` (free text) OR `start_date` + `end_date` (strict `YYYY`, `YYYY-MM`, `YYYY-MM-DD`; end date can be `present`). Do not combine a free-form `date` with `start_date` and `end_date`. Quote strings that include `:`.

Common social networks include GitHub, GitLab, LinkedIn, Leetcode, StackOverflow. Use any network supported by the pinned schema when relevant to the profession; GitHub and other developer accounts are optional. Only populate confirmed accounts. Don't add phone numbers without a country code.

## Rendering and Review

The repository CLI runs RenderCV 2.8 with explicit PDF/PNG paths and official CLI value overrides, not through a global installation. This preserves the upstream `rendercv new` (starter YAML) → edit YAML → `rendercv render` conceptual workflow: AI interviews the human and generates schema-compatible YAML in place of manual edits. Running `rendercv new` on every CV is NOT required. Avoid setting unreviewed output paths inside CV YAML. Use its defaults unless the user asks for a deliberate change. Each section should use a consistent entry type. Check dates, chronology, overflow, page count, contact links, missing characters, and extracted PDF text. Prefer improving content before shrinking fonts.

Use only the local `.venv` through project commands; do not follow upstream global installation recipes. Build requests PDF/PNG and disables HTML/Markdown. The live docs and upstream skill main can drift; unfamiliar fields need checking against the pinned 2.8 schema and installed CLI. Do not guess publication authors or other metadata absent from confirmed profile content.

For full optional design, typography, locale, and settings fields, consult the pinned upstream schema instead of guessing. Never tell the user that an editable template or all fields are validated merely because the generated PDF exists.
