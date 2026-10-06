import os
import sys
from pathlib import Path

from agents import (
    AGENTS, new_log_file, log, read_state, write_state, find_decision, find_reason,
    update_index, source_file_path, clean_temp_files,
)
from config import REPO_PATH, SOURCE_NAME, CATEGORY, ISSUE_NUMBER, SOURCE_PREFIX


def find_raw_text() -> tuple[bool, str]:
    clean_name = SOURCE_PREFIX
    for ext in (".md", ".txt"):
        if clean_name.lower().endswith(ext):
            clean_name = clean_name[: -len(ext)]
            break

    for ext in (".md", ".txt"):
        candidate = Path(REPO_PATH) / "phase1-research" / "raw-texts" / f"{clean_name}{ext}"
        if candidate.exists():
            return True, f"phase1-research/raw-texts/{clean_name}{ext}"
    return False, ""


def task_prompt(agent: str, role_file: str, file_path: str, round_no: int, reason: str) -> str:
    has_raw_text, raw_text_path = find_raw_text()
    if has_raw_text:
        primary_text_note = (
            f"The primary text is already in the repo: {raw_text_path}. DO NOT "
            f"SEARCH THE WEB FOR THIS SOURCE, read this file from start to end "
            f"(if it is long, read it section by section; if you cannot finish "
            f"in one round, ask for a second round). In addition, use your own "
            f"web search tool to scan at least 2 different secondary/academic sources."
        )
    else:
        primary_text_note = (
            "The primary text is not in the repo. Use your own web search tool "
            "to find a reliable translation/edition and read it from start to "
            "end. In addition, scan at least 2 different secondary/academic sources."
        )

    if round_no > 1:
        round_note = (
            f"\nTHIS IS ROUND {round_no} FOR THIS SOURCE. It is a continuation, not a fresh start.\n"
            f"First read your own previous file ({file_path}) and see what is already "
            f"covered. In this round, focus on: {reason}\n"
            f"DO NOT REWRITE THE FILE FROM SCRATCH. Keep the previous content and "
            f"work the deeper parts from this round into the existing structure. "
            f"Set the `round:` field in the YAML metadata to {round_no}."
        )
    else:
        round_note = ""

    return f"""AGENT: {agent}
ROLE FILE: {role_file}
SOURCE: {SOURCE_NAME}
SOURCE ISSUE: #{ISSUE_NUMBER}
CATEGORY: {CATEGORY}
ROUND: {round_no}
PASS: 1 (independent)

TASK:
First read {role_file} and apply its depth protocol, output format and
limits. {primary_text_note} Do not rely only on what you already know.
Do not look for, read or refer to what the other agents wrote for this
source; this must be a fully independent reading. OUTPUT IS ALWAYS IN
ENGLISH, whatever the language of the source.
{round_note}

OUTPUT:
- Write the file to: {file_path}
- When you are done, leave a notice on the issue with
  `gh issue comment {ISSUE_NUMBER}`: "Analysis done, file: {file_path}".
  At the END of this comment add (required):
  1. Your signature: -{agent}
  2. On a separate line, one of these two formats:
     DECISION: COMPLETE
     or
     DECISION: SECOND_ROUND_NEEDED
     REASON: [one sentence, which sub-theme is not covered]
  Do not paste the analysis into the issue, only this short notice +
  signature + DECISION/REASON block.
- Add the same DECISION/REASON block (with the signature) to the very end
  of your final answer to me as well. The script reads it to track state,
  so the block must appear in both places (issue comment and final answer).
- Do not add or commit the file to git. Only create the file and leave
  the issue comment; commit/push is done separately.
- If you need a temp file for `gh` (e.g. `--body-file`), start its name
  with `.tmp_` and put it in the repo root (e.g. `.tmp_comment.md`). DO
  NOT try to delete it, you have no `rm` permission; the script cleans
  these files up for you.
"""


def run_pass1() -> bool:
    log_file = new_log_file("pass1")
    state = read_state(REPO_PATH, SOURCE_PREFIX)

    clean_temp_files(REPO_PATH, log_file)

    if SOURCE_PREFIX.lower().endswith((".md", ".txt")):
        log(f"WARNING: SOURCE_PREFIX ('{SOURCE_PREFIX}') ends with a file extension. "
            f"The script will still run, but the folder name will include the extension. "
            f"Fix it in config.py for consistency.", log_file)

    log(f"=== Source: {SOURCE_NAME} (#{ISSUE_NUMBER}) - Pass 1 starting ===", log_file)

    completed_again = []

    for agent, role_file, run_fn in AGENTS:
        agent_key = agent.lower()
        file_path = source_file_path(SOURCE_PREFIX, agent_key)
        record = state.get(agent_key)

        if record and record.get("status") == "complete":
            log(f"{agent}: already complete (round {record.get('round')}), skipping.", log_file)
            continue

        round_no = (record.get("round", 0) + 1) if record else 1
        reason = record.get("reason", "") if record else ""

        prompt = task_prompt(agent, role_file, file_path, round_no, reason)
        ok, output = run_fn(prompt, REPO_PATH, log_file, agent_name=agent)

        decision = find_decision(output)
        new_reason = find_reason(output) if decision == "SECOND_ROUND_NEEDED" else ""

        state[agent_key] = {
            "status": "complete" if decision == "COMPLETE" else (
                "second_round_needed" if decision == "SECOND_ROUND_NEEDED" else "unclear"
            ),
            "round": round_no,
            "reason": new_reason,
            "pass2_status": (record.get("pass2_status") if record else None),
        }
        write_state(REPO_PATH, SOURCE_PREFIX, state)

        if round_no > 1 and decision == "COMPLETE":
            completed_again.append(agent_key)

        log(f"{agent}: {'ran' if ok else 'failed'} | round {round_no} | DECISION: {decision}", log_file)

    if completed_again:
        for key in state:
            state[key]["pass2_status"] = None
        write_state(REPO_PATH, SOURCE_PREFIX, state)
        log(f"Agent(s) finished a later round ({', '.join(completed_again)}). Pass 2 status "
            f"was reset for everyone so all agents cross-check the updated files.", log_file)

    log("=== Pass 1 finished ===", log_file)

    all_complete = all(v.get("status") == "complete" for v in state.values()) and len(state) == len(AGENTS)
    max_round = max((v.get("round", 1) for v in state.values()), default=1)

    if all_complete:
        index_status = "in-progress"
        log("All three agents say COMPLETE. index.md set to 'in-progress', ready for pass 2.", log_file)
    else:
        index_status = "needs-second-pass" if any(
            v.get("status") == "second_round_needed" for v in state.values()
        ) else "in-progress"
        log("Some agents are not done. Run pass1.py again; it continues where it stopped.", log_file)

    update_index(REPO_PATH, ISSUE_NUMBER, SOURCE_NAME, CATEGORY, index_status, max_round)
    log("index.md updated.", log_file)
    log(f"Full log: {log_file}", log_file)

    return all_complete


if __name__ == "__main__":
    if not os.path.isdir(REPO_PATH):
        print(f"ERROR: REPO_PATH not found: {REPO_PATH}")
        sys.exit(1)
    run_pass1()
