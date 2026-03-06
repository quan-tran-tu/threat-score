"""
Alert Scoring Simulation
========================
Uses past data (up to cutoff) to initialize confidence scores,
then replays live alerts one by one. Each alert is scored on arrival
and printed once. At the end, the full stack is shown sorted by
score (ascending) to evaluate TP/FP separation.
"""

import sys
import time
import pandas as pd
from scorer import AlertScorer, load_config, filter_partial


HEADER_FMT = "{:<4} {:<14} {:>7} {:<5} {}"
ROW_FMT = "{:<4} {:<14} {:>7.4f} {:<5} {}"
SEPARATOR = "-" * 100


def main():
    cfg = load_config()
    data_cfg = cfg["data"]
    data_mode = cfg.get("data_mode", "partial")

    # Load data
    df = pd.read_csv(data_cfg["file"])
    df[data_cfg["datetime_col"]] = pd.to_datetime(
        df[data_cfg["datetime_col"]], format="mixed"
    )
    df = df.sort_values(data_cfg["datetime_col"]).reset_index(drop=True)

    # Filter to partial data if configured
    if data_mode == "partial":
        df = filter_partial(df)
        print(f"Data mode: partial ({len(df)} rows with organization.name)")
    else:
        print(f"Data mode: full ({len(df)} rows)")

    cutoff = pd.Timestamp(data_cfg["past_cutoff"], tz="UTC")
    past_df = df[df[data_cfg["datetime_col"]] < cutoff]
    live_df = df[df[data_cfg["datetime_col"]] >= cutoff].reset_index(drop=True)

    # Initialize scorer with past data
    scorer = AlertScorer(cfg)
    scorer.ingest_past_data(past_df, cfg)

    print(f"Past data: {len(past_df)} alerts ingested")
    print(f"Live data: {len(live_df)} alerts to simulate")
    print(f"Unique rules in past: {len(scorer.tp_counts)}")
    print()

    # Parse speed argument
    delay = 0.05
    if len(sys.argv) > 1:
        try:
            delay = float(sys.argv[1])
        except ValueError:
            pass

    # Live feed header
    print("=== LIVE ALERT FEED ===")
    print(SEPARATOR)
    print(HEADER_FMT.format("#", "Code", "Score", "Label", "Alert Name"))
    print(SEPARATOR)

    # Simulate live alerts
    stack = []
    for i, row in live_df.iterrows():
        alert_name = row[data_cfg["name_col"]]
        resolution = row[data_cfg["resolution_col"]]
        code = row["code"]
        more_info = row.get("more_information", "")

        # Score before updating (score based on what we know so far)
        pt_score = scorer.score(alert_name, more_info)
        label = "TP" if resolution == data_cfg["tp_value"] else "FP"

        entry = {
            "code": code,
            "name": alert_name,
            "score": pt_score,
            "label": label,
        }
        stack.append(entry)

        step = live_df.index.get_loc(i) + 1
        display_name = alert_name if len(alert_name) <= 65 else alert_name[:62] + "..."
        print(ROW_FMT.format(step, code, pt_score, label, display_name))

        time.sleep(delay)

    # Final sorted stack
    stack.sort(key=lambda e: e["score"])

    print(f"\n{'=' * 100}")
    print("SORTED ALERT STACK (ascending by score)")
    print(SEPARATOR)
    print(HEADER_FMT.format("#", "Code", "Score", "Label", "Alert Name"))
    print(SEPARATOR)

    for idx, entry in enumerate(stack, 1):
        display_name = entry["name"] if len(entry["name"]) <= 65 else entry["name"][:62] + "..."
        print(ROW_FMT.format(idx, entry["code"], entry["score"], entry["label"], display_name))

    # Summary
    print(f"\n{'=' * 100}")
    print("SIMULATION COMPLETE")
    print(f"Total alerts processed: {len(stack)}")
    scores = [e["score"] for e in stack]
    print(f"Score range: {min(scores):.4f} — {max(scores):.4f}")
    print(f"Mean score: {sum(scores)/len(scores):.4f}")

    tp_scores = [e["score"] for e in stack if e["label"] == "TP"]
    fp_scores = [e["score"] for e in stack if e["label"] == "FP"]
    if tp_scores:
        print(f"TP alerts ({len(tp_scores)}): mean={sum(tp_scores)/len(tp_scores):.4f}, "
              f"min={min(tp_scores):.4f}, max={max(tp_scores):.4f}")
    if fp_scores:
        print(f"FP alerts ({len(fp_scores)}): mean={sum(fp_scores)/len(fp_scores):.4f}, "
              f"min={min(fp_scores):.4f}, max={max(fp_scores):.4f}")

    # Threshold analysis
    threshold = cfg.get("threshold", 1.0)
    tp_above = [e for e in stack if e["label"] == "TP" and e["score"] >= threshold]
    tp_below = [e for e in stack if e["label"] == "TP" and e["score"] < threshold]
    fp_above = [e for e in stack if e["label"] == "FP" and e["score"] >= threshold]
    fp_below = [e for e in stack if e["label"] == "FP" and e["score"] < threshold]
    total_tp = len(tp_above) + len(tp_below)
    total_fp = len(fp_above) + len(fp_below)

    print(f"\n--- Threshold Analysis (score >= {threshold}) ---")
    print(f"  TP above: {len(tp_above)}/{total_tp}    TP below: {len(tp_below)}/{total_tp}")
    print(f"  FP above: {len(fp_above)}/{total_fp}    FP below: {len(fp_below)}/{total_fp}")


if __name__ == "__main__":
    main()
