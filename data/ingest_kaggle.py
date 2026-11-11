"""Convert a Kaggle Upwork-postings CSV into jobs.json-style records. Usage: python data/ingest_kaggle.py in.csv owner/slug [out.json]
shortcut: column names are guessed from common spellings, check them once the real CSV is downloaded."""
import csv, json, re, sys, pathlib

COLS = dict(title=("title", "job_title"), description=("description", "job_description", "desc"),
            budget=("budget", "fixed_budget", "budget_usd", "amount"))

def pick(row, names):
    low = {k.lower().strip(): v for k, v in row.items()}
    return next((low[n] for n in names if low.get(n)), "")

def clean(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s or "")).strip()

def ingest(path, slug):
    seen, out = set(), []
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        for i, row in enumerate(csv.DictReader(f)):
            t, d = (clean(pick(row, COLS[k])) for k in ("title", "description"))
            try:
                b = float(re.sub(r"[^\d.]", "", pick(row, COLS["budget"])) or 0)
            except ValueError:
                b = 0
            key = (t + d).lower()
            if not t or not d or b <= 0 or key in seen:
                continue
            seen.add(key)
            out.append(dict(id=f"k{i}", title=t, description=d, budget_usd=b, source=f"kaggle:{slug}"))
    return out

if __name__ == "__main__":
    dst = pathlib.Path(sys.argv[3] if len(sys.argv) > 3 else "data/processed/real_jobs.json")
    dst.write_text(json.dumps(ingest(sys.argv[1], sys.argv[2]), indent=1))

def test_ingest(tmp_path):
    p = tmp_path / "x.csv"
    p.write_text("Title,Description,Budget\nA,<b>hi</b>  there,$100\nA,<b>hi</b>  there,$100\nB,x,0\n,y,5\n")
    r = ingest(p, "o/s")
    assert len(r) == 1 and r[0]["description"] == "hi there" and r[0]["budget_usd"] == 100
