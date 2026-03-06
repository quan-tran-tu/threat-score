# Alert Scoring System

Scores SOAR alerts using historical TP/FP data to prioritize which alerts an analyst should investigate first.

## Formula

```
PT(a, t) = L(a, t) × I(a) × 10

L(a, t) = w_E × E(a) + w_C × C_r(t)
I(a)    = w_S × S(a) + w_V × V(a)
```

- `E(a)` — evidence score (hardcoded to 1.0)
- `C_r(t)` — confidence score for rule name `r`, based on historical TP/FP ratio
- `S(a)` — severity score (from `kibana.alert.severity` in partial mode)
- `V(a)` — vulnerability score (hardcoded to 5.0)

## Run

```bash
.venv/Scripts/python.exe simulate.py          # animated (0.05s delay)
.venv/Scripts/python.exe simulate.py 0        # instant
.venv/Scripts/python.exe simulate.py 0.2      # slower
```

## Config (`config.json`)

### `weights`

Controls relative importance of each factor. Each pair must sum to 1.

| Key   | Description                          | Constraint     |
|-------|--------------------------------------|----------------|
| `w_E` | Weight for evidence `E(a)`           | `w_E + w_C = 1`|
| `w_C` | Weight for confidence `C_r(t)`       | `w_E + w_C = 1`|
| `w_S` | Weight for severity `S(a)`           | `w_S + w_V = 1`|
| `w_V` | Weight for vulnerability `V(a)`      | `w_S + w_V = 1`|

### `priors`

Bayesian priors for the Beta distribution used in confidence calculation.

| Key     | Description                        | Default |
|---------|------------------------------------|---------|
| `alpha` | Prior weight for TP (pseudocount)  | `1`     |
| `beta`  | Prior weight for FP (pseudocount)  | `1`     |

With `alpha=1, beta=1`, a rule with no history starts at 0.5 confidence (used by `mean` and `discount` methods).

### `confidence`

Controls how the confidence score `C_r(t)` is calculated.

| Key             | Description                                          | Default  |
|-----------------|------------------------------------------------------|----------|
| `method`        | One of `mean`, `wilson`, `discount`, `tp_discount`   | `"mean"` |
| `wilson_z`      | Z-score for Wilson interval (only for `wilson`)      | `1.96`   |
| `discount_k`    | Sample size threshold (only for `discount`)          | `50`     |
| `tp_discount_k` | TP count threshold (only for `tp_discount`)          | `10`     |

**Methods:**

- **`mean`** — Beta posterior mean: `(TP + α) / (TP + FP + α + β)`. Simple ratio, no sample-size adjustment. Unseen rules get `α / (α + β)`.
- **`wilson`** — Wilson score lower bound on TP rate. Penalizes low sample sizes by widening the confidence interval. Returns 0 for unseen rules.
- **`discount`** — Beta mean multiplied by `n / (n + k)` where `n = TP + FP`. Shrinks confidence for low-sample rules. Falls back to prior for unseen rules.
- **`tp_discount`** — Beta mean multiplied by `TP / (TP + k)`. Confidence only grows with TP evidence. Returns 0 for unseen rules (no TP evidence = no confidence).

### `threshold`

Score threshold for the summary analysis. The simulation reports how many TP and FP alerts fall above/below this value.

| Key         | Description                  | Default |
|-------------|------------------------------|---------|
| `threshold` | Score cutoff for analysis    | `30.0`   |

**Reading the output:**

```
--- Threshold Analysis (score >= 30.0) ---
  TP above: 3/15    TP below: 12/15
  FP above: 173/293    FP below: 120/293
```

- **TP above** � true positives the system would surface to the analyst. Higher is better (catch rate).
- **TP below** � true positives the system would miss. Lower is better.
- **FP above** � false positives the analyst would still have to review. Lower is better.
- **FP below** � false positives correctly filtered out. Higher is better.

**Tuning the threshold:**

| Problem                           | Action                |
|-----------------------------------|-----------------------|
| Too many TPs missed (TP below high) | Lower the threshold |
| Too many FPs surfaced (FP above high) | Raise the threshold |
| Both TP above and FP above are high | Adjust weights or confidence method to better separate TP from FP before changing threshold |

### `data_mode`

| Value     | Description                                                                 |
|-----------|-----------------------------------------------------------------------------|
| `partial` | Only process rows where `more_information` contains `organization.name:`. Extracts `kibana.alert.severity` to set `S(a)`: low=1, medium=4, high=7, critical=10. |
| `full`    | Process all rows. `S(a)` defaults to 1.0.                                  |

### `data`

| Key              | Description                                    |
|------------------|------------------------------------------------|
| `file`           | Path to the CSV data file                      |
| `past_cutoff`    | Date string (e.g. `"2026-01-31"`). Data before this is used to build the confidence model. Data on/after this is live simulation. |
| `datetime_col`   | Column name for alert timestamp                |
| `name_col`       | Column name for the alert/rule name            |
| `resolution_col` | Column name for TP/FP label                    |
| `tp_value`       | Value in `resolution_col` that means TP        |
| `fp_value`       | Value in `resolution_col` that means FP        |
