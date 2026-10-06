import os
import sys
from datetime import date
from pathlib import Path

from agents import (
    AGENTS, new_log_file, log, find_decision, find_reason, source_file_path,
    find_completed_sources, read_synthesis_state, write_synthesis_state,
)
from config import REPO_PATH


def synthesis_file_path(agent_key: str) -> str:
    return f"phase1-research/synthesis/{agent_key}.md"


def task_prompt(agent: str, role_file: str, synthesis_file: str,
                new_source_files: list, synthesis_exists: bool,
                round_no: int, attempt_no: int, reason: str) -> str:
    file_list = "\n".join(f"- {f}" for f in new_source_files)

    if synthesis_exists:
        step1 = (
            f"1. FIRST read your own existing synthesis file ({synthesis_file}) "
            f"from start to end. See which patterns, usable features and gaps "
            f"you noted in earlier rounds."
        )
    else:
        step1 = (
            f"1. Your synthesis file does not exist yet ({synthesis_file}), skip "
            f"this step, you are starting from scratch."
        )

    attempt_note = ""
    if attempt_no > 1:
        attempt_note = (
            f"\nThis is attempt {attempt_no} for round {round_no} (you are continuing "
            f"on the same list of sources, the previous attempt did not finish). "
            f"Focus on the part you could not finish last time: {reason}\n"
        )

    return f"""AGENT: {agent}
ROLE FILE: {role_file}
TASK TYPE: SYNTHESIS
ROUND: {round_no}

STEPS (in this order):
{step1}
2. THEN read the NEW source files below (these are YOUR past analyses,
   {len(new_source_files)} of them; do not read the other agents' files,
   only the ones in this list):
{file_list}
{attempt_note}
TASK:
From your own lens (staying true to your role file), pull out two kinds of
observations:

A) RECURRING PATTERNS: Structural/thematic patterns that repeat across more
   than one source, at least 3-5 of them. Show each one with a concrete
   example of how you saw it in which source(s).

B) USABLE FEATURES FOR WORLDBUILDING: If a concept/institution/mechanism/
   image is strong and original enough on its own, note it even if it shows
   up in ONLY ONE source. The test here is NOT repetition, it is this
   question: "Is this a usable feature for building a world?" If yes, keep
   it even if it does not repeat, so it is not lost.

Also:
C) Note which themes now look saturated (adding new sources gives less and less).
D) Note where data is still thin or missing.

E) (OPTIONAL) For one of the gaps above, you may use your own web search
   tool to suggest a concrete work/book. If you find nothing, leave this
   section empty, that is fine.

Do not read the other agents' files, this must be a synthesis fully
independent and from your own lens. OUTPUT IS ALWAYS IN ENGLISH. Do not
add a separate list of scanned sources, only analysis.

OUTPUT FORMAT AND FILE UPDATE RULE (VERY IMPORTANT):
This file is a GROWING archive, no round overwrites the earlier rounds. If
the file already exists (you read it in step 1), DO NOT CHANGE OR DELETE
ANY OF ITS CONTENT. Only add this to the VERY END of the file:

--------------------

## Round {round_no} Synthesis ({date.today().isoformat()}, {len(new_source_files)} new sources this round)

### Recurring Patterns
[item A]

### Usable Features for Worldbuilding
[item B]

### Saturated Themes
[item C]

### Open Areas / Gaps
[item D]

### Source Suggestions for Gaps (optional, may be empty)
[item E if any; format: "Work title - which gap it fills, one sentence". Otherwise write "No suggestion this round."]

If the file does not exist at all (your first round), write the
`## Round {round_no} Synthesis...` section above as the whole file
(WITHOUT the leading `--------------------` separator).

OUTPUT:
- Write the file to: {synthesis_file}
- There is no GitHub issue for this task, you do not need `gh`.
- At the VERY END of your answer (this last message to me), on a separate
  line, add one of these. This is REQUIRED FOR THE TASK TO COUNT:
  DECISION: COMPLETE
  or
  DECISION: SECOND_ROUND_NEEDED
  REASON: [one sentence, which source(s) or part could not be processed]

  WARNING: If you leave this line out, the script cannot record your work
  as complete and next time it will GIVE YOU ALL THE SAME SOURCES AGAIN,
  so your work is lost and has to be repeated. Do not end your answer
  with a closing line like "ready" or "waiting", the last line must be
  the DECISION block.
"""


def run_synthesis() -> bool:
    log_file = new_log_file("synthesis")
    log("=== Synthesis round starting ===", log_file)

    completed_sources = find_completed_sources(REPO_PATH)
    log(f"Completed sources: {len(completed_sources)}", log_file)

    synthesis_state = read_synthesis_state(REPO_PATH)
    all_up_to_date = True

    for agent, role_file, run_fn in AGENTS:
        agent_key = agent.lower()
        record = synthesis_state.get(agent_key, {})
        processed = set(record.get("processed_sources", []))
        new_sources = [s for s in completed_sources if s not in processed]

        if not new_sources:
            log(f"{agent}: no new sources, synthesis up to date, skipping.", log_file)
            continue

        synthesis_file = synthesis_file_path(agent_key)
        synthesis_exists = (Path(REPO_PATH) / synthesis_file).exists()

        continuing = record.get("status") == "second_round_needed"
        attempt_no = (record.get("attempt", 0) + 1) if continuing else 1
        reason = record.get("reason", "") if continuing else ""
        round_no = record.get("successful_rounds", 0) + 1

        new_source_files = [source_file_path(s, agent_key) for s in new_sources]

        prompt = task_prompt(agent, role_file, synthesis_file, new_source_files,
                             synthesis_exists, round_no, attempt_no, reason)
        ok, output = run_fn(prompt, REPO_PATH, log_file, agent_name=agent)

        decision = find_decision(output)
        new_reason = find_reason(output) if decision == "SECOND_ROUND_NEEDED" else ""

        if decision == "COMPLETE":
            record["processed_sources"] = sorted(processed | set(new_sources))
            record["successful_rounds"] = round_no
            record["attempt"] = 0
            record["status"] = "complete"
            record["reason"] = ""
        elif decision == "SECOND_ROUND_NEEDED":
            record["attempt"] = attempt_no
            record["status"] = "second_round_needed"
            record["reason"] = new_reason
            all_up_to_date = False
        else:
            record["status"] = "unclear"
            all_up_to_date = False

        synthesis_state[agent_key] = record
        write_synthesis_state(REPO_PATH, synthesis_state)

        processed_count = len(record.get("processed_sources", []))
        log(f"{agent}: {'ran' if ok else 'failed'} | round {round_no} (attempt {attempt_no}) | "
            f"DECISION: {decision} | processed: {processed_count}/{len(completed_sources)}", log_file)

    log("=== Synthesis round finished ===", log_file)
    if all_up_to_date:
        log("All agents are up to date. See phase1-research/synthesis/.", log_file)
    else:
        log("At least one agent did not finish. Run synthesis.py again.", log_file)
    log(f"Full log: {log_file}", log_file)

    return all_up_to_date


if __name__ == "__main__":
    if not os.path.isdir(REPO_PATH):
        print(f"ERROR: REPO_PATH not found: {REPO_PATH}")
        sys.exit(1)
    run_synthesis()
