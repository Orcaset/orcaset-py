import pandas as pd
from pathlib import Path
from orcaset import Period, span, sum_spans
from dateutil.relativedelta import relativedelta
from datetime import date

_data_dir = Path(__file__).resolve().parent.parent / "data"


def period_from_end(column: str) -> Period:
    end = date.fromisoformat(column)
    return Period(end - relativedelta(months=3, day=31), end)


def series_for_metric(
    metric: str, df: pd.DataFrame, label: str | None = None
) -> span.SpanSeriesDef:
    values = df.loc[metric].to_dict()
    formatted_values = [(period_from_end(str(dt)), val) for dt, val in values.items()]
    return span.from_list(
        formatted_values,
        agg=sum_spans(0.0),
        label=label or metric,
    )


# --------------- METRICS DATA ---------------
metrics_data = pd.read_csv(_data_dir / "MNDY-metrics.csv", header=0, index_col=0)

group_keys = ("<10 users", "10+ users", "50k+ ARR", "100k+ ARR", "500k+ ARR")

# Historical period anchors used by the projection modules.
hist_start = period_from_end(min(metrics_data.columns, key=date.fromisoformat)).start
last_hist_period = period_from_end(max(metrics_data.columns, key=date.fromisoformat))

# Total Paying Customers is only disclosed annually (zeros elsewhere); interpolate the
# missing quarters so the "<10 users" customer slice is meaningful at every quarter end.
_tpc = pd.Series(
    {
        column: float(value) if value else float("nan")
        for column, value in metrics_data.loc["Total Paying Customers"].to_dict().items()
    }
)
metrics_data.loc["Total Paying Customers"] = _tpc.interpolate().ffill().bfill()

# Customer counts and percent ARR are cumulative thresholds; subtract higher bands for each slice.
metrics_data.loc["Customers | 500k+ ARR"] = metrics_data.loc[
    "Number of Customers w/ >500K Annual Recurring Revenue (ARR)"
]
metrics_data.loc["Customers | 100k+ ARR"] = (
    metrics_data.loc["Number of Customers w/ >100K Annual Recurring Revenue (ARR)"]
    - metrics_data.loc["Customers | 500k+ ARR"]
)
metrics_data.loc["Customers | 50k+ ARR"] = (
    metrics_data.loc["Number of Customers w/ >50K Annual Recurring Revenue (ARR)"]
    - metrics_data.loc["Customers | 100k+ ARR"]
    - metrics_data.loc["Customers | 500k+ ARR"]
)
metrics_data.loc["Customers | 10+ users"] = (
    metrics_data.loc["Number of Customers w/ 10+ Users"]
    - metrics_data.loc["Customers | 50k+ ARR"]
    - metrics_data.loc["Customers | 100k+ ARR"]
    - metrics_data.loc["Customers | 500k+ ARR"]
)
metrics_data.loc["Customers | <10 users"] = (
    metrics_data.loc["Total Paying Customers"]
    - metrics_data.loc["Number of Customers w/ 10+ Users"]
)

metrics_data.loc["Pct ARR | 500k+ ARR"] = metrics_data.loc[
    "Percent of Annual Recurring Revenue (ARR) from Customers w/ > 500K ARR"
]
metrics_data.loc["Pct ARR | 100k+ ARR"] = (
    metrics_data.loc["Percent of Annual Recurring Revenue (ARR) from Customers w/ >100K ARR"]
    - metrics_data.loc["Pct ARR | 500k+ ARR"]
)
metrics_data.loc["Pct ARR | 50k+ ARR"] = (
    metrics_data.loc["Percent of Annual Recurring Revenue (ARR) from Customers w/ >50K ARR"]
    - metrics_data.loc["Pct ARR | 100k+ ARR"]
    - metrics_data.loc["Pct ARR | 500k+ ARR"]
)
metrics_data.loc["Pct ARR | 10+ users"] = (
    metrics_data.loc["Percent of Annual Recurring Revenue (ARR) from Customers w/ 10+ Users"]
    - metrics_data.loc["Pct ARR | 50k+ ARR"]
    - metrics_data.loc["Pct ARR | 100k+ ARR"]
    - metrics_data.loc["Pct ARR | 500k+ ARR"]
)
metrics_data.loc["Pct ARR | <10 users"] = (
    100 - metrics_data.loc["Percent of Annual Recurring Revenue (ARR) from Customers w/ 10+ Users"]
)


