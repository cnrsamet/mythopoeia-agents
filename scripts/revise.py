import os
import re
import sys
from pathlib import Path

from agents import new_log_file, log, run_codex, find_decision, clean_temp_files, style_contract_path
from config import REPO_PATH, WORLD_NAME, STORY_NAME

CRITERIA_FILE = "phase3-fiction/REJECTION_CRITERIA.md"
PASS_TIMEOUT = 2700
QUOTES = "“”„\"'«»"


def story_folder() -> str:
    return f"phase3-fiction/stories/{STORY_NAME}"


def source_chapter_path(chapter: str) -> str:
    return f"{story_folder()}/chapters/{chapter}.md"


def revision_folder() -> str:
    return f"{story_folder()}/revision"


def protect_original(path: Path, expected: str, log_file) -> bool:
    if not path.exists():
        path.write_text(expected, encoding="utf-8")
        log(f"WARNING: source file was deleted, restored: {path.name}", log_file)
        return False
    if path.read_text(encoding="utf-8") != expected:
        path.write_text(expected, encoding="utf-8")
        log(f"WARNING: source file was CHANGED, original content written back: {path.name}", log_file)
        return False
    return True


def _paragraphs(text: str) -> list[str]:
    blocks = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    return [p for p in blocks if not p.lstrip().startswith("#")]


def _sentences(paragraph: str) -> list[str]:
    one_line = " ".join(paragraph.split())
    return [s for s in re.split(r"(?<=[.!?…])\s+", one_line) if s.strip()]


def _is_dialogue(paragraph: str) -> bool:
    return paragraph.lstrip()[:1] in QUOTES


def _lines_of_speech(paragraph: str) -> list[str]:
    return re.findall(r"[“\"]([^”\"]+)[”\"]", paragraph)


def measure(text: str) -> dict:
    paragraphs = _paragraphs(text)
    if not paragraphs:
        return {}

    word_counts = [len(p.split()) for p in paragraphs]
    sentence_counts = [len(_sentences(p)) for p in paragraphs]

    single_sentence = sum(1 for c in sentence_counts if c <= 1)
    long_development = sum(
        1 for p, w in zip(paragraphs, word_counts)
        if w >= 150 and not _is_dialogue(p)
    )

    aphorism = 0
    for p, c in zip(paragraphs, sentence_counts):
        if _is_dialogue(p) or c < 2:
            continue
        if len(_sentences(p)[-1].split()) <= 8:
            aphorism += 1

    longest_chain = 0
    chain = 0
    for p, c in zip(paragraphs, sentence_counts):
        if _is_dialogue(p) and c <= 2:
            chain += 1
            longest_chain = max(longest_chain, chain)
        else:
            chain = 0

    longest_line = 0
    for p in paragraphs:
        for line in _lines_of_speech(p):
            longest_line = max(longest_line, len(line.split()))

    return {
        "words": len(text.split()),
        "paragraphs": len(paragraphs),
        "avg_words_per_paragraph": round(sum(word_counts) / len(paragraphs), 1),
        "avg_sentences_per_paragraph": round(sum(sentence_counts) / len(paragraphs), 1),
        "single_sentence_paragraphs": single_sentence,
        "single_sentence_ratio": round(100 * single_sentence / len(paragraphs)),
        "longest_paragraph": max(word_counts),
        "long_development_150": long_development,
        "aphorism_endings": aphorism,
        "longest_short_line_chain": longest_chain,
        "longest_single_line": longest_line,
    }


MEASURE_ROWS = [
    ("words", "Total words", ""),
    ("paragraphs", "Paragraphs", ""),
    ("avg_words_per_paragraph", "Average words / paragraph", "should be high"),
    ("avg_sentences_per_paragraph", "Average sentences / paragraph", "should be high"),
    ("single_sentence_paragraphs", "Single-sentence paragraphs", "A1: at most 2"),
    ("single_sentence_ratio", "Single-sentence paragraph ratio (%)", "should be low"),
    ("longest_paragraph", "Longest paragraph (words)", ""),
    ("long_development_150", "Unbroken development of 150+ words", "A2: at least 3"),
    ("aphorism_endings", "Aphorism-like paragraph endings", "B1: at most 2"),
    ("longest_short_line_chain", "Longest chain of short dialogue lines", "A3: at most 2"),
    ("longest_single_line", "Longest single line of dialogue (words)", "A4: should be 50+"),
]


