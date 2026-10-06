# Phase 1 - Source Index

Status values: `pending`, `in-progress`, `needs-second-pass`, `completed`

One round = one source, processed by all three agents (Erendiz, Wilson, Tyler). Each round has two passes:
1. Independent pass: each agent writes its own file without seeing the others
2. Shared pass: each agent reads the others' independent files and leaves a short reaction/objection on the issue

A source can take more than one round; the agents decide this themselves (`needs-second-pass`).

**Synthesis**: `synthesis.py` is run by hand. Each agent goes back only to its own files for completed sources and appends a new round to `synthesis/{agent}.md`.

This public repo keeps six public-domain sources as examples. The table is updated by `pass1.py` and `pass2.py`; a source that is not listed gets a new row automatically.

| # | Source | Category | Status | Rounds | Issue |
|---|--------|----------|--------|--------|-------|
| 1 | Homer Odyssey | Mythology / Greek | completed | 2 | #1 |
| 2 | Kalevala | Mythology / Finnish | completed | 2 | #2 |
| 3 | The Poetic Edda | Mythology / Norse | completed | 3 | #3 |
| 4 | The Mabinogion | Mythology / Welsh | completed | 2 | #4 |
| 5 | Turkish fairy tales and folk tales | Mythology / Folk tales | completed | 2 | #5 |
| 6 | The Castle of Otranto | Literature / Novel | completed | 2 | #6 |
<!--
Row format for a new source:
| 7 | Source name | Category | pending | 0 | #7 |
-->
