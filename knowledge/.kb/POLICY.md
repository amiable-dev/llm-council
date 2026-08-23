# Lint policy

Normative. Every generated harness adapter cites this file.

This exists because of a real incident in the predecessor vault on 2026-07-26: a scheduled audit rewrote wikilinks **inside code spans** and deleted links to pages that should exist, corrupting two concept notes and destroying the only record of three concept gaps. Bulk tag rewriting and bulk relinking are the highest-blast-radius operations in this pipeline, and they are exactly what caused that damage.

## An automated pass MAY, unattended

- Regenerate `concepts/_index.md`
- Append to the proposal queue under `.kb/queue/`
- Add a generated frontmatter field that the pipeline owns (facet scalars and their mirrored nested tags, card IDs)

## An automated pass MUST NOT, ever

- **Delete or rewrite any wikilink**, resolved or not. An unresolved link is recorded as a gap with the link left in place.
- **Modify any text inside inline code spans or fenced code blocks.** No exceptions. Illustrative markup in prose is not markup to act on.
- Edit prose in any section
- Change a frontmatter value the pipeline does not own
- Delete any file

Anything not on the first list is **report-only**. Findings become proposed edits for review, not applied edits.

## Mechanical consequences

- `kb link --apply` and any bulk facet operation default to dry-run and emit a reviewable patch.
- `--apply` requires a clean `kb verify` and a git-clean working tree.
- A novel facet value does not fail a write. It is recorded as a proposal and the note proceeds; `kb verify` fails only on proposals left unreviewed past their ageing threshold. Blocking causes agents to pick a wrong-but-permitted value to get past the gate; auto-fixing destroys the judgment that produced it.