def write_measure_table(versions: list[tuple[str, Path]], target: Path, log_file) -> str:
    results = []
    for label, path in versions:
        if not path.exists():
            continue
        results.append((label, measure(path.read_text(encoding="utf-8"))))

    if not results:
        return ""

    headers = " | ".join(label for label, _ in results)
    lines = [
        "# Revision Experiment - Measurements",
        "",
        f"Story: `{STORY_NAME}` (world: {WORLD_NAME})",
        "",
        "These numbers turn the A and B items of `phase3-fiction/REJECTION_CRITERIA.md`",
        "into counts. They do not replace a reader's judgment, they give it a",
        "floor: did the passes really change how the text is built, or only the words?",
        "",
        f"| Metric | {headers} | Target |",
        f"|---|{'---|' * len(results)}---|",
    ]
    for key, name, target_note in MEASURE_ROWS:
        values = " | ".join(str(r.get(key, "-")) for _, r in results)
        lines.append(f"| {name} | {values} | {target_note} |")

    text = "\n".join(lines) + "\n"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    log(f"Measurement table written: {target.relative_to(REPO_PATH)}", log_file)
    return text


def _shared_rules(source: str, output_list: str) -> str:
    return f"""
DO NOT TOUCH (this is an EXPERIMENT run, not a production run):
- ONLY READ `{source}`. Do not overwrite, edit or delete it. The first
  version is kept for comparison. The script checks this file after
  every pass.
- DO NOT TOUCH `story_state.json`, `canon.json`, `writer-brain.md`,
  `architecture.json`, `STYLE_CONTRACT.md` or `config.py`. This run does not
  move the story forward, it only reworks an existing text.
- Write only these files: {output_list}
- Do not produce a CHAPTER_UPDATE block, it is not needed in this run.
"""


def prompt_pass1(source: str, output: str) -> str:
    return f"""AGENT: Tyler
ROLE FILE: roles/TYLER.md
TASK TYPE: REVISION - PASS 1 (CONDENSING)
STORY: {STORY_NAME} (world: {WORLD_NAME})

This is NOT a write-from-scratch task. You are fixing how one of your own
chapters is built. Plot, scene order, character decisions, what is said in
the dialogue and the emotional course of the chapter stay EXACTLY the same.
The only thing that changes is how the text is put together.

READ:
- `{source}` (the text to revise)
- `{style_contract_path(WORLD_NAME)}` (your voice; do not change it, apply it)
- `{CRITERIA_FILE}` (defines why a text gets rejected)
{_shared_rules(source, f"`{output}`")}
WHAT TO LOOK FOR (the usual failure of a single-pass draft):
The text can be clean and error-free while every unit closes on itself.
Most paragraphs are 1-3 sentences and each ends on a small, sealed,
quotable line. The result is thirty small closed thoughts and not one
thought that develops over two hundred words. The shallowness is there,
not in the word choice. Check the text against `{CRITERIA_FILE}` items
A1-A4 and B1-B2 before you start, and name what you found in your answer.

WHAT TO DO (all required):
1. Merge short paragraphs that follow each other. Target: MOST paragraphs
   have 5-9 sentences. A one-sentence "emphasis paragraph" can be used AT
   MOST 2 times in the whole chapter.
2. Drop the habit of closing paragraphs with a short, epigram-like line. A
   paragraph can end in the middle of a thought too; not every paragraph
   needs a seal. AT MOST 2 times in the chapter.
3. In AT LEAST THREE places, let one perception/memory/thought develop
   WITHOUT BREAK for at least 150 words. Use subordinate clauses, long
   syntactic arcs, links from one image to the next. Do not cut the scene
   in the middle of these.
4. In dialogue: in AT LEAST ONE place a character speaks for 5+ sentences
   without interruption (tells a memory, explains a fear, defends
   something). A chain of one-line replies is limited to 2 lines at most;
   after that, action/look/body must come in.
5. Make feelings cost something instead of naming them: what a character
   feels is met with a concrete behavior, a hesitation, a movement of the hand.

FREEDOM: The text may get longer, that is fine (30-60% longer is expected).
Do not try to shorten it, that is not this pass's job. Do not shy away from
risky sentences that might fail; smoothness is this text's problem, not its
virtue.

KEEP: Dialogue uses quotation marks (not dashes). Events, characters,
scene order and the chapter title stay the same. Add nothing that goes
against the canon, the architecture or the world constraints.

OUTPUT:
- Write the full condensed chapter to: `{output}`
- End your answer with a short note: how many paragraphs you merged, where
  you put the three long developments, who got the long line of dialogue.
- Last line: DECISION: COMPLETE
"""


