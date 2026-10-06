import os
import re
import sys
import threading
from pathlib import Path

from agents import (
    new_log_file, log, run_codex, find_decision, find_reason, clean_temp_files,
    read_json, write_json,
)
import config as _config

REPO_PATH = _config.REPO_PATH
PREFERRED_GENRE = getattr(_config, "PREFERRED_GENRE", "")
COMPLEXITY_PREFERENCE = getattr(_config, "COMPLEXITY_PREFERENCE", "")
ELEMENT_PEOPLES = getattr(_config, "ELEMENT_PEOPLES", "")
ELEMENT_LANGUAGES = getattr(_config, "ELEMENT_LANGUAGES", "")
ELEMENT_GEOGRAPHY = getattr(_config, "ELEMENT_GEOGRAPHY", "")
ELEMENT_COSMOLOGY = getattr(_config, "ELEMENT_COSMOLOGY", "")
ELEMENT_HISTORICAL_EVENTS = getattr(_config, "ELEMENT_HISTORICAL_EVENTS", "")
ELEMENT_MAGIC = getattr(_config, "ELEMENT_MAGIC", "")

SETUP_STATE_PATH = "phase2-world/setup-state.json"
CONSTRAINTS_FILE = "phase2-world/CONSTRAINTS.md"
SYNTHESIS_FILES = [
    "phase1-research/synthesis/tyler.md",
    "phase1-research/synthesis/erendiz.md",
    "phase1-research/synthesis/wilson.md",
]

WATCHED_PATHS = {
    "phase2-world/worlds": "World architecture",
    "phase2-world/cosmology": "Cosmology",
    "phase2-world/peoples-geography": "Peoples / Geography",
    "phase2-world/languages-names": "Languages / Names",
}


def update_config_world_name(world_name: str, log_file) -> bool:
    config_path = Path(__file__).resolve().parent / "config.py"
    if not config_path.exists():
        log(f"WARNING: {config_path} not found, set WORLD_NAME by hand.", log_file)
        return False

    content = config_path.read_text(encoding="utf-8")
    new_line = f'WORLD_NAME = "{world_name}"'

    if re.search(r"^WORLD_NAME\s*=.*$", content, re.MULTILINE):
        new_content = re.sub(r"^WORLD_NAME\s*=.*$", new_line, content, count=1, flags=re.MULTILINE)
    else:
        new_content = content.rstrip("\n") + f"\n{new_line}\n"

    config_path.write_text(new_content, encoding="utf-8")
    log(f'config.py updated: WORLD_NAME = "{world_name}"', log_file)
    return True


def _start_stage_watcher(log_file, stop_event: threading.Event) -> threading.Thread:

    def loop():
        last_mtime: dict[Path, float] = {}
        first_scan = True
        while not stop_event.is_set():
            for rel_path, label in WATCHED_PATHS.items():
                target = Path(REPO_PATH) / rel_path
                files = [target] if target.is_file() else (
                    list(target.rglob("*.md")) + list(target.rglob("*.json"))
                    if target.is_dir() else []
                )
                for f in files:
                    try:
                        mtime = f.stat().st_mtime
                    except FileNotFoundError:
                        continue
                    previous = last_mtime.get(f)
                    last_mtime[f] = mtime
                    if not first_scan and previous != mtime:
                        log(f"  -> Looks like it is working on '{label}' "
                            f"({f.relative_to(REPO_PATH)} changed)", log_file)
            first_scan = False
            stop_event.wait(10)

    t = threading.Thread(target=loop, daemon=True)
    t.start()
    return t


