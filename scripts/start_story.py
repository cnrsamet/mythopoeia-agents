import json
import os
import re
import sys
from pathlib import Path

from agents import new_log_file, log, architecture_file_path, write_json
from config import REPO_PATH, WORLD_NAME, TARGET_CHAPTER_COUNT

CLOSING_THRESHOLD = 80


def update_config_story_name(story_name: str, log_file) -> bool:
    config_path = Path(__file__).resolve().parent / "config.py"
    if not config_path.exists():
        log(f"WARNING: {config_path} not found, set STORY_NAME by hand.", log_file)
        return False

    content = config_path.read_text(encoding="utf-8")
    new_line = f'STORY_NAME = "{story_name}"'

    if re.search(r"^STORY_NAME\s*=.*$", content, re.MULTILINE):
        new_content = re.sub(r"^STORY_NAME\s*=.*$", new_line, content, count=1, flags=re.MULTILINE)
    else:
        new_content = content.rstrip("\n") + f"\n{new_line}\n"

    config_path.write_text(new_content, encoding="utf-8")
    log(f'config.py updated: STORY_NAME = "{story_name}"', log_file)
    return True


def next_story_name(stories_folder: Path) -> str:
    if not stories_folder.exists():
        return "story-1"
    numbers = []
    for d in stories_folder.iterdir():
        if d.is_dir() and d.name.startswith("story-"):
            try:
                numbers.append(int(d.name.split("-")[1]))
            except (IndexError, ValueError):
                continue
    return f"story-{max(numbers, default=0) + 1}"


def start_story():
    log_file = new_log_file("start_story")

    architecture_path = Path(REPO_PATH) / architecture_file_path(WORLD_NAME)
    if not architecture_path.exists():
        log(f"ERROR: {architecture_path} not found. Build this world with build_world.py first.", log_file)
        return False

    architecture = json.loads(architecture_path.read_text(encoding="utf-8"))
    skeleton = architecture.get("story_skeleton", {})

    stories_folder = Path(REPO_PATH) / "phase3-fiction" / "stories"
    story_name = next_story_name(stories_folder)
    story_path = stories_folder / story_name
    story_path.mkdir(parents=True, exist_ok=True)
    (story_path / "chapters").mkdir(exist_ok=True)

    characters = [
        {"name": c.get("name", ""), "status": "alive", "last_seen_chapter": 0}
        for c in skeleton.get("characters", [])
    ]

    story_state = {
        "world_name": WORLD_NAME,
        "target_chapter_count": TARGET_CHAPTER_COUNT,
        "written_chapter_count": 0,
        "progress_percent": 0,
        "closing_threshold": CLOSING_THRESHOLD,
        "characters": characters,
        "open_threads": [],
        "closed_threads": [],
    }
    write_json(story_path / "story_state.json", story_state)

    writer_brain_header = (
        f"# Writer-Brain: {story_name} ({WORLD_NAME})\n\n"
        f"Tyler's free-form notebook for this story. A new entry is added after "
        f"every chapter, no old entry is ever deleted.\n"
    )
    (story_path / "writer-brain.md").write_text(writer_brain_header, encoding="utf-8")

    log(f"=== Story started: {story_name} (world: {WORLD_NAME}) ===", log_file)
    log(f"Target chapter count: {TARGET_CHAPTER_COUNT}, characters: {len(characters)}", log_file)
    update_config_story_name(story_name, log_file)
    log("You can now write the first chapter with python write_chapter.py.", log_file)
    log(f"Full log: {log_file}", log_file)
    return True


if __name__ == "__main__":
    if not os.path.isdir(REPO_PATH):
        print(f"ERROR: REPO_PATH not found: {REPO_PATH}")
        sys.exit(1)
    start_story()