def prompt_pass2(source: str, input_file: str, output: str, variant_prefix: str, note_file: str) -> str:
    return f"""AGENT: Tyler
ROLE FILE: roles/TYLER.md
TASK TYPE: REVISION - PASS 2 (VARIANTS + SELECTION)
STORY: {STORY_NAME} (world: {WORLD_NAME})

The goal of this pass is to create selection pressure. A text is good not
because it was produced in one go, but because it was chosen from many
possibilities. Until now nothing in this system was thrown away; in this
pass something will be.

READ:
- `{input_file}` (the condensed text from pass 1, your working base)
- `{CRITERIA_FILE}` (the selection criteria; you will choose by THIS)
- `{style_contract_path(WORLD_NAME)}` (your voice)
{_shared_rules(source, f"`{variant_prefix}-*.md`, `{note_file}`, `{output}`")}
TWO KEY SCENES (you mark their exact boundaries yourself):
- SCENE A (opening): from the start of the chapter to the end of the first
  real exchange between characters. The opening sets the voice of a
  chapter, so this is where selection pressure matters most.
- SCENE B (turning point): the moment where the chapter's main character
  changes course, plus the build-up that leads to it. The emotional axis
  of the chapter turns here.
State where each scene starts and ends in the selection note.

WHAT TO DO:
1. Write THREE different versions of each scene. The versions must not be
   polished copies of each other, they must REALLY try different strategies:
   - v1: inner development: a long, unbroken chain of memory or
     perception; the character's mind carries the scene.
   - v2: bodily/sensory texture: the feeling is never named, it is paid
     for only with hands, objects, distance, light and behavior.
   - v3: speech: a long, unbroken line of dialogue sits at the center of
     the scene; the other character answers with action, not words.
   File names:
     `{variant_prefix}-sceneA-v1.md`, `-v2.md`, `-v3.md`
     `{variant_prefix}-sceneB-v1.md`, `-v2.md`, `-v3.md`
   Each variant is a full scene that can be read on its own.

2. SELECTION: Follow the order in `{CRITERIA_FILE}`: first C (content
   violations), then A (measurable structure), then B (style judgment). If
   A and B are tied, pick the RISKIER one. You will really throw away two
   of your own three versions; do not escape with "they are all good".

3. Write the selection note to `{note_file}`: for each scene, which version
   you picked, which criteria item (A1/A2/B1/B4...) eliminated which
   version, and in one sentence what the eliminated version loses. This
   note is written so the user can check whether your criteria match their
   own taste; try to show the reasoning, not to prove yourself right.

4. Write to `{output}` the FULL pass 1 text with these two scenes replaced
   by the chosen versions. Do not touch the rest of the text; at the joins,
   fix only the minimum transition sentences to keep the flow smooth.

OUTPUT:
- End your answer with a one-line summary of which versions you picked.
- Last line: DECISION: COMPLETE
"""


def prompt_pass3(source: str, input_file: str, output: str) -> str:
    return f"""AGENT: Tyler
ROLE FILE: roles/TYLER.md
TASK TYPE: REVISION - PASS 3 (PRUNING)
STORY: {STORY_NAME} (world: {WORLD_NAME})

Last pass. Your only job is to cut. You are NOT ADDING anything.

READ:
- `{input_file}` (the text from pass 2)
- `{CRITERIA_FILE}`
{_shared_rules(source, f"`{output}`")}
CUT:
- Sentences with no function; ones that add no information, feeling or
  tension to the scene.
- Saying the same image/feeling a second time. If something was said well
  once, saying it again weakens it.
- Sentences that explain what the reader already understood.
- Adjectives and adverbs that do not earn their place.

HARD RULES (the most important part of this pass):
- DO NOT SPLIT paragraphs again. Splitting long paragraphs into short
  pieces while pruning undoes the work of pass 1. The number of paragraphs
  CANNOT GO UP in this pass, it can only go down.
- Do not add new aphorism/epigram endings.
- Do not shorten the unbroken developments of 150+ words; they stay.
- Do not split the long line of dialogue.
- Do not add new scenes, events or characters.

MEASURE: 10-15% shorter is expected, but the goal is need, not a percentage.
If you cannot find much to cut, cut little; do not pretend to cut what is
not there.

OUTPUT:
- Write the full pruned text to: `{output}`
- End your answer with: roughly how many words you cut, what you had to cut
  most, and whether there is a place you found doubtful but could not
  bring yourself to cut.
- Last line: DECISION: COMPLETE
"""


