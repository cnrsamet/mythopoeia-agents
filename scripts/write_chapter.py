import json
import os
import re
import sys
from pathlib import Path

from agents import (
    new_log_file, log, run_codex, find_decision, clean_temp_files,
    architecture_file_path, canon_file_path, style_contract_path, read_json, write_json,
)
from config import REPO_PATH, WORLD_NAME, STORY_NAME


def story_folder() -> str:
    return f"phase3-fiction/stories/{STORY_NAME}"


def story_state_path() -> Path:
    return Path(REPO_PATH) / story_folder() / "story_state.json"


def writer_brain_path() -> str:
    return f"{story_folder()}/writer-brain.md"


def chapters_folder() -> str:
    return f"{story_folder()}/chapters"


def find_update_block(text: str) -> dict:
    m = re.search(r"CHAPTER_UPDATE:\s*```(?:json)?\s*(\{.*?\})\s*```", text or "", re.DOTALL)
    if not m:
        return {}
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return {}


def task_prompt(state: dict, chapter_no: int, has_canon: bool) -> str:
    progress = state.get("progress_percent", 0)
    threshold = state.get("closing_threshold", 80)
    closing_note = ""
    if progress >= threshold:
        closing_note = (
            f"\nYOU ARE IN THE CLOSING ZONE (progress {progress}%, threshold {threshold}%). "
            f'Give priority to wrapping up the open threads with "weight: main". '
            f"But do NOT force every thread closed; most great works do not tie "
            f"up everything either.\n"
        )

    character_list = "\n".join(
        f"  - {c['name']}: {c['status']}" for c in state.get("characters", [])
    ) or "  (no characters)"
    open_thread_list = "\n".join(
        f"  - {t['thread']} (weight: {t.get('weight', '?')}, opened in chapter: {t.get('opened_chapter', '?')})"
        for t in state.get("open_threads", [])
    ) or "  (no open threads yet)"

    canon_note = (
        f"- {canon_file_path(WORLD_NAME)} (permanent events from ALL stories in "
        f"this WORLD; do not contradict them, refer to them if needed)"
        if has_canon else
        "- (this world has no canon.json yet, no story has added a permanent "
        "event, you are the first)"
    )

    return f"""AGENT: Tyler
ROLE FILE: roles/TYLER.md
TASK TYPE: CHAPTER WRITING
STORY: {STORY_NAME} (world: {WORLD_NAME})
CHAPTER: {chapter_no} / target {state.get('target_chapter_count')}

READ:
- {architecture_file_path(WORLD_NAME)} (world + story skeleton; its
  `constraint_compliance` field is the record of the binding constraints
  the user set when this world was built, follow it too)
{canon_note}
- {writer_brain_path()} (your own past notes, if any; skip if none)
- {style_contract_path(WORLD_NAME)} (your identity/voice FOR THIS WORLD, LOCKED, never change it)

CURRENT STORY STATE:
Characters:
{character_list}
Open threads:
{open_thread_list}
{closing_note}
TASK:
Write chapter {chapter_no} of the story. Stay fully true to the Style
Contract. Chapter length is up to your flow, there is no fixed word target.
Respect the open threads, character states and world/canon facts, do not
contradict them. You may open a new thread or create something unexpected
(like a character's death); that is your creative call, but report the
result in the update block below.

OUTPUT:
- Write the chapter text to: {chapters_folder()}/{chapter_no:03d}.md
- Add a free-form note about this chapter to the writer-brain
  (`{writer_brain_path()}`): DO NOT DELETE earlier content, add a new entry
  at the END of the file, separated by `--------------------`.
- There is no GitHub issue for this task, you do not need `gh`.
- At the VERY END of your answer, add an update block in this format
  (REQUIRED, must be valid JSON, do not skip any field, leave a list empty
  `[]` if nothing changed):

CHAPTER_UPDATE:
```json
{{
  "character_updates": [{{"name": "...", "new_status": "alive/dead/missing"}}],
  "new_threads": [{{"thread": "...", "weight": "main/side"}}],
  "closed_threads": [{{"thread": "..."}}],
  "canon_additions": [{{"event": "...", "date_note": "..."}}]
}}
```

And on the last line:
DECISION: COMPLETE

WARNING: Without the update block and the DECISION line the script cannot
process this chapter and will ask for the same chapter again next time.
"""


