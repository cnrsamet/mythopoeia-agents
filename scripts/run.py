import os
import sys

from agents import new_log_file, log, clean_temp_files
from pass1 import run_pass1
from pass2 import run_pass2
from config import REPO_PATH, SOURCE_NAME, ISSUE_NUMBER

MAX_ROUNDS = 6


def main():
    log_file = new_log_file("run")
    log(f"=== AUTOMATIC RUN STARTING: {SOURCE_NAME} (#{ISSUE_NUMBER}) ===", log_file)

    for round_no in range(1, MAX_ROUNDS + 1):
        log(f"--- Loop {round_no}/{MAX_ROUNDS}: pass 1 ---", log_file)
        if not run_pass1():
            log(f"Pass 1 not finished yet, will retry at the end of loop {round_no}.", log_file)
            continue

        log(f"--- Loop {round_no}/{MAX_ROUNDS}: pass 2 ---", log_file)
        if run_pass2():
            log(f"=== SOURCE FULLY DONE: {SOURCE_NAME} (#{ISSUE_NUMBER}) ===", log_file)
            clean_temp_files(REPO_PATH, log_file)
            return

        log("Pass 2 reopened pass 1 for at least one agent. Continuing.", log_file)

    log(f"=== Tried {MAX_ROUNDS} loops but the source is still not done. ===", log_file)
    log("The agents probably disagree for real. Check the issue and state.json by hand.", log_file)
    clean_temp_files(REPO_PATH, log_file)


if __name__ == "__main__":
    if not os.path.isdir(REPO_PATH):
        print(f"ERROR: REPO_PATH not found: {REPO_PATH}")
        sys.exit(1)
    main()