def revise(chapter: str, redo: bool = False, measure_only: bool = False) -> bool:
    log_file = new_log_file("revise")
    clean_temp_files(REPO_PATH, log_file)

    source_rel = source_chapter_path(chapter)
    source_full = Path(REPO_PATH) / source_rel
    if not source_full.exists():
        log(f"ERROR: source chapter not found: {source_rel}", log_file)
        return False

    original = source_full.read_text(encoding="utf-8")
    rev_rel = revision_folder()
    rev_full = Path(REPO_PATH) / rev_rel
    rev_full.mkdir(parents=True, exist_ok=True)

    p1 = f"{rev_rel}/{chapter}-p1-condensed.md"
    p2 = f"{rev_rel}/{chapter}-p2-selected.md"
    p3 = f"{rev_rel}/{chapter}-p3-pruned.md"
    variant_prefix = f"{rev_rel}/{chapter}-p2-variant"
    selection_note = f"{rev_rel}/{chapter}-p2-selection-note.md"

    versions = [
        ("Original", source_full),
        ("P1 condensed", Path(REPO_PATH) / p1),
        ("P2 selected", Path(REPO_PATH) / p2),
        ("P3 pruned", Path(REPO_PATH) / p3),
    ]

    if measure_only:
        write_measure_table(versions, rev_full / "MEASUREMENTS.md", log_file)
        return True

    log(f"=== Revision experiment: {source_rel} ({len(original.split())} words) ===", log_file)
    log(f"Source file is protected, outputs go to: {rev_rel}/", log_file)

    passes = [
        ("Pass 1 - Condensing", p1, prompt_pass1(source_rel, p1)),
        ("Pass 2 - Variants + Selection", p2,
         prompt_pass2(source_rel, p1, p2, variant_prefix, selection_note)),
        ("Pass 3 - Pruning", p3, prompt_pass3(source_rel, p2, p3)),
    ]

    for name, output_rel, prompt in passes:
        output_full = Path(REPO_PATH) / output_rel
        if output_full.exists() and not redo:
            log(f"{name}: output already exists, skipping ({output_full.name}). "
                f"Add --redo to produce it again.", log_file)
            continue

        log(f"--- {name} starting ---", log_file)
        ok, output_text = run_codex(prompt, REPO_PATH, log_file, agent_name="Tyler", timeout=PASS_TIMEOUT)
        protect_original(source_full, original, log_file)

        if not output_full.exists():
            log(f"ERROR: {name} did not produce its output file ({output_rel}). "
                f"Stopping here; check the log, you can run the same command again.", log_file)
            return False

        if find_decision(output_text) != "COMPLETE":
            log(f"WARNING: no DECISION line for {name}, but the output file exists. Continuing.", log_file)

        m = measure(output_full.read_text(encoding="utf-8"))
        log(f"{name} done: {m.get('words')} words, {m.get('paragraphs')} paragraphs, "
            f"single-sentence paragraphs {m.get('single_sentence_ratio')}%, "
            f"150+ developments {m.get('long_development_150')}, "
            f"longest line {m.get('longest_single_line')} words", log_file)

    table = write_measure_table(versions, rev_full / "MEASUREMENTS.md", log_file)
    log("=== Revision experiment finished ===", log_file)
    if table:
        print()
        print(table)
    log(f"Full log: {log_file}", log_file)
    return True


if __name__ == "__main__":
    if not os.path.isdir(REPO_PATH):
        print(f"ERROR: REPO_PATH not found: {REPO_PATH}")
        sys.exit(1)

    argv = sys.argv[1:]
    chapter_arg = next((a for a in argv if not a.startswith("--")), "001")
    revise(chapter_arg, redo="--redo" in argv, measure_only="--measure" in argv)
