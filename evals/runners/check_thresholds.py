"""CI gate (E2): fail if unsupported claims rise or bid/skip F1 drops past the thresholds in agent/config.yaml."""
import json, sys
from agent.config import cfg

s = json.load(open(sys.argv[1]))["summary"]
th = cfg()["ci_thresholds"]
fails = []
if s["bid_skip"]["f1_bid"] < th["min_bid_f1"]:
    fails.append(f"bid F1 {s['bid_skip']['f1_bid']} < {th['min_bid_f1']}")
ua = s["proposals"]["unsupported_claims_after"] or 0
if ua > th["max_unsupported_after"]:
    fails.append(f"unsupported claims after verification {ua} > {th['max_unsupported_after']}")
if (s["scam_detection"]["recall"] or 0) < th["min_scam_recall"]:
    fails.append(f"scam recall {s['scam_detection']['recall']} < {th['min_scam_recall']}")
print("\n".join(fails) or "thresholds ok")
sys.exit(1 if fails else 0)
