import json
import math
import re
import pandas as pd


SEVERITY_SCORES = {"low": 1, "medium": 4, "high": 7, "critical": 10}
SEVERITY_SCALE = 10


def load_config(path="config.json"):
    with open(path) as f:
        return json.load(f)


def extract_severity(more_info):
    """Extract kibana.alert.severity from more_information field."""
    m = re.search(r'kibana\.alert\.severity:\s*(\w+)', more_info)
    if m:
        return m.group(1).lower()
    return None


def filter_partial(df, info_col="more_information"):
    """Keep only rows where more_information contains organization.name:"""
    mask = df[info_col].str.contains("organization.name:", na=False)
    return df[mask].copy()


class AlertScorer:
    def __init__(self, config):
        w = config["weights"]
        p = config["priors"]
        self.w_E = w["w_E"]
        self.w_C = w["w_C"]
        self.w_S = w["w_S"]
        self.w_V = w["w_V"]
        self.alpha = p["alpha"]
        self.beta = p["beta"]

        # Confidence method: "mean", "wilson", "discount", or "tp_discount"
        conf = config.get("confidence", {})
        self.conf_method = conf.get("method", "mean")
        self.wilson_z = conf.get("wilson_z", 1.96)
        self.discount_k = conf.get("discount_k", 50)
        self.tp_discount_k = conf.get("tp_discount_k", 10)

        # Data mode: "partial" or "full"
        self.data_mode = config.get("data_mode", "partial")

        # Cumulative TP/FP counts per rule name
        self.tp_counts = {}
        self.fp_counts = {}

    def ingest_past_data(self, df, cfg):
        """Build initial TP/FP counts from historical data."""
        name_col = cfg["data"]["name_col"]
        res_col = cfg["data"]["resolution_col"]
        tp_val = cfg["data"]["tp_value"]
        fp_val = cfg["data"]["fp_value"]

        for name, group in df.groupby(name_col):
            self.tp_counts[name] = (group[res_col] == tp_val).sum()
            self.fp_counts[name] = (group[res_col] == fp_val).sum()

    def _mean_confidence(self, tp, fp):
        """Beta posterior mean: (TP + α) / (TP + FP + α + β)"""
        return (tp + self.alpha) / (tp + fp + self.alpha + self.beta)

    def _wilson_confidence(self, tp, fp):
        """Wilson score lower bound on TP rate."""
        n = tp + fp
        if n == 0:
            return 0.0
        p_hat = tp / n
        z = self.wilson_z
        z2 = z * z
        denom = 1 + z2 / n
        centre = p_hat + z2 / (2 * n)
        spread = z * math.sqrt(p_hat * (1 - p_hat) / n + z2 / (4 * n * n))
        return max(0.0, (centre - spread) / denom)

    def _discount_confidence(self, tp, fp):
        """Beta posterior mean discounted by sample size. Falls back to prior when n=0."""
        n = tp + fp
        if n == 0:
            return self.alpha / (self.alpha + self.beta)
        mean = self._mean_confidence(tp, fp)
        return mean * n / (n + self.discount_k)

    def _tp_discount_confidence(self, tp, fp):
        """Beta posterior mean discounted by TP count only. Returns 0 when unseen."""
        if tp + fp == 0:
            return 0.0
        mean = self._mean_confidence(tp, fp)
        return mean * tp / (tp + self.tp_discount_k)

    def confidence(self, rule_name):
        tp = self.tp_counts.get(rule_name, 0)
        fp = self.fp_counts.get(rule_name, 0)
        if self.conf_method == "wilson":
            return self._wilson_confidence(tp, fp)
        elif self.conf_method == "discount":
            return self._discount_confidence(tp, fp)
        elif self.conf_method == "tp_discount":
            return self._tp_discount_confidence(tp, fp)
        else:
            return self._mean_confidence(tp, fp)

    def severity_score(self, more_info):
        """Return S(a) on 0-10 scale based on kibana.alert.severity."""
        if self.data_mode != "partial":
            return 1
        sev = extract_severity(more_info)
        if sev is None:
            return 1
        return SEVERITY_SCORES.get(sev, 1)

    def score(self, alert_name, more_info=""):
        """
        PT(a, t) = L(a, t) * I(a) * 10 * M(a)
        L(a, t) = w_E * E(a) + w_C * C_r(t)
        I(a) = w_S * S(a) + w_V * V(a)
        E(a) = V(a) = 1 for now
        """
        E = 1.0
        V = 5.0     # Asset value
        M = 1.0     # Mitigation factor
        S = self.severity_score(more_info)
        C_r = self.confidence(alert_name)
        L = self.w_E * E + self.w_C * C_r
        I = self.w_S * S + self.w_V * V
        return round(L * I * 10 * M, 4)

    def update(self, alert_name, resolution_code, tp_value="HT", fp_value="FPAlert"):
        """Update cumulative counts after an alert is resolved."""
        if resolution_code == tp_value:
            self.tp_counts[alert_name] = self.tp_counts.get(alert_name, 0) + 1
        elif resolution_code == fp_value:
            self.fp_counts[alert_name] = self.fp_counts.get(alert_name, 0) + 1
