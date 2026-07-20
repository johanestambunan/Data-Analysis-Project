"""Prepare hourly and daily files for the Streamlit dashboard."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


NUMERIC_COLUMNS = [
    "Global_active_power",
    "Global_reactive_power",
    "Voltage",
    "Global_intensity",
    "Sub_metering_1",
    "Sub_metering_2",
    "Sub_metering_3",
]


def prepare_data(input_path: Path, output_dir: Path) -> dict:
    """Clean minute-level data and export hourly/daily aggregates."""
    output_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(input_path, na_values="?", low_memory=False)

    for column in NUMERIC_COLUMNS:
        df[column] = pd.to_numeric(df[column], errors="coerce")

    df["datetime"] = pd.to_datetime(
        df["Date"] + " " + df["Time"],
        format="%d/%m/%Y %H:%M:%S",
        errors="coerce",
    )

    df = (
        df.drop(columns=["Date", "Time"])
        .dropna(subset=["datetime"])
        .drop_duplicates(subset=["datetime"])
        .set_index("datetime")
        .sort_index()
    )

    missing = df["Global_active_power"].isna()
    missing_group = missing.ne(missing.shift()).cumsum()
    run_size = missing.groupby(missing_group).transform("sum")
    short_gap = missing & (run_size <= 60)

    interpolated = df[NUMERIC_COLUMNS].interpolate(
        method="time",
        limit_direction="both",
    )
    df.loc[short_gap, NUMERIC_COLUMNS] = interpolated.loc[
        short_gap, NUMERIC_COLUMNS
    ]
    df["was_imputed"] = short_gap.astype(int)

    df["energy_kwh"] = df["Global_active_power"] / 60
    for meter in (1, 2, 3):
        df[f"sub_metering_{meter}_kwh"] = (
            df[f"Sub_metering_{meter}"] / 1000
        )

    df["other_energy_kwh"] = (
        df["energy_kwh"]
        - df["sub_metering_1_kwh"]
        - df["sub_metering_2_kwh"]
        - df["sub_metering_3_kwh"]
    ).clip(lower=0)

    aggregation = {
        "Global_active_power": "mean",
        "Global_reactive_power": "mean",
        "Voltage": "mean",
        "Global_intensity": "mean",
        "energy_kwh": "sum",
        "sub_metering_1_kwh": "sum",
        "sub_metering_2_kwh": "sum",
        "sub_metering_3_kwh": "sum",
        "other_energy_kwh": "sum",
        "was_imputed": "sum",
    }

    hourly = df.resample("h").agg(aggregation)
    hourly["observed_minutes"] = (
        df["Global_active_power"].resample("h").count()
    )
    hourly["coverage_pct"] = hourly["observed_minutes"] / 60 * 100
    hourly["year"] = hourly.index.year
    hourly["month"] = hourly.index.month
    hourly["month_name"] = hourly.index.month_name().str[:3]
    hourly["day_name"] = hourly.index.day_name()
    hourly["hour"] = hourly.index.hour
    hourly["day_type"] = np.where(
        hourly.index.dayofweek >= 5, "Weekend", "Weekday"
    )

    daily = df.resample("D").agg(aggregation)
    daily["observed_minutes"] = (
        df["Global_active_power"].resample("D").count()
    )
    daily["coverage_pct"] = daily["observed_minutes"] / 1440 * 100
    daily["year"] = daily.index.year
    daily["month"] = daily.index.month
    daily["month_name"] = daily.index.month_name().str[:3]
    daily["day_name"] = daily.index.day_name()
    daily["day_type"] = np.where(
        daily.index.dayofweek >= 5, "Weekend", "Weekday"
    )

    complete = daily["coverage_pct"] >= 95
    q1 = daily.loc[complete, "energy_kwh"].quantile(0.25)
    q3 = daily.loc[complete, "energy_kwh"].quantile(0.75)
    iqr = q3 - q1
    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr

    daily["anomaly_status"] = "Normal"
    daily.loc[~complete, "anomaly_status"] = "Low coverage"
    daily.loc[
        complete & (daily["energy_kwh"] > upper),
        "anomaly_status",
    ] = "High usage"
    daily.loc[
        complete & (daily["energy_kwh"] < lower),
        "anomaly_status",
    ] = "Low usage"

    hourly.reset_index().to_csv(
        output_dir / "electricity_hourly.csv", index=False
    )
    daily.reset_index().to_csv(
        output_dir / "electricity_daily.csv", index=False
    )

    summary = {
        "rows": int(len(df)),
        "start": df.index.min().isoformat(),
        "end": df.index.max().isoformat(),
        "raw_missing_rows": int(missing.sum()),
        "short_gap_rows_imputed": int(short_gap.sum()),
        "remaining_missing_rows": int(
            df["Global_active_power"].isna().sum()
        ),
        "complete_days": int(complete.sum()),
        "low_coverage_days": int((~complete).sum()),
        "iqr_upper_bound_kwh": float(upper),
    }

    with open(
        output_dir / "pipeline_summary.json",
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(summary, file, indent=2)

    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        type=Path,
        default=Path(
            "data/raw/household_power_consumption.csv"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/processed"),
    )
    args = parser.parse_args()

    summary = prepare_data(args.input, args.output)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
