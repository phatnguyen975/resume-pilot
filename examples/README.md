# RenderCV Theme Previews

This flat directory is an optional **gallery for the human**, not RenderCV input or a source of candidate facts. The repository includes all nine official RenderCV v2.8 theme PDFs with their original filenames. Use the source links below to restore missing previews. Theme names do not restrict which professions can use them.

## Add Previews

1. Open any source PDF below (from the **v2.8** release), click **Download raw file** on GitHub, and save the PDF.
2. Move the downloaded PDF directly into `resume-pilot/examples/`, **keeping the original filename exactly as shown below**. Do **not** create a `themes/` subdirectory and do **not** rename `John_Doe_HarvardTheme_CV.pdf` to `harvard.pdf`.
3. Run `python scripts/cv.py themes` to see `ready`, `missing` or `invalid` for each official filename. This command is read-only and works without installing RenderCV.

| Theme ID             | Filename to place in `examples/`          | Official source (v2.8)                                                                                 |
| -------------------- | ----------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| `classic`            | `John_Doe_ClassicTheme_CV.pdf`            | [PDF](https://github.com/rendercv/rendercv/blob/v2.8/examples/John_Doe_ClassicTheme_CV.pdf)            |
| `engineeringresumes` | `John_Doe_EngineeringresumesTheme_CV.pdf` | [PDF](https://github.com/rendercv/rendercv/blob/v2.8/examples/John_Doe_EngineeringresumesTheme_CV.pdf) |
| `engineeringclassic` | `John_Doe_EngineeringclassicTheme_CV.pdf` | [PDF](https://github.com/rendercv/rendercv/blob/v2.8/examples/John_Doe_EngineeringclassicTheme_CV.pdf) |
| `harvard`            | `John_Doe_HarvardTheme_CV.pdf`            | [PDF](https://github.com/rendercv/rendercv/blob/v2.8/examples/John_Doe_HarvardTheme_CV.pdf)            |
| `sb2nov`             | `John_Doe_Sb2novTheme_CV.pdf`             | [PDF](https://github.com/rendercv/rendercv/blob/v2.8/examples/John_Doe_Sb2novTheme_CV.pdf)             |
| `moderncv`           | `John_Doe_ModerncvTheme_CV.pdf`           | [PDF](https://github.com/rendercv/rendercv/blob/v2.8/examples/John_Doe_ModerncvTheme_CV.pdf)           |
| `ink`                | `John_Doe_InkTheme_CV.pdf`                | [PDF](https://github.com/rendercv/rendercv/blob/v2.8/examples/John_Doe_InkTheme_CV.pdf)                |
| `opal`               | `John_Doe_OpalTheme_CV.pdf`               | [PDF](https://github.com/rendercv/rendercv/blob/v2.8/examples/John_Doe_OpalTheme_CV.pdf)               |
| `ember`              | `John_Doe_EmberTheme_CV.pdf`              | [PDF](https://github.com/rendercv/rendercv/blob/v2.8/examples/John_Doe_EmberTheme_CV.pdf)              |

A preview must be a PDF, not a downloaded HTML page. The `themes` command checks basic PDF header/trailer markers and a 12 MB size cap; this is a convenience check, **not** cryptographic verification. Missing previews do not block CV creation or human selection. When a preview is absent, the AI agent shows the source link and waits for your choice; it must not invent a local file or silently download one.

**Source:** [rendercv/rendercv](https://github.com/rendercv/rendercv/tree/v2.8/examples) ([MIT license](https://github.com/rendercv/rendercv/blob/v2.8/LICENSE)).

## Selection and Maintenance

Tell the agent your choice before intake review. The choice is recorded with CV language and target page count in `data/preferences.draft.yaml`, then reviewed and promoted with the profile. Neither a filename nor an example default constitutes human consent. See [the workflow contract](../docs/workflow.md).

Do not edit or fabricate official previews to fill missing entries. Keep local preview PDFs out of milestone commits unless their inclusion is deliberately agreed; do not place personal CVs in this gallery. A theme/version change needs coordinated review of this table, schema enums and CLI behavior.