def find_world_name(text: str) -> str:
    m = re.search(r"WORLD_NAME:\s*(.+)", text or "", re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return ""


def _element_notes() -> str:
    elements = [
        ("peoples", ELEMENT_PEOPLES, "the world.peoples field and the peoples part of peoples-geography.md"),
        ("languages", ELEMENT_LANGUAGES, "the world.languages field and the whole languages-names.md file"),
        ("geography", ELEMENT_GEOGRAPHY, "the geography part of peoples-geography.md"),
        ("cosmology", ELEMENT_COSMOLOGY, "the world.cosmology_summary field and the whole cosmology.md file"),
        ("historical events", ELEMENT_HISTORICAL_EVENTS, "the world.historical_events field"),
        ("magic", ELEMENT_MAGIC, "any magic/supernatural mechanic; magic-related rules in CONSTRAINTS.md "
         "apply ONLY if this element is ACTIVE"),
    ]
    lines = []
    for name, value, scope in elements:
        if value.strip():
            lines.append(f'  - {name}: ACTIVE. Direction: "{value.strip()}". Covers: {scope}.')
        elif name == "magic":
            lines.append(f"  - magic: INACTIVE. Covers: {scope}. This world has NO magic or "
                         f"supernatural mechanic at all; do not invent a magic system/object/power "
                         f"in architecture.json (in any field), in the prose files or in "
                         f"story_skeleton. Even if CONSTRAINTS.md mentions magic (e.g. 'magic "
                         f"should be rare'), that rule does not assume magic EXISTS, only how "
                         f"it is limited if it does; if there is no magic, simply ignore it.")
        else:
            lines.append(f"  - {name}: INACTIVE. Covers: {scope}. DO NOT PRODUCE it: do not add "
                         f"the related field to architecture.json at all (not even an empty "
                         f"list/object, the key must not exist), do not create the related prose "
                         f"file/section.")
    return "\n".join(lines)


def task_prompt(round_no: int, reason: str, continuing: bool, current_name: str) -> str:
    if continuing and current_name:
        name_note = (
            f"\nTHIS IS ROUND {round_no} (you are continuing the same task). In the "
            f"previous round you named the world '{current_name}', USE THE SAME NAME, "
            f"do not rename it. First read your own earlier drafts "
            f"(phase2-world/worlds/{current_name}/architecture.json and the files under "
            f"phase2-world/{{cosmology,peoples-geography,languages-names}}/{current_name}/, "
            f"if any) and continue where you stopped. "
            f"Focus on the part you could not finish: {reason}\n"
        )
    else:
        existing_worlds = []
        worlds_folder = Path(REPO_PATH) / "phase2-world" / "worlds"
        if worlds_folder.exists():
            existing_worlds = [d.name for d in worlds_folder.iterdir() if d.is_dir()]

        list_note = (
            f" These world names already exist (pick a DIFFERENT name that does not "
            f"clash with them): {', '.join(existing_worlds)}."
            if existing_worlds else ""
        )

        name_note = (
            "\nThis is your first round. Give the world an original name of your own "
            "(short, no spaces or with hyphens, e.g. 'Kirenmoor' or 'Ashendale')."
            f"{list_note} You will use this name in every file path and at the end "
            "of your answer.\n"
        )

    if PREFERRED_GENRE.strip():
        genre_note = (
            f"\nUSER'S GENRE CHOICE (BINDING): '{PREFERRED_GENRE}'. The world and story "
            f"skeleton you build must fit this genre, even if the syntheses pull "
            f"another way (e.g. sources heavy on mythology). Reinterpret the "
            f"abstracted patterns from the syntheses (threshold, authority, duality "
            f"and so on) inside this genre, do not change the genre.\n"
        )
    else:
        genre_note = (
            "\nThe user did not choose a genre. Pick the genre (fantasy, romance, "
            "science fiction, historical, etc.) from the patterns in the syntheses, "
            "and say briefly at the end of your answer which genre you picked and why.\n"
        )

    if COMPLEXITY_PREFERENCE.strip():
        complexity_note = (
            f"\nUSER'S COMPLEXITY CHOICE (BINDING): '{COMPLEXITY_PREFERENCE}'. This is not "
            f"only about simple sentences, it also limits how many separate "
            f"institutions/intrigues/threads the story skeleton (plot) carries. Build "
            f"a few clear institutions; keep the number of parallel threads the reader "
            f"must follow at once low on purpose. Richness should come from the "
            f"emotional/human weight of details, not from their number.\n"
        )
    else:
        complexity_note = ""

    return f"""AGENT: Tyler
ROLE FILE: roles/TYLER.md
TASK TYPE: WORLD BUILDING
ROUND: {round_no}

READ (this is the ONLY exception to the "do not read the other agents'
files" rule, here you read all three):
- {SYNTHESIS_FILES[0]} (your own synthesis)
- {SYNTHESIS_FILES[1]}
- {SYNTHESIS_FILES[2]}
- {CONSTRAINTS_FILE} (the user's binding constraints, they come before your own creative choices and are not up for debate)
{name_note}{genre_note}{complexity_note}
WORLD ELEMENTS (BINDING, under the user's explicit control. Whatever the
genre, YOU cannot decide these, you only follow the list below):
{_element_notes()}

TASK:
Feed on these three syntheses and build an original world from scratch.
Do not quote or copy from the sources in the syntheses (or the original
works); blend the abstracted patterns and the findings marked as "usable
features for worldbuilding" into something fully NEW. OUTPUT IS ALWAYS IN
ENGLISH.

YOU WILL PRODUCE THREE KINDS OF FILES (below, {{name}} is the world name you
give/use):

1. `phase2-world/worlds/{{name}}/STYLE_CONTRACT.md` (SPECIFIC TO THIS WORLD,
   not shared with other worlds). From now on you are no longer only a
   language/narrative analyst, you are a myth-maker and storyteller. Write
   down what this identity/voice is: tone, narrative tense, voice, POV
   leaning (single or multiple characters, you decide), dialogue rules. This
   file is the voice of THIS world only; if you build a different world it
   is written again for that world.

   Voice and tone can change per world, but the following BASE rules must
   appear in EVERY world's Style Contract, as they are, regardless of the
   world (they are lessons from earlier reader tests and are about
   readability, not about any one world):
   - Dialogue is written with quotation marks, not dashes.
   - Dialogue length follows the needs of the scene; when needed it can
     become a real, long conversation, it does not have to stay short and
     clipped. Back-to-back lines are not left bare; action/look/reaction is
     placed between them. THIS IS REQUIRED, NOT OPTIONAL: in every chapter,
     AT LEAST ONCE, a character speaks without interruption for at least 4-5
     sentences (about a paragraph): tells a memory, explains a feeling,
     defends something. A constant exchange of one or two sentence lines
     (short-short-short) feels like an interrogation, not a conversation;
     this rhythm alone cannot fill a WHOLE chapter.
   - Warmth is required: every chapter has at least one moment of real
     relief, joking or friendship; constant gravity is monotony. BUT warmth
     should not ALWAYS be witty banter or teasing; in at least some chapters
     there should also be a quiet closeness, direct tenderness, unguarded
     honesty or a moment of physical relief. If two characters keep throwing
     witty, pointed lines at each other (a good tool on its own), they are
     stuck in ONE register of warmth; variety is needed.
   - A new term, tool, institution, title, PLACE NAME OR SMALL/PASSING
     DETAIL (the job of a passer-by, the name of an object) is introduced
     the first time it appears with a natural hook tied to the character
     (a habit, a memory of learning it, a short clause that sums up what it
     does); the reader should not have to read twice. This rule applies to
     SMALL/SIDE details too, not only to the main institutions of the world;
     if a detail has no hook, either give it one or cut it, do not leave it
     to guesswork.
   - Dialogue with subtext (a character saying one thing and meaning
     another) is used RARELY and with a CLEAR trace; the reader should sense
     the double meaning without rereading. If you build two-layer dialogue
     (one real topic, one hidden feeling), at least one character should
     name it openly ("You weren't talking about that, I know"); do not make
     the reader solve it alone.
   - Every scene, before going into detail, answers in a few sentences
     "what is at stake right now, what does the character want"; rich
     detail does not replace this hook, it follows it.
   - YOU read the source files like architecture.json, but THE READER DID
     NOT, the reader has only read the earlier CHAPTERS. Each new
     institution/term/title is introduced in the chapter where it first
     appears; do not use it without introducing it because "it came up in
     chapter 1" or "it was defined in the source file". This rule applies
     again in every chapter, not only the first one.
   These seven rules do not depend on the genre/tone of the world; they
   must appear as they are in every Style Contract.

2. `phase2-world/worlds/{{name}}/architecture.json`: ONLY valid JSON.
   The schema below is shown in its FULL/theoretical form, but YOU fill only
   the fields that are ACTIVE in the "WORLD ELEMENTS" list above. Do not
   add INACTIVE fields to architecture.json at all (not even the key, no
   empty `[]`/`""`, the field is fully absent):
```
{{
  "world": {{
    "genre": "...",
    "period": "...",
    "cosmology_summary": "... (ONLY if cosmology is ACTIVE)",
    "peoples": [{{"name": "...", "trait": "..."}}] "... (ONLY if peoples is ACTIVE)",
    "languages": [{{"name": "...", "trait": "..."}}] "... (ONLY if languages is ACTIVE)",
    "geography_summary": "... (ONLY if geography is ACTIVE)",
    "historical_events": [{{"event": "...", "date": "..."}}] "... (ONLY if historical events is ACTIVE)"
  }},
  "story_skeleton": {{
    "genre": "...", "narrative_form": "...",
    "characters": [{{"name": "...", "role": "...", "trait": "..."}}],
    "relationships": [{{"who": "...", "with": "...", "relationship": "..."}}],
    "plot": [{{"stage": "...", "summary": "..."}}]
  }},
  "constraint_compliance": [{{"constraint": "...", "how_met": "..."}}]
}}
```
   `story_skeleton` and `constraint_compliance` are ALWAYS filled, whatever
   the element list says (every story needs characters/plot, every world
   needs to meet its constraints). In `constraint_compliance` list EVERY
   item in `{CONSTRAINTS_FILE}` one by one and write how you met it in
   concrete terms.

3. RICH, READABLE PROSE files. Create them ONLY if the related element(s)
   are ACTIVE; if INACTIVE, do not create the file at all:
   - `phase2-world/cosmology/{{name}}/cosmology.md` (if cosmology is ACTIVE)
   - `phase2-world/peoples-geography/{{name}}/peoples-geography.md` (if
     peoples AND/OR geography are ACTIVE; if both, cover both, if only one,
     write only that part)
   - `phase2-world/languages-names/{{name}}/languages-names.md` (if
     languages is ACTIVE)
   These are the short fields of architecture.json expanded into real
   narrative; they deepen architecture.json, they do not repeat it.

CONSISTENCY CHECK (REQUIRED, do it before saying `DECISION: COMPLETE`):
Do a simple arithmetic check between the dates in `historical_events` and
the characters' ages, their role in those events, or claims about the past
such as "they were a child/young then". For example, if a character is
remembered as a child/young person in a past event, the gap in years
between the story's present and that event must match the character's
current age; otherwise (unless your world has an unusual long-life/no-aging
mechanic) it is an error, fix either the past or the age. Summarize briefly
in your answer anything you found/fixed while doing this.

OUTPUT:
- Write all files to the paths above.
- There is no GitHub issue for this task, you do not need `gh`.
- After this step the pipeline DOES NOT move on to Phase 3 (the actual
  writing) on its own. The user will review/approve/edit first; be aware
  of that.
- If you need a temp file, start its name with `.tmp_`, do NOT try to delete it.
- At the VERY END of your answer, on separate lines, add these (REQUIRED):
  WORLD_NAME: [the name you picked/used]
  DECISION: COMPLETE
  or
  DECISION: SECOND_ROUND_NEEDED
  REASON: [one sentence, which part you could not finish]

  WARNING: If you leave these lines out, the script cannot count your work
  as complete and next time it will give you THE SAME TASK FROM THE START.
"""


def build_world() -> bool:
    log_file = new_log_file("build_world")
    clean_temp_files(REPO_PATH, log_file)

    log("=== World building starting ===", log_file)

    for s in SYNTHESIS_FILES:
        if not (Path(REPO_PATH) / s).exists():
            log(f"ERROR: {s} not found. Finish Phase 1 (including synthesis.py) first.", log_file)
            return False

    state_path = Path(REPO_PATH) / SETUP_STATE_PATH
    record = read_json(state_path)

    if record.get("status") == "complete":
        log(f"World building already complete: '{record.get('world_name')}'. "
            f"For a new world, delete {SETUP_STATE_PATH}.", log_file)
        return True

    continuing = record.get("status") == "second_round_needed"
    round_no = (record.get("round", 0) + 1) if continuing else 1
    reason = record.get("reason", "") if continuing else ""
    current_name = record.get("world_name", "")

    prompt = task_prompt(round_no, reason, continuing, current_name)

    stop_event = threading.Event()
    watcher = _start_stage_watcher(log_file, stop_event)
    try:
        ok, output = run_codex(prompt, REPO_PATH, log_file, agent_name="Tyler", timeout=5400)
    finally:
        stop_event.set()
        watcher.join(timeout=2)

    decision = find_decision(output)
    new_reason = find_reason(output) if decision == "SECOND_ROUND_NEEDED" else ""
    new_name = find_world_name(output) or current_name

    if decision == "COMPLETE":
        record = {"status": "complete", "round": round_no, "reason": "", "world_name": new_name}
        log(f"Tyler: world building complete (round {round_no}), world name: '{new_name}'.", log_file)
        update_config_world_name(new_name, log_file)
        log(f"REVIEW STOP: check phase2-world/worlds/{new_name}/architecture.json and "
            f"STYLE_CONTRACT.md (plus the {new_name}/ folders under cosmology/"
            f"peoples-geography/languages-names), edit by hand if needed. "
            f"Then start Phase 3.", log_file)
    elif decision == "SECOND_ROUND_NEEDED":
        record = {"status": "second_round_needed", "round": round_no, "reason": new_reason, "world_name": new_name}
        log(f"Tyler: round {round_no} not finished ('{new_name}'), reason: {new_reason}. "
            f"Run build_world.py again.", log_file)
    else:
        record = {"status": "unclear", "round": round_no, "reason": "", "world_name": new_name}
        log("Tyler: no DECISION line found, result unclear. Check the files by hand.", log_file)

    write_json(state_path, record)
    log(f"Full log: {log_file}", log_file)

    return record.get("status") == "complete"


if __name__ == "__main__":
    if not os.path.isdir(REPO_PATH):
        print(f"ERROR: REPO_PATH not found: {REPO_PATH}")
        sys.exit(1)
    build_world()
