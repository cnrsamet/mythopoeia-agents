import json
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from config import CLAUDE_MODEL, CODEX_MODEL, GEMINI_MODEL

AGENT_KEYS = ("erendiz", "wilson", "tyler")

if sys.platform == "win32":
    subprocess.run("chcp 65001", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def new_log_file(script_name: str) -> Path:
    log_dir = Path(__file__).parent / "run_logs"
    log_dir.mkdir(exist_ok=True)
    return log_dir / f"{script_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"


def log(msg: str, log_file: Path):
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    print(line)
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def source_folder(source_prefix: str) -> str:
    return f"phase1-research/sources/{source_prefix}"


def source_file_path(source_prefix: str, agent_key: str) -> str:
    return f"{source_folder(source_prefix)}/{agent_key}.md"


def state_file_path(repo_path: str, source_prefix: str) -> Path:
    return Path(repo_path) / source_folder(source_prefix) / "state.json"


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def read_state(repo_path: str, source_prefix: str) -> dict:
    return read_json(state_file_path(repo_path, source_prefix))


def write_state(repo_path: str, source_prefix: str, data: dict):
    write_json(state_file_path(repo_path, source_prefix), data)


def update_index(repo_path: str, issue_number: int, source_name: str, category: str, status: str, round_count: int):
    path = Path(repo_path) / "phase1-research" / "index.md"
    if not path.exists():
        return

    target = f"#{issue_number}"
    lines = path.read_text(encoding="utf-8").splitlines()
    new_lines = []
    found = False
    max_no = 0

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("|") and "---" not in stripped and "Source" not in stripped:
            parts = [p.strip() for p in stripped.strip("|").split("|")]
            if len(parts) >= 6:
                try:
                    max_no = max(max_no, int(parts[0]))
                except ValueError:
                    pass
                if parts[5] == target:
                    parts[1] = source_name
                    parts[2] = category
                    parts[3] = status
                    parts[4] = str(round_count)
                    line = "| " + " | ".join(parts) + " |"
                    found = True
        new_lines.append(line)

    if not found:
        new_row = f"| {max_no + 1} | {source_name} | {category} | {status} | {round_count} | {target} |"
        inserted = False
        for i, line in enumerate(new_lines):
            if line.strip().startswith("<!--"):
                new_lines.insert(i, new_row)
                inserted = True
                break
        if not inserted:
            new_lines.append(new_row)

    path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def clean_temp_files(repo_path: str, log_file: Path = None):
    root = Path(repo_path)
    removed = []
    for f in root.glob(".tmp_*"):
        if f.is_file():
            try:
                f.unlink()
                removed.append(f.name)
            except Exception:
                pass
    if removed and log_file:
        log(f"Temp files removed: {', '.join(removed)}", log_file)
    return removed


def find_decision(text: str) -> str:
    # The last match wins: the block is required at the very end, and an agent
    # that echoes the option list earlier in its answer must not decide the state.
    matches = re.findall(r"DECISION:\s*(COMPLETE|SECOND_ROUND_NEEDED|ENRICHMENT)", text or "", re.IGNORECASE)
    if matches:
        return matches[-1].upper()
    return "UNCLEAR"


def find_reason(text: str) -> str:
    matches = re.findall(r"REASON:\s*(.+)", text or "", re.IGNORECASE)
    if matches:
        return matches[-1].strip()
    return ""


def trusted_issue_comments(repo_path: str, issue_number: int, log_file: Path) -> str:
    # Only comments by the logged-in gh account. The agents comment through this
    # same account, so their notices are kept; anyone else's comment on a public
    # repo is dropped and never reaches an agent's prompt.
    gh = shutil.which("gh") or "gh"
    try:
        me = subprocess.run(
            [gh, "api", "user", "--jq", ".login"],
            cwd=repo_path, capture_output=True, text=True, timeout=60,
            encoding="utf-8", errors="replace",
        )
        view = subprocess.run(
            [gh, "issue", "view", str(issue_number), "--json", "comments"],
            cwd=repo_path, capture_output=True, text=True, timeout=60,
            encoding="utf-8", errors="replace",
        )
    except Exception as e:
        log(f"Could not read issue #{issue_number} comments: {e}", log_file)
        return ""
    login = (me.stdout or "").strip()
    if me.returncode != 0 or not login or view.returncode != 0:
        log(f"Could not read issue #{issue_number} comments: {(me.stderr or view.stderr or '')[:500]}", log_file)
        return ""
    try:
        comments = json.loads(view.stdout).get("comments", [])
    except Exception:
        return ""

    kept = [c for c in comments if (c.get("author") or {}).get("login") == login]
    dropped = len(comments) - len(kept)
    if dropped:
        log(f"Issue #{issue_number}: ignored {dropped} comment(s) not written by '{login}'.", log_file)
    return "\n\n---\n\n".join(c.get("body", "").strip() for c in kept)


def find_completed_sources(repo_path: str) -> list:
    root = Path(repo_path) / "phase1-research" / "sources"
    if not root.exists():
        return []
    completed = []
    for folder in sorted(root.iterdir()):
        if not folder.is_dir():
            continue
        state = read_json(folder / "state.json")
        if state and all(
            state.get(agent, {}).get("status") == "complete"
            and state.get(agent, {}).get("pass2_status") == "complete"
            for agent in AGENT_KEYS
        ):
            completed.append(folder.name)
    return completed


def synthesis_state_path(repo_path: str) -> Path:
    return Path(repo_path) / "phase1-research" / "synthesis" / "synthesis-state.json"


def read_synthesis_state(repo_path: str) -> dict:
    return read_json(synthesis_state_path(repo_path))


def write_synthesis_state(repo_path: str, data: dict):
    write_json(synthesis_state_path(repo_path), data)


def world_folder(world_name: str) -> str:
    return f"phase2-world/worlds/{world_name}"


def architecture_file_path(world_name: str) -> str:
    return f"{world_folder(world_name)}/architecture.json"


def canon_file_path(world_name: str) -> str:
    return f"{world_folder(world_name)}/canon.json"


def style_contract_path(world_name: str) -> str:
    return f"{world_folder(world_name)}/STYLE_CONTRACT.md"


def _finish(agent_name: str, result, log_file: Path) -> tuple[bool, str]:
    ok = result.returncode == 0
    log(f"{agent_name} {'finished' if ok else 'FAILED'} (returncode={result.returncode})", log_file)
    log(f"{agent_name} output (first 500 chars): {(result.stdout or '')[:500]}", log_file)
    if not ok:
        log(f"{agent_name} stderr: {(result.stderr or '')[:2500]}", log_file)
    return ok, result.stdout


def run_claude(
    prompt: str, repo_path: str, log_file: Path,
    agent_name: str = "Erendiz", model: str = CLAUDE_MODEL, timeout: int = 1200,
) -> tuple[bool, str]:
    log(f"{agent_name} (claude) running... (timeout: {timeout // 60} min)", log_file)
    try:
        result = subprocess.run(
            [shutil.which("claude") or "claude", "-p", prompt,
             "--model", model,
             "--allowedTools",
             "Read,Write,Edit,WebSearch,WebFetch,"
             "Bash(gh issue comment *)",
             "--disallowedTools",
             "Bash(rm *),Bash(del *),Bash(curl *),Bash(Invoke-WebRequest *),"
             "Bash(iwr *),Bash(sudo *),Bash(chmod *),Bash(git push*)",
             "--permission-mode", "acceptEdits"],
            cwd=repo_path, capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace",
        )
        return _finish(agent_name, result, log_file)
    except subprocess.TimeoutExpired as e:
        partial = e.stdout or ""
        log(f"{agent_name} timed out ({timeout} s), partial output kept ({len(partial)} chars)", log_file)
        return False, partial
    except Exception as e:
        log(f"{agent_name} call failed: {e}", log_file)
        return False, str(e)


def run_codex(
    prompt: str, repo_path: str, log_file: Path,
    agent_name: str = "Tyler", model: str = CODEX_MODEL, timeout: int = 1200,
) -> tuple[bool, str]:
    log(f"{agent_name} (codex) running... (timeout: {timeout // 60} min)", log_file)
    try:
        result = subprocess.run(
            [shutil.which("codex") or "codex", "exec",
             "--model", model,
             "-c", 'model_reasoning_effort="high"',
             "--sandbox", "workspace-write",
             "-c", 'approval_policy="never"',
             "-c", 'sandbox_workspace_write.network_access=true',
             "-c", 'web_search="live"',
             "-"],
            cwd=repo_path, capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace", input=prompt,
        )
        return _finish(agent_name, result, log_file)
    except subprocess.TimeoutExpired as e:
        partial = e.stdout or ""
        log(f"{agent_name} timed out ({timeout} s), partial output kept ({len(partial)} chars)", log_file)
        return False, partial
    except Exception as e:
        log(f"{agent_name} call failed: {e}", log_file)
        return False, str(e)


def run_gemini(
    prompt: str, repo_path: str, log_file: Path,
    agent_name: str = "Wilson", model: str = GEMINI_MODEL, timeout: int = 1200,
) -> tuple[bool, str]:
    log(f"{agent_name} (agy) running... (timeout: {timeout // 60} min)", log_file)
    try:
        from agy_headless_bridge import run, AgyNotFoundError, AgyTimeoutError
    except ImportError:
        log("agy_headless_bridge is not installed. Install it with: pip install agy-headless-bridge", log_file)
        return False, "agy_headless_bridge missing"

    try:
        output = run(
            prompt,
            add_dirs=[repo_path],
            model=model,
            timeout=timeout,
            idle_timeout=180,
            extra_args=["--dangerously-skip-permissions"],
        )
        log(f"{agent_name} finished", log_file)
        log(f"{agent_name} output (first 500 chars): {(output or '')[:500]}", log_file)
        return True, output
    except AgyTimeoutError as e:
        log(f"{agent_name} timed out, partial output kept ({len(e.partial)} chars)", log_file)
        return False, e.partial
    except AgyNotFoundError:
        log("agy command not found. Make sure it is on PATH and you are logged in.", log_file)
        return False, "agy not found"
    except Exception as e:
        log(f"{agent_name} call failed: {e}", log_file)
        return False, str(e)


AGENTS = [
    ("Erendiz", "roles/ERENDIZ.md", run_claude),
    ("Wilson", "roles/WILSON.md", run_gemini),
    ("Tyler", "roles/TYLER.md", run_codex),
]
