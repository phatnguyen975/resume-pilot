# Maintenance

## Documentation

| Location              | Owns                                                           |
| --------------------- | -------------------------------------------------------------- |
| `README.md`           | User setup, prompt templates and CLI overview                  |
| `AGENTS.md`           | Shared agent invariants, routing and human gates               |
| `CLAUDE.md`           | Imports shared instructions and points to the canonical skills |
| `.agents/skills/`     | Procedures for individual workflow stages                      |
| `docs/workflow.md`    | Data semantics and implementation limits                       |
| `docs/maintaining.md` | Contribution, validation and commit conventions                |
| `examples/README.md`  | Optional official preview gallery                              |

Write repository-maintained prose, comments and sample prompts in **English**. Use short Markdown headings in **Title Case**. Preserve official capitalization for names and acronyms such as RenderCV, YAML, CV and CLI. Do not rename schema keys or RenderCV section identifiers merely to change heading style.

Use lowercase `snake_case` for generated CV filenames, such as `master_cv.yaml` and `<company>_<role>_cv.yaml`. Use underscores within company and role names as well, for example `acme_business_analyst_cv.yaml`. Preserve original filenames of official theme PDFs and conventional configuration/dependency filenames. Skill directories retain their hyphenated names to match skill identifiers.

Prompt templates use descriptive `{{variable}}` placeholders. This convention does not constrain the human's conversation language or the language of a generated private CV. External product identifiers and locale names retain their official spelling.

Keep shared rules in one authoritative location and link to it. A shortened reminder in a skill is appropriate when omitting it would enable a factual or approval mistake. Do not duplicate whole manuals or add files without a purpose.

## Change Workflow

For each coherent change:

1. Inspect the working tree and define the files in scope.
2. Complete the change and appropriate validation; report checks not performed.
3. Present a concrete reviewable result. If the human requested sign-off before committing, wait for it; do not infer sign-off from unrelated messages.
4. Stage explicit paths, inspect the staged diff and verify that private data, generated output and unrelated edits are absent.
5. Commit one coherent change with the convention below, then push to the agreed remote/branch when authorized. Report the commit hash and push outcome.

Repository change approval is separate from candidate intake/PDF approval. Do not run the candidate approval workflow for repository maintenance.

Inspect tracked and untracked files before staging. Include only files belonging to the change, preserve unrelated work and distinguish verified behavior from assumptions. Do not create extra approval gates for routine reversible work; honor the review and publishing boundaries agreed with the maintainer.

## Commit Format

Follow [Conventional Commits 1.0.0](https://www.conventionalcommits.org/en/v1.0.0/):

```text
<type>(<scope>): <imperative summary>

<Problem or reason for the change.>

<What changed and any material limits or follow-up work.>

Validation: <checks actually performed and relevant checks deferred>

<optional footer>
```

Repository conventions, beyond the specification:

- Use English. Keep the header around 72 characters or fewer, no final period.
- Use a specific imperative summary, such as "generalize", "preserve" or "fix".
- Scope is optional; use meaningful areas such as `workflow`, `skills`, `schema`, `cli` or `ci`.
- Include a body for substantive commits. Explain why and observable behavior; avoid narrating every edit or claiming tests passed without running them.
- Wrap ordinary body text around 72 characters when practical; preserve links and commands. Separate header, body and footers with blank lines.
- Use `!` or a `BREAKING CHANGE:` footer for an actual incompatible change. Describe the migration. Do not label ordinary wording changes as breaking.
- Issue references and trailers are optional and must be accurate.

| Type       | Use                                                     |
| ---------- | ------------------------------------------------------- |
| `docs`     | Guidance, examples or nonfunctional schema descriptions |
| `feat`     | New user-visible capability                             |
| `fix`      | Correct an observable defect                            |
| `refactor` | Internal restructuring without intended behavior change |
| `test`     | Test additions or corrections                           |
| `ci`       | CI configuration                                        |
| `build`    | Dependency or build-system changes                      |
| `chore`    | Maintenance that does not fit the categories above      |

A schema validation rule change is functional: use `feat` or `fix` as appropriate, with coordinated code/tests. Do not hide it under a documentation-only commit.

Example commit message:

```text
docs(workflow): clarify presentation review

Presentation choices need to be visible alongside candidate facts.

Explain how the human reviews theme, language and page count before
promotion. Keep the existing approval behavior unchanged.

Validation: checked local links and consistency with the CLI contract.
```

Adapt the validation line to actual results; this is an example, not a test report.

When using a CLI to submit a multiline commit/PR description, prefer an exact UTF-8 text file and the CLI's file argument to preserve newlines and literal text. Do not force-push, rewrite shared history or amend a published commit unless asked. Use a follow-up commit for later corrections.

## Validation

Choose checks based on the behavior and contracts affected by a change. Documentation must distinguish intended workflow requirements from guarantees actually enforced by code. Do not describe a documentation edit as an implemented CLI capability.

| Change                  | Relevant Checks                                                                                      |
| ----------------------- | ---------------------------------------------------------------------------------------------------- |
| Documentation           | Local links, command examples, naming, heading style and consistency with the data/workflow contract |
| Skills                  | Frontmatter, names, paths, routing and realistic behavior around confirmation and human decisions    |
| Schemas or templates    | JSON/YAML syntax, schema validity, example validation and affected readers/writers                   |
| Scripts or dependencies | Lint, formatting, type checks, relevant tests and real rendering when affected                       |
| Rendering or layout     | Actual PDF page count, extracted text, links, every preview page and factual support                 |
| CI or setup             | Affected commands and platform assumptions; report platforms not exercised                           |

Use the project-local development environment:

```bash
python scripts/bootstrap.py --dev
python scripts/dev.py check
```

Run checks appropriate to the change and record actual results, failures and omissions. Mocked tests do not establish real RenderCV or platform compatibility. Use fictional candidate data for tests and render checks; keep personal data out of fixtures and shared reports.

## Contract Changes

Coordinate schema, CLI, skill, template and documentation changes when a shared contract changes. Nonfunctional schema descriptions must not silently alter validation rules.

- Preserve the distinction between confirmed facts and presentation preferences, both human approval gates and the exclusion of unconfirmed claims.
- For profile/preferences changes, consider existing drafts, review hashes, approved data and update/backup behavior. Document migration steps for incompatible formats.
- For rendering changes, verify unique output paths, artifact freshness, preview coverage and the approved page target, including PDFs with too few or too many pages.
- For dependency upgrades, review the pinned version, supported fields, theme/locale values, CLI flags and example compatibility together. Install only in `.venv`.
- Describe known limitations with their affected behavior and verification needs. Keep task-specific progress, investigation lists and temporary repository state in review discussions or issue tracking rather than permanent maintenance guidance.
