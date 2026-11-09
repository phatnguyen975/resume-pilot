# Resume Pilot

An AI-assisted workflow for creating and updating truthful, readable CVs across professions, using **RenderCV 2.8** to produce PDFs. The human confirms facts, chooses presentation preferences and approves the result; the agent interviews, edits and checks the CV.

This repository contains reusable tools, rules, schemas and fictional examples. Real profiles, job descriptions and generated CVs are created during use and Git-ignored.

## Get Started

**Requirements:** Python **3.12+** with `venv`, `ensurepip` and `pip`; internet access for dependency installation; and a coding agent that can read files, run commands and inspect images.

Use `python` on Windows, Linux and macOS. Check that `python --version` selects a supported version. If Linux lacks `venv` or `ensurepip`, install the appropriate Python support package through your operating system's package manager first.

```bash
git clone https://github.com/phatnguyen975/resume-pilot.git
cd resume-pilot
python scripts/bootstrap.py
python scripts/cv.py doctor
```

Bootstrap creates `.venv`, installs pinned direct dependencies and smoke-renders a fictional CV inside `.venv/`. Subsequent runs check the environment and skip installation when satisfied. CLI commands select the local environment without manual activation. Transitive dependencies are resolved by `pip`, not fully locked.

Open your agent at the repository root and use a prompt below. The agent follows `AGENTS.md` and reads the relevant procedures in `.agents/skills/` as needed.

## Prompt Templates

Replace every `{{variable}}` before sending. These are prompt placeholders, not YAML or CLI syntax. Write "unknown" for missing information and "none" for absent documents. Conversation language and CV content language can differ.

### Create a CV

```text
Read AGENTS.md and the relevant skills in .agents/skills/ in this repository.
Help me create a CV for {{profession}}, targeting {{target_role}} at
{{career_stage}}, for applications in {{application_market}}.
Talk to me in {{conversation_language}} and write the CV in {{cv_language}}.
The PDF should contain {{target_pages}} pages.
Information I already have: {{existing_information}}.
Documents you may read for this task: {{authorized_files_or_links}}.
Ask short batches of questions relevant to my background and profession.
Let me choose a theme and review all facts and presentation preferences before
creating the CV. After rendering, check the facts, PDF text and every preview
page, then send me the PDF for final review.
```

### Update a CV

```text
Read AGENTS.md and follow the existing-profile update workflow.
Changes to collect or correct: {{changes}}.
Documents you may read: {{authorized_files_or_links}}.
Presentation preferences: {{keep_or_change_theme_language_target_pages}}.
CVs to regenerate: {{cv_files}}.
Ask only about missing details. Let me review the updated facts and preferences
before replacing approved data, then render, audit and send me the PDFs to review.
```

### Tailor a CV

```text
Read AGENTS.md and use my approved profile to create a separate CV for
{{organization}}, targeting {{role}}.
Job description: {{job_description_or_path}}.
CV language: {{cv_language}}. Required page count: {{target_pages}}.
Identify supported matches and gaps, then select relevant confirmed facts.
Route new facts or persistent preference changes through review first.
Do not add skills simply because the job description requests them.
Render, audit and send me the PDF for final review.
```

## Workflow

```text
Human information + authorized supporting documents
  → Agent interview → profile.draft.yaml + preferences.draft.yaml
  → Validation → intake-review.yaml
  → HUMAN GATE #1: full facts, exclusions and presentation preferences
  → CLI approve → profile.yaml + preferences.yaml
  → Agent selects confirmed facts → RenderCV YAML
  → PDF + PNG build → structural checks + factual and visual agent review
  → HUMAN GATE #2: PDF approval before calling the CV final
```

| Participant | Responsibility                                                                                             |
| ----------- | ---------------------------------------------------------------------------------------------------------- |
| Human       | Confirm facts, choose presentation and approve the result                                                  |
| Agent       | Interview, organize evidence, edit content and inspect all output                                          |
| Project CLI | Validate structure, check review hashes and approval conditions, invoke RenderCV and inspect PDF structure |
| RenderCV    | Validate its input model and typeset documents; it does not verify career claims                           |

Only `confirmed` records and highlights may appear in a CV. An approved profile can retain unresolved items when the human agrees to exclude them. See the [workflow and data contract](docs/workflow.md).

Run `python scripts/cv.py themes` to see nine themes. Theme names do not restrict their use to particular professions. Official PDF previews are included in `examples/`; see [examples/README.md](examples/README.md) for source links and instructions to restore missing files. Missing previews do not block creation. The agent must obtain a theme choice, not assume a default.