def write_chapter() -> bool:
    log_file = new_log_file("write_chapter")
    clean_temp_files(REPO_PATH, log_file)

    state = read_json(story_state_path())
    if not state:
        log(f"ERROR: {story_state_path()} not found. Run start_story.py first.", log_file)
        return False

    written = state.get("written_chapter_count", 0)
    target = state.get("target_chapter_count", 1)

    if written >= target:
        log(f"The story already reached its target chapter count ({target}). "
            f"To continue, raise target_chapter_count in story_state.json.", log_file)
        return True

    chapter_no = written + 1
    has_canon = (Path(REPO_PATH) / canon_file_path(WORLD_NAME)).exists()

    log(f"=== Writing chapter {chapter_no}/{target} ({STORY_NAME}) ===", log_file)

    prompt = task_prompt(state, chapter_no, has_canon)
    ok, output = run_codex(prompt, REPO_PATH, log_file, agent_name="Tyler", timeout=3600)

    decision = find_decision(output)
    if decision != "COMPLETE":
        log(f"Tyler did not finish the chapter or no DECISION line was found (DECISION: {decision}). "
            f"Check the files by hand; if all is well, run the same command again.", log_file)
        return False

    update = find_update_block(output)
    if not update:
        log("WARNING: could not parse the CHAPTER_UPDATE block, check story_state.json by hand.", log_file)

    character_map = {c["name"]: c for c in state.get("characters", [])}
    for u in update.get("character_updates", []):
        name = u.get("name")
        if name in character_map:
            character_map[name]["status"] = u.get("new_status", character_map[name]["status"])
            character_map[name]["last_seen_chapter"] = chapter_no

    open_threads = state.get("open_threads", [])
    closed_threads = state.get("closed_threads", [])
    for new in update.get("new_threads", []):
        open_threads.append({
            "thread": new.get("thread", ""),
            "weight": new.get("weight", "side"),
            "opened_chapter": chapter_no,
        })
    closed_names = {t.get("thread") for t in update.get("closed_threads", [])}
    if closed_names:
        still_open = []
        for t in open_threads:
            if t["thread"] in closed_names:
                t["closed_chapter"] = chapter_no
                closed_threads.append(t)
            else:
                still_open.append(t)
        open_threads = still_open

    state["characters"] = list(character_map.values())
    state["open_threads"] = open_threads
    state["closed_threads"] = closed_threads
    state["written_chapter_count"] = chapter_no
    state["progress_percent"] = round(100 * chapter_no / target)
    write_json(story_state_path(), state)

    canon_additions = update.get("canon_additions", [])
    if canon_additions:
        canon_path = Path(REPO_PATH) / canon_file_path(WORLD_NAME)
        canon = []
        if canon_path.exists():
            try:
                canon = json.loads(canon_path.read_text(encoding="utf-8"))
            except Exception:
                canon = []
        for event in canon_additions:
            canon.append({
                "event": event.get("event", ""),
                "date_note": event.get("date_note", ""),
                "source_story": STORY_NAME,
                "source_chapter": chapter_no,
            })
        write_json(canon_path, canon)
        log(f"Added {len(canon_additions)} permanent event(s) to canon.", log_file)

    closed_count = len(update.get("closed_threads", []))
    log(f"Chapter {chapter_no}/{target} done. Progress: {state['progress_percent']}%. "
        f"Open threads: {len(open_threads)}, closed in this chapter: {closed_count}.", log_file)

    if chapter_no % 10 == 0 or chapter_no >= target:
        gone = sum(1 for c in state["characters"] if c["status"] != "alive")
        log(f"--- DEVELOPER STATUS (chapter {chapter_no}, log only, never touches the story) ---", log_file)
        log(f"  Progress: {state['progress_percent']}% ({chapter_no}/{target})", log_file)
        log(f"  Open threads: {len(open_threads)} | Closed threads (total): {len(closed_threads)}", log_file)
        log(f"  Characters: {len(state['characters']) - gone} alive, {gone} dead/missing", log_file)

    if chapter_no >= target:
        log(f"=== STORY REACHED ITS TARGET CHAPTER COUNT: {STORY_NAME} ({chapter_no} chapters) ===", log_file)

    log(f"Full log: {log_file}", log_file)
    return chapter_no >= target


if __name__ == "__main__":
    if not os.path.isdir(REPO_PATH):
        print(f"ERROR: REPO_PATH not found: {REPO_PATH}")
        sys.exit(1)
    write_chapter()