def series_for_group(metric: str, group: str, df: pd.DataFrame) -> span.SpanSeriesDef:
    return series_for_metric(f"{metric} | {group}", df)


hist_metrics = {
    "customers": {
        group: series_for_group("Customers", group, metrics_data) for group in group_keys
    },
    "pct_arr": {group: series_for_group("Pct ARR", group, metrics_data) for group in group_keys},
    "ndr": {
        "<10 users": series_for_metric(
            "Net Dollar Retention Rate (NDR) for All Customers", metrics_data
        ),
        "10+ users": series_for_metric(
            "Net Dollar Retention Rate (NDR) for Customers w/ 10+ Users", metrics_data
        ),
        "50k+ ARR": series_for_metric(
            "Net Dollar Retention Rate (NDR) for >50K ARR Customers", metrics_data
        ),
        "100k+ ARR": series_for_metric(
            "Net Dollar Retention Rate (NDR) for >100K ARR Customers", metrics_data
        ),
        "500k+ ARR": series_for_metric(
            "Net Dollar Retention Rate (NDR) for >100K ARR Customers", metrics_data
        ),
    },
    "pct_arr_new_products": series_for_metric(
        "Percent of Annual Recurring Revenue (ARR) from New Products", metrics_data
    ),
    "total_paying_customers": series_for_metric("Total Paying Customers", metrics_data),
}

# --------------- REVENUE DATA ---------------
revenue_data = pd.read_csv(_data_dir / "MNDY-revenue.csv", header=0, index_col=0)

# Estimate revenue by size group using total revenue and percentage of ARR by size group.
# Percent metrics are cumulative thresholds; subtract higher bands to get each slice.
# Assumes all 10+ users are less than $50k ARR, all 50k+ ARR users are less than $100k ARR, etc.
revenue_data.loc["500k+ ARR"] = (
    revenue_data.loc["Revenue"]
    * metrics_data.loc["Percent of Annual Recurring Revenue (ARR) from Customers w/ > 500K ARR"]
    / 100
)
revenue_data.loc["100k+ ARR"] = (
    revenue_data.loc["Revenue"]
    * metrics_data.loc["Percent of Annual Recurring Revenue (ARR) from Customers w/ >100K ARR"]
    / 100
    - revenue_data.loc["500k+ ARR"]
)
revenue_data.loc["50k+ ARR"] = (
    revenue_data.loc["Revenue"]
    * metrics_data.loc["Percent of Annual Recurring Revenue (ARR) from Customers w/ >50K ARR"]
    / 100
    - revenue_data.loc["100k+ ARR"]
    - revenue_data.loc["500k+ ARR"]
)
revenue_data.loc["10+ users"] = (
    revenue_data.loc["Revenue"]
    * metrics_data.loc["Percent of Annual Recurring Revenue (ARR) from Customers w/ 10+ Users"]
    / 100
    - revenue_data.loc["50k+ ARR"]
    - revenue_data.loc["100k+ ARR"]
    - revenue_data.loc["500k+ ARR"]
)
revenue_data.loc["<10 users"] = revenue_data.loc["Revenue"] * (
    1
    - metrics_data.loc["Percent of Annual Recurring Revenue (ARR) from Customers w/ 10+ Users"]
    / 100
)


hist_revenue = {
    group: series_for_metric(group, revenue_data, label=f"Revenue | {group}")
    for group in group_keys
}
