import os
from pathlib import Path


def _load_env_file():
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env_file()

REPO_PATH = os.environ.get("MYTHOPOEIA_REPO_PATH") or str(Path(__file__).resolve().parent.parent)

CLAUDE_MODEL = os.environ.get("MYTHOPOEIA_CLAUDE_MODEL", "claude-sonnet-5")
CODEX_MODEL = os.environ.get("MYTHOPOEIA_CODEX_MODEL", "gpt-5.6-sol")
GEMINI_MODEL = os.environ.get("MYTHOPOEIA_GEMINI_MODEL", "Gemini 3.1 Pro (High)")

SOURCE_NAME = "The Castle of Otranto"
CATEGORY = "Literature / Novel"
ISSUE_NUMBER = 6
SOURCE_PREFIX = "castle-of-otranto"

WORLD_NAME = "Saltreach"
TARGET_CHAPTER_COUNT = 3
STORY_NAME = "story-1"
PREFERRED_GENRE = "Quiet literary fiction"
COMPLEXITY_PREFERENCE = "simple and fast to read, few institutions, relationships and feelings come first"
ELEMENT_PEOPLES = ""
ELEMENT_LANGUAGES = ""
ELEMENT_GEOGRAPHY = "a small tidal island town, one main location"
ELEMENT_COSMOLOGY = ""
ELEMENT_HISTORICAL_EVENTS = "one old family secret"
ELEMENT_MAGIC = ""
