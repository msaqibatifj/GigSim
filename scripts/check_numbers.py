"""CI: every number the README cites as `[results: <file>]` must name an existing evals/results file."""
import pathlib, re, sys
root = pathlib.Path(__file__).resolve().parents[1]
bad = [f for f in re.findall(r"\[results: ([\w./-]+)\]", (root / "README.md").read_text(encoding="utf-8") if (root / "README.md").exists() else "")
       if not (root / "evals" / "results" / f).exists()]
print("missing results files:", bad) if bad else print("README numbers trace ok")
sys.exit(1 if bad else 0)
