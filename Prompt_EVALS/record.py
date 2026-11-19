"""Records one test or eval run: runs a command, saves its full output, and adds a row to Prompt_EVALS/RUNS.md.
Usage (from the Faro folder):
    python Prompt_EVALS/record.py <name> "<what it checks>" -- <command ...>
    python Prompt_EVALS/record.py <name> "<what it checks>" --from-file <existing_output.txt> --command "<how it was run>"
Output is saved to Prompt_EVALS/runs/<date>_<number>_<name>.txt. The row shows the result line (pytest summary or the last line printed) and the exit status."""
import datetime as dt
import re
import subprocess
import sys
from pathlib import Path

EVALS = Path(__file__).resolve().parent
ROOT = EVALS.parent
RUNS = EVALS / "RUNS.md"


def next_number() -> int:
    nums = [int(m.group(1)) for m in re.finditer(r"^\| R(\d+) ", RUNS.read_text(encoding="utf-8"), re.M)] if RUNS.exists() else []
    return max(nums, default=0) + 1


def main():
    argv = sys.argv[1:]
    name, what = argv[0], argv[1]
    if "--from-file" in argv:
        src = Path(argv[argv.index("--from-file") + 1])
        cmd_txt = argv[argv.index("--command") + 1] if "--command" in argv else "(recorded from an earlier run)"
        out, code = src.read_text(encoding="utf-8", errors="replace"), 0
    else:
        cmd = argv[argv.index("--") + 1:]
        cmd_txt = " ".join(cmd)
        p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
        out, code = p.stdout + (("\n--- stderr ---\n" + p.stderr) if p.stderr.strip() else ""), p.returncode
    lines = [l for l in out.splitlines() if l.strip() and "Warning" not in l and not l.strip().startswith("flags[name]")]
    summ = next((l.strip() for l in reversed(lines) if re.search(r"\d+ (passed|failed|error)", l)), lines[-1].strip() if lines else "(no output)")
    num = next_number()
    when = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    fname = f"{dt.date.today().isoformat()}_R{num:02d}_{name}.txt"
    (EVALS / "runs").mkdir(exist_ok=True)
    (EVALS / "runs" / fname).write_text(f"# {name}: {what}\n# command: {cmd_txt}\n# when: {when}   exit status: {code}\n\n{out}", encoding="utf-8")
    status = "PASS" if code == 0 and "failed" not in summ and "error" not in summ.lower().split("passed")[0] else "FAIL"
    row = f"| R{num:02d} | {when} | {name} | {what} | `{cmd_txt[:70]}` | {status}: {summ[:110]} | [runs/{fname}](runs/{fname}) |\n"
    if not RUNS.exists():
        RUNS.write_text("# Run log\n\nEvery test or eval run, in order. Full output of each run is in `runs/`. Added automatically by `record.py`.\n\n"
                        "| Run | When | Name | What it checks | Command | Result | Output |\n|---|---|---|---|---|---|---|\n", encoding="utf-8")
    with open(RUNS, "a", encoding="utf-8") as f:
        f.write(row)
    sys.stdout.reconfigure(errors="replace")  # some tools print characters a Windows console cannot show
    print(f"R{num:02d} {status}: {summ}\n  saved {fname}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
