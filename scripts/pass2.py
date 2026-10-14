import os
import sys
from pathlib import Path

from agents import (
    AGENTS, new_log_file, log, read_state, write_state, find_decision, find_reason,
    update_index, source_file_path, clean_temp_files, trusted_issue_comments,
)
from config import REPO_PATH, SOURCE_NAME, CATEGORY, ISSUE_NUMBER, SOURCE_PREFIX


def task_prompt(agent: str, role_file: str, own_file: str, other_files: list, notices: str) -> str:
    other_list = "\n".join(f"- {f}" for f in other_files)
    return f"""AGENT: {agent}
ROLE FILE: {role_file}
SOURCE: {SOURCE_NAME}
SOURCE ISSUE: #{ISSUE_NUMBER}
PASS: 2 (shared)

READ:
{other_list}
- The pass 1 notices on issue #{ISSUE_NUMBER}, given below. Do not run
  `gh issue view`; other comments on the issue are not part of this task.

PASS 1 NOTICES:
{notices or "(none found)"}

TASK:
Your own file ({own_file}) was already written in pass 1. Read the two
files listed above. There are three possible outcomes:

1. **Contradiction / real gap**: After reading the others you see that part
   of your own analysis is missing or wrong -> write
   `DECISION: SECOND_ROUND_NEEDED` and DO NOT CHANGE your file (this reopens
   pass 1, you will fix it there).
2. **Enrichment**: Not a refuting gap, but reading the others you noticed a
   valuable link from your own lens -> add a small, clearly titled section
   at the VERY END of your file: `## Pass 2 Note`, 2-4 sentences, fully in
   your own lens and voice. Do not change the rest of the file, only append
   this section. Then write `DECISION: ENRICHMENT`.
3. **Neither**: No gap and no enrichment -> write `DECISION: COMPLETE`.

Whatever the outcome, leave a comment of at most 150-200 words on the issue
with `gh issue comment {ISSUE_NUMBER}` (summarize what you noticed, do not
stay silent). OUTPUT IS ALWAYS IN ENGLISH.

At the END of this issue comment (the text you send to GitHub with
gh issue comment) add the following, this is required:
1. Your signature: -{agent}
2. On a separate line, one of the three options above:
   DECISION: COMPLETE
   or
   DECISION: ENRICHMENT
   REASON: [one sentence, which link you added to your file and why]
   or
   DECISION: SECOND_ROUND_NEEDED
   REASON: [one sentence, which sub-theme is not covered]

Add the same DECISION/REASON block (with the signature) to the very end of
your final answer to me as well. The script reads it to track state, so the
block must appear in both places (issue comment and final answer).

If you need a temp file for `gh` (e.g. `--body-file`), start its name with
`.tmp_` and put it in the repo root. DO NOT try to delete it, you have no
`rm` permission; the script cleans these files up for you.
"""


def run_pass2() -> bool:
    log_file = new_log_file("pass2")
    state = read_state(REPO_PATH, SOURCE_PREFIX)

    clean_temp_files(REPO_PATH, log_file)

    log(f"=== Source: {SOURCE_NAME} (#{ISSUE_NUMBER}) - Pass 2 starting ===", log_file)

    all_files = {agent.lower(): source_file_path(SOURCE_PREFIX, agent.lower()) for agent, _, _ in AGENTS}
    notices = trusted_issue_comments(REPO_PATH, ISSUE_NUMBER, log_file)
    agents_run = 0

    for agent, role_file, run_fn in AGENTS:
        agent_key = agent.lower()
        record = state.get(agent_key, {})

        if record.get("status") != "complete":
            log(f"{agent}: pass 1 not complete yet ({record.get('status', 'never ran')}), skipping pass 2.", log_file)
            continue

        if record.get("pass2_status") == "complete":
            log(f"{agent}: pass 2 already complete, skipping.", log_file)
            continue

        if not (Path(REPO_PATH) / all_files[agent_key]).exists():
            log(f"{agent}: file ({all_files[agent_key]}) not found, skipping.", log_file)
            continue

        other_files = [v for k, v in all_files.items() if k != agent_key]
        prompt = task_prompt(agent, role_file, all_files[agent_key], other_files, notices)
        ok, output = run_fn(prompt, REPO_PATH, log_file, agent_name=agent)
        agents_run += 1

        decision = find_decision(output) if ok else "UNCLEAR"
        new_reason = find_reason(output) if decision in ("SECOND_ROUND_NEEDED", "ENRICHMENT") else ""

        if decision == "SECOND_ROUND_NEEDED":
            record["status"] = "second_round_needed"
            record["reason"] = new_reason
            record["pass2_status"] = None
            log(f"{agent}: found a gap in pass 2, pass 1 reopened. Reason: {new_reason}", log_file)
        elif decision == "ENRICHMENT":
            record["pass2_status"] = "complete"
            log(f"{agent}: enriched its own file in pass 2. Note: {new_reason}", log_file)
        elif decision == "COMPLETE":
            record["pass2_status"] = "complete"
            log(f"{agent}: pass 2 complete.", log_file)
        else:
            record["pass2_status"] = "unclear"
            log(f"{agent}: pass 2 result unclear (no DECISION line found), check the issue by hand.", log_file)

        state[agent_key] = record
        write_state(REPO_PATH, SOURCE_PREFIX, state)

    log("=== Pass 2 finished ===", log_file)

    if agents_run == 0:
        log("No agent ran (each one either has not finished pass 1 or already finished pass 2).", log_file)

    all_done = all(
        state.get(agent.lower(), {}).get("status") == "complete"
        and state.get(agent.lower(), {}).get("pass2_status") == "complete"
        for agent, _, _ in AGENTS
    )
    max_round = max((v.get("round", 1) for v in state.values()), default=1)

    if all_done:
        index_status = "completed"
        log("All three agents say COMPLETE in pass 1 AND pass 2. index.md set to 'completed'.", log_file)
    else:
        reopened = any(v.get("status") == "second_round_needed" for v in state.values())
        index_status = "needs-second-pass" if reopened else "in-progress"
        log("Source is not fully done yet.", log_file)

    update_index(REPO_PATH, ISSUE_NUMBER, SOURCE_NAME, CATEGORY, index_status, max_round)
    log("index.md updated.", log_file)
    log(f"Full log: {log_file}", log_file)

    return all_done


if __name__ == "__main__":
    if not os.path.isdir(REPO_PATH):
        print(f"ERROR: REPO_PATH not found: {REPO_PATH}")
        sys.exit(1)
    run_pass2()
