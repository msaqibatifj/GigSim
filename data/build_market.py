"""Build the GigSim job feed and market statistics from the real Kaggle datasets (see docs/DATA_CARD.md).
Run: python -m data.build_market   (needs data/raw/<owner>__<slug>/ from `make data`)

Outputs (small, committed; every record carries "source"):
  data/mock_market/real_jobs.json     real postings + real client signals, mapped to the 3 personas
  data/mock_market/real_clients.json  client histories derived from those postings' client columns
  data/market/market_stats.json       budget / hourly-rate percentiles per category (pricing node)
  evals/datasets/scam_external.json   labelled fake/real postings, LOCAL EVAL ONLY (license unknown)"""
import hashlib, json, pathlib, re
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
SRC60 = "kaggle:ahmedmyalo/upwork-freelance-jobs-60k"
SRC50 = "kaggle:asaniczka/upwork-job-postings-dataset-2024-50k-records"
SRCC = "kaggle:asaniczka/freelance-contracts-dataset-1-3-million-entries"
SRCF = "kaggle:adityammantri/trial-1"
PER_PERSONA = 40

# persona -> (keyword regex on title+categories, category label used for market stats)
PERSONAS = {
    "ayesha_ml": (r"(?:machine learning|nlp|natural language|llm|chatbot|gpt|langchain|rag|deep learning|pytorch|ai model|computer vision)\b", "ml_nlp"),
    "bilal_web": (r"(?:react|next\.?js|typescript|frontend|front-end|full.?stack|node\.?js|web app)\b", "web"),
    "sara_data": (r"(?:data analy|dashboard|power bi|tableau|sql|etl|data visuali|bigquery|dbt|excel report)\b", "data"),
}


def money(s) -> float:
    m = re.findall(r"[\d.]+", str(s).replace(",", ""))
    return float(m[0]) if m else 0.0


def clean(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", str(s or ""))
    s = re.sub(r"[\w.+-]+@[\w-]+\.[\w.]+", "[email]", s)            # PII never enters the feed
    s = re.sub(r"\+?\d[\d\s().-]{8,}\d", "[phone]", s)
    return re.sub(r"\s+", " ", s.replace("�", "'")).strip()


def _id(prefix, text):
    return prefix + hashlib.sha1(text.encode()).hexdigest()[:8]


def build_feed():
    k = pd.read_csv(RAW / "ahmedmyalo__upwork-freelance-jobs-60k" / "Final_Upwork_Dataset.csv", low_memory=False)
    k = k[(k.Payment_type == "Fixed-price") & k.Description.str.len().between(200, 3000)].copy()
    k["cost"] = k.Job_Cost.map(money)
    k = k[k.cost >= 50].drop_duplicates(subset=["Description"])
    cats = k[[c for c in k.columns if c.startswith("Category_")]].fillna("").astype(str).agg(" ".join, axis=1)
    k["hay"] = (k["Job Title"].astype(str) + " " + cats).str.lower()
    jobs, clients = [], []
    for persona, (rx, cat) in PERSONAS.items():
        sub = k[k.hay.str.contains(rx, regex=True)].sample(frac=1, random_state=7).head(PER_PERSONA)
        for _, r in sub.iterrows():
            jid = _id("k", r["Description"])
            cid = "c_" + jid
            jobs.append(dict(id=jid, title=clean(r["Job Title"])[:120], description=clean(r["Description"]), budget_usd=r.cost,
                             client_id=cid, posted_at="2024-01-01", category=cat, persona_hint=persona,
                             connects_cost=int(r.Connects_Num) if pd.notna(r.Connects_Num) else 6,
                             applicants=str(r.Applicants_Num), source=SRC60))
            fb = int(r.Feedback_Num) if pd.notna(r.Feedback_Num) else 0
            rating = float(r.Rating) if pd.notna(r.Rating) else None
            clients.append(dict(client_id=cid, total_spent_usd=float(r["Spent($)"] or 0),
                                hire_rate=min(1.0, 0.3 + 0.1 * min(fb, 7)) if fb else 0.0,   # derived: dataset has no hire rate
                                payment_verified=r.Payment_Situation == "Payment verified",
                                reviews=[f"Average rating {rating:.2f} from {fb} reviews"] if rating and fb else [],
                                country=str(r.Client_Country), source=SRC60 + " (hire_rate derived from Feedback_Num)"))
    return jobs, clients


def build_stats():
    stats = {}
    j = pd.read_csv(RAW / "asaniczka__upwork-job-postings-dataset-2024-50k-records" / "upwork-jobs.csv")
    j["text"] = (j.title.astype(str) + " " + j.description.astype(str)).str.lower()
    c = pd.read_csv(RAW / "asaniczka__freelance-contracts-dataset-1-3-million-entries" / "contracts.csv",
                    usecols=["job_title", "hourly_rate", "total_paid"])
    c = c[c.hourly_rate.between(3, 300)]
    c["t"] = c.job_title.astype(str).str.lower()
    for persona, (rx, cat) in PERSONAS.items():
        fixed = j[j.text.str.contains(rx, regex=True) & (j.is_hourly == False) & (j.budget > 0)].budget   # noqa: E712
        hourly = c[c.t.str.contains(rx, regex=True)].hourly_rate
        stats[cat] = {
            "fixed_budget_usd": {p: round(float(fixed.quantile(p / 100)), 0) for p in (25, 50, 75)} | {"n": int(len(fixed))},
            "hourly_rate_usd": {p: round(float(hourly.quantile(p / 100)), 1) for p in (25, 50, 75)} | {"n": int(len(hourly))},
            "sources": [SRC50, SRCC]}
    return stats


def build_scam_eval(n=300):
    f = pd.read_excel(RAW / "adityammantri__trial-1" / "processed_labeled_dataset_without_encoding.xlsx")
    f = f.dropna(subset=["fraudulent", "job_desc"])
    out = pd.concat([f[f.fraudulent == 1].sample(n // 2, random_state=1), f[f.fraudulent == 0].sample(n // 2, random_state=1)])
    return [dict(id=f"x{i}", title=str(r.job_title), description=clean(f"{r.job_desc} {r.skills_desc}"), fraudulent=bool(r.fraudulent),
                 source=SRCF + " (license unknown: local eval only)") for i, (_, r) in enumerate(out.iterrows())]


if __name__ == "__main__":
    jobs, clients = build_feed()
    (ROOT / "data" / "mock_market" / "real_jobs.json").write_text(json.dumps(jobs, indent=1))
    (ROOT / "data" / "mock_market" / "real_clients.json").write_text(json.dumps(clients, indent=1))
    (ROOT / "data" / "market").mkdir(exist_ok=True)
    (ROOT / "data" / "market" / "market_stats.json").write_text(json.dumps(build_stats(), indent=1))
    (ROOT / "evals" / "datasets" / "scam_external.json").write_text(json.dumps(build_scam_eval(), indent=1))
    print(f"{len(jobs)} real jobs, {len(clients)} clients; stats + scam eval written")


def test_clean_masks_pii():
    assert clean("<b>mail</b> a.b@x.com or +1 (555) 123-4567 now") == "mail [email] or [phone] now"
    assert money("$1,000 ") == 1000.0