`target_pages` is the human-approved page count for the delivered PDF. The agent selects relevant confirmed content, adjusts the layout and repeats rendering and review until the PDF matches that count and remains readable. Do not add filler or unsupported claims to fill pages. If the requested count cannot be met responsibly, explain the issue and obtain a revised target before delivery.

The delivered CV must also use the requested language for both prose and locale-dependent labels and dates.

## CLI Reference

Run from the repository root. Real CV commands require the bootstrapped environment.

| Command                                                                                | Purpose                                                                |
| -------------------------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| `python scripts/cv.py doctor`                                                          | Inspect the runtime environment                                        |
| `python scripts/cv.py themes`                                                          | List themes, exact PDF paths and preview status; no bootstrap required |
| `python scripts/cv.py begin-update`                                                    | Draft the approved profile and preferences for an update               |
| `python scripts/cv.py validate --kind profile --input data/profile.draft.yaml`         | Validate candidate facts                                               |
| `python scripts/cv.py validate --kind preferences --input data/preferences.draft.yaml` | Validate presentation preferences                                      |
| `python scripts/cv.py review`                                                          | Generate the review with both snapshots                                |
| `python scripts/cv.py review --replace`                                                | Regenerate after draft changes; obtain fresh human approval            |
| `python scripts/cv.py approve`                                                         | Promote drafts after explicit human approval                           |
| `python scripts/cv.py approve --replace`                                               | Replace approved data after a new review                               |
| `python scripts/cv.py validate --kind resume --input resumes/master_cv.yaml`           | Basic YAML preflight, not full RenderCV validation                     |
| `python scripts/cv.py build --input resumes/master_cv.yaml`                            | Render with approved preferences and inspect PDF structure             |
| `python scripts/cv.py audit --pdf output/master_cv/resume.pdf --max-pages 1`           | Inspect PDF structure with an explicit page upper bound                |
| `python scripts/cv.py build --example --input templates/rendercv.example.yaml`         | Render the fictional example without approved candidate data           |

Build accepts `--theme harvard` and `--max-pages 2` as one-time overrides. Agents use them only when requested or approved; they do not update preferences. Standalone audit defaults to an upper bound of two pages, so pass the agreed target explicitly. The agent must also verify that the actual page count equals the target; this flag alone does not establish an exact match.

Output is currently keyed by the YAML **file stem**, including targeted CVs: `resumes/targeted/<company>_<role>_cv.yaml` produces `output/<company>_<role>_cv/`. Use unique stems to prevent collisions.

## Repository Map

| Path                                    | Purpose                                                              |
| --------------------------------------- | -------------------------------------------------------------------- |
| `AGENTS.md`                             | Shared agent rules and workflow routing                              |
| `CLAUDE.md`                             | Imports shared instructions and points to the canonical skills       |
| `.agents/skills/`                       | `resume-intake`, `resume-tailor`, `resume-render` and `resume-audit` |
| `docs/`                                 | Workflow, data contract and maintenance conventions                  |
| `schemas/`                              | Profile and preferences JSON Schemas                                 |
| `templates/`                            | Fictional YAML format examples                                       |
| `examples/`                             | Official theme PDF previews and source links                         |
| `scripts/`                              | Bootstrap, workflow CLI and development checks                       |
| `tests/`, `.github/workflows/ci.yml`    | Tests and Linux/Windows CI                                           |
| `data/`, `resumes/`, `jobs/`, `output/` | Private runtime data, Git-ignored                                    |

## Maintenance

- Keep personal data out of commits and external services unless authorized. Git-ignore does not prevent manual sharing; submitted content is also subject to the agent provider's data policy.
- Automated PDF checks do not prove facts, visual quality or ATS acceptance. The agent must inspect every PNG and disclose checks it could not perform.
- Profile YAML and RenderCV YAML serve different purposes. Schemas validate structure, not truthfulness.
- Install only in `.venv`; do not automatically upgrade pinned dependencies.
- See [maintenance](docs/maintaining.md) for contribution, validation and commit conventions.

For code maintenance:

```bash
python scripts/bootstrap.py --dev
python scripts/dev.py check
```

## References

- [RenderCV 2.8](https://pypi.org/project/rendercv/2.8/) and [schema.json](https://raw.githubusercontent.com/rendercv/rendercv/refs/tags/v2.8/schema.json).
- [Upstream RenderCV Skill](https://github.com/rendercv/rendercv-skill/tree/main/skills/rendercv): reference material; the local `resume-render` skill is independently adapted.
- [RenderCV CLI Guide](https://docs.rendercv.com/user_guide/cli_reference/): live documentation may change; project behavior must match 2.8.
