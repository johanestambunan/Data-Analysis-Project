from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data" / "processed"

st.set_page_config(
    page_title="Household Electricity Analytics",
    page_icon="⚡",
    layout="wide",
)

st.markdown(
    """
    <style>
        .block-container {
            padding-top: 1.4rem;
            padding-bottom: 2rem;
            max-width: 1450px;
        }
        [data-testid="stMetric"] {
            border: 1px solid rgba(128, 128, 128, 0.22);
            border-radius: 14px;
            padding: 14px 16px;
        }
        div[data-testid="stMetricValue"] {
            font-size: 1.65rem;
        }
        .section-note {
            color: #6b7280;
            font-size: 0.93rem;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data
def load_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    daily_path = DATA_DIR / "electricity_daily.csv"
    hourly_path = DATA_DIR / "electricity_hourly.csv"

    if not daily_path.exists() or not hourly_path.exists():
        raise FileNotFoundError(
            "Processed files are missing. Run "
            "`python src/data_pipeline.py` first."
        )

    daily = pd.read_csv(daily_path, parse_dates=["datetime"])
    hourly = pd.read_csv(hourly_path, parse_dates=["datetime"])
    return daily, hourly


def format_number(value: float, decimals: int = 1) -> str:
    return f"{value:,.{decimals}f}"


def aggregate_trend(
    frame: pd.DataFrame,
    frequency: str,
) -> pd.DataFrame:
    frame = frame.set_index("datetime")
    if frequency == "Daily":
        output = frame[["energy_kwh"]].resample("D").sum(
            min_count=1
        )
    elif frequency == "Weekly":
        output = frame[["energy_kwh"]].resample("W").sum(
            min_count=1
        )
    else:
        output = frame[["energy_kwh"]].resample("ME").sum(
            min_count=1
        )

    return output.dropna().reset_index()


try:
    daily, hourly = load_data()
except FileNotFoundError as error:
    st.error(str(error))
    st.stop()

st.title("⚡ Household Electricity Analytics")
st.markdown(
    """
    Explore household electricity consumption patterns, peak-load periods,
    equipment-level energy shares, anomalies, and data quality.
    """
)
st.caption(
    "Portfolio dataset: 1,048,575 one-minute observations from "
    "16 December 2006 to 13 December 2008."
)

# ------------------------------------------------------------------
# Sidebar filters
# ------------------------------------------------------------------
with st.sidebar:
    st.header("Dashboard controls")

    min_date = daily["datetime"].min().date()
    max_date = daily["datetime"].max().date()
    selected_dates = st.date_input(
        "Date range",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date,
    )

    if isinstance(selected_dates, tuple) and len(selected_dates) == 2:
        start_date, end_date = selected_dates
    else:
        start_date, end_date = min_date, max_date

    selected_day_types = st.multiselect(
        "Day type",
        options=["Weekday", "Weekend"],
        default=["Weekday", "Weekend"],
    )

    minimum_coverage = st.slider(
        "Minimum daily coverage",
        min_value=0,
        max_value=100,
        value=95,
        step=5,
        format="%d%%",
        help=(
            "Coverage is the percentage of expected minute-level "
            "observations available for a day."
        ),
    )

    trend_frequency = st.selectbox(
        "Trend aggregation",
        options=["Daily", "Weekly", "Monthly"],
        index=0,
    )

    st.divider()
    st.subheader("Cost simulator")
    currency_symbol = st.text_input(
        "Currency symbol",
        value="€",
        max_chars=4,
    )
    tariff = st.number_input(
        "Cost per kWh",
        min_value=0.0,
        value=0.20,
        step=0.01,
        format="%.2f",
    )

start_ts = pd.Timestamp(start_date)
end_ts = pd.Timestamp(end_date) + pd.Timedelta(days=1)

daily_filtered = daily[
    (daily["datetime"] >= start_ts)
    & (daily["datetime"] < end_ts)
    & (daily["day_type"].isin(selected_day_types))
    & (daily["coverage_pct"] >= minimum_coverage)
].copy()

hourly_filtered = hourly[
    (hourly["datetime"] >= start_ts)
    & (hourly["datetime"] < end_ts)
    & (hourly["day_type"].isin(selected_day_types))
].copy()

if daily_filtered.empty:
    st.warning(
        "No daily observations match the current filters. "
        "Lower the coverage threshold or widen the date range."
    )
    st.stop()

# ------------------------------------------------------------------
# KPI cards
# ------------------------------------------------------------------
total_energy = daily_filtered["energy_kwh"].sum()
average_daily = daily_filtered["energy_kwh"].mean()
peak_row = daily_filtered.loc[
    daily_filtered["energy_kwh"].idxmax()
]
estimated_cost = total_energy * tariff
anomaly_count = (
    daily_filtered["anomaly_status"] == "High usage"
).sum()

kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)
kpi1.metric("Total energy", f"{format_number(total_energy, 0)} kWh")
kpi2.metric("Average daily", f"{format_number(average_daily)} kWh")
kpi3.metric(
    "Peak day",
    f"{format_number(peak_row['energy_kwh'])} kWh",
    peak_row["datetime"].strftime("%d %b %Y"),
)
kpi4.metric(
    "Estimated cost",
    f"{currency_symbol}{format_number(estimated_cost, 0)}",
)
kpi5.metric("High-use anomalies", f"{int(anomaly_count)} days")

overview_tab, pattern_tab, components_tab, quality_tab = st.tabs(
    [
        "Overview",
        "Usage patterns",
        "Energy components",
        "Data quality",
    ]
)

# ------------------------------------------------------------------
# Overview
# ------------------------------------------------------------------
with overview_tab:
    st.subheader("Energy-consumption trend")
    st.markdown(
        '<p class="section-note">Use the sidebar to switch between '
        "daily, weekly, and monthly totals.</p>",
        unsafe_allow_html=True,
    )

    trend = aggregate_trend(daily_filtered, trend_frequency)
    trend_fig = px.line(
        trend,
        x="datetime",
        y="energy_kwh",
        markers=trend_frequency != "Daily",
        labels={
            "datetime": "Date",
            "energy_kwh": "Energy consumption (kWh)",
        },
    )
    trend_fig.update_layout(
        margin=dict(l=10, r=10, t=20, b=10),
        hovermode="x unified",
    )
    st.plotly_chart(trend_fig, use_container_width=True)

    left, right = st.columns([1.7, 1])

    with left:
        st.subheader("Daily anomalies")
        anomaly_data = daily_filtered[
            daily_filtered["anomaly_status"] == "High usage"
        ]
        anomaly_fig = go.Figure()
        anomaly_fig.add_trace(
            go.Scatter(
                x=daily_filtered["datetime"],
                y=daily_filtered["energy_kwh"],
                mode="lines",
                name="Daily consumption",
            )
        )
        anomaly_fig.add_trace(
            go.Scatter(
                x=anomaly_data["datetime"],
                y=anomaly_data["energy_kwh"],
                mode="markers",
                name="High usage",
                marker=dict(size=9),
            )
        )
        anomaly_fig.update_layout(
            xaxis_title="Date",
            yaxis_title="Energy consumption (kWh)",
            margin=dict(l=10, r=10, t=20, b=10),
            hovermode="x unified",
        )
        st.plotly_chart(anomaly_fig, use_container_width=True)

    with right:
        st.subheader("Top consumption days")
        top_days = (
            daily_filtered.nlargest(8, "energy_kwh")[
                ["datetime", "energy_kwh", "day_type", "anomaly_status"]
            ]
            .copy()
        )
        top_days["datetime"] = top_days["datetime"].dt.strftime(
            "%d %b %Y"
        )
        top_days["energy_kwh"] = top_days["energy_kwh"].round(2)
        top_days.columns = [
            "Date",
            "Energy (kWh)",
            "Day type",
            "Status",
        ]
        st.dataframe(
            top_days,
            use_container_width=True,
            hide_index=True,
        )

# ------------------------------------------------------------------
# Usage patterns
# ------------------------------------------------------------------
with pattern_tab:
    hourly_complete = hourly_filtered[
        hourly_filtered["coverage_pct"] >= 95
    ].copy()

    left, right = st.columns(2)

    with left:
        st.subheader("Average hourly load profile")
        hourly_pattern = (
            hourly_complete.groupby(
                ["hour", "day_type"], as_index=False
            )["energy_kwh"]
            .mean()
        )
        hourly_fig = px.line(
            hourly_pattern,
            x="hour",
            y="energy_kwh",
            color="day_type",
            markers=True,
            labels={
                "hour": "Hour of day",
                "energy_kwh": "Average energy (kWh)",
                "day_type": "Day type",
            },
        )
        hourly_fig.update_xaxes(dtick=2)
        hourly_fig.update_layout(
            margin=dict(l=10, r=10, t=20, b=10),
        )
        st.plotly_chart(hourly_fig, use_container_width=True)

    with right:
        st.subheader("Weekday versus weekend")
        day_type_fig = px.box(
            daily_filtered,
            x="day_type",
            y="energy_kwh",
            points="outliers",
            labels={
                "day_type": "Day type",
                "energy_kwh": "Daily energy (kWh)",
            },
        )
        day_type_fig.update_layout(
            margin=dict(l=10, r=10, t=20, b=10),
        )
        st.plotly_chart(day_type_fig, use_container_width=True)

    st.subheader("Day–hour consumption heatmap")
    day_order = [
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    ]
    heatmap = (
        hourly_complete.pivot_table(
            index="day_name",
            columns="hour",
            values="energy_kwh",
            aggfunc="mean",
        )
        .reindex(day_order)
    )
    heatmap_fig = px.imshow(
        heatmap,
        aspect="auto",
        labels={
            "x": "Hour of day",
            "y": "Day",
            "color": "Average kWh",
        },
    )
    heatmap_fig.update_layout(
        margin=dict(l=10, r=10, t=20, b=10),
    )
    st.plotly_chart(heatmap_fig, use_container_width=True)

# ------------------------------------------------------------------
# Components
# ------------------------------------------------------------------
with components_tab:
    component_columns = {
        "Kitchen": "sub_metering_1_kwh",
        "Laundry room": "sub_metering_2_kwh",
        "Water heater & AC": "sub_metering_3_kwh",
        "Other equipment": "other_energy_kwh",
    }

    component_data = pd.DataFrame(
        {
            "Component": component_columns.keys(),
            "Energy (kWh)": [
                daily_filtered[column].sum()
                for column in component_columns.values()
            ],
        }
    )

    left, right = st.columns([1, 1.3])

    with left:
        st.subheader("Energy mix")
        component_fig = px.pie(
            component_data,
            names="Component",
            values="Energy (kWh)",
            hole=0.52,
        )
        component_fig.update_layout(
            margin=dict(l=10, r=10, t=20, b=10),
        )
        st.plotly_chart(component_fig, use_container_width=True)

    with right:
        st.subheader("Monthly component consumption")
        monthly_components = (
            daily_filtered.set_index("datetime")[
                list(component_columns.values())
            ]
            .resample("ME")
            .sum(min_count=1)
            .reset_index()
            .melt(
                id_vars="datetime",
                var_name="component_code",
                value_name="energy_kwh",
            )
        )
        reverse_names = {
            value: key for key, value in component_columns.items()
        }
        monthly_components["Component"] = monthly_components[
            "component_code"
        ].map(reverse_names)

        component_trend_fig = px.area(
            monthly_components,
            x="datetime",
            y="energy_kwh",
            color="Component",
            labels={
                "datetime": "Month",
                "energy_kwh": "Energy (kWh)",
            },
        )
        component_trend_fig.update_layout(
            margin=dict(l=10, r=10, t=20, b=10),
        )
        st.plotly_chart(
            component_trend_fig,
            use_container_width=True,
        )

    st.info(
        "Sub-metering 1 represents the kitchen; sub-metering 2 "
        "represents the laundry room; sub-metering 3 represents "
        "the electric water heater and air conditioner. "
        "Other equipment is calculated from the residual active energy."
    )

# ------------------------------------------------------------------
# Data quality
# ------------------------------------------------------------------
with quality_tab:
    st.subheader("Observation coverage")
    quality_daily = daily[
        (daily["datetime"] >= start_ts)
        & (daily["datetime"] < end_ts)
    ].copy()

    coverage_fig = px.line(
        quality_daily,
        x="datetime",
        y="coverage_pct",
        labels={
            "datetime": "Date",
            "coverage_pct": "Coverage (%)",
        },
    )
    coverage_fig.add_hline(
        y=95,
        line_dash="dash",
        annotation_text="95% dashboard threshold",
    )
    coverage_fig.update_layout(
        margin=dict(l=10, r=10, t=20, b=10),
        yaxis_range=[0, 105],
    )
    st.plotly_chart(coverage_fig, use_container_width=True)

    col1, col2, col3 = st.columns(3)
    col1.metric(
        "Rows with short-gap interpolation",
        f"{int(daily['was_imputed'].sum()):,}",
    )
    col2.metric(
        "Days below 95% coverage",
        f"{int((daily['coverage_pct'] < 95).sum()):,}",
    )
    col3.metric(
        "Median daily coverage",
        f"{daily['coverage_pct'].median():.1f}%",
    )

    with st.expander("Methodology and limitations"):
        st.markdown(
            """
            - Missing values originally encoded as `?` were converted
              to null values.
            - Only consecutive missing runs of 60 minutes or less were
              interpolated.
            - Longer gaps remain missing and are represented through
              `coverage_pct`.
            - Daily anomalies use the 1.5×IQR rule and are descriptive,
              not evidence of equipment failure or electricity theft.
            - This portfolio file is a subset of the full UCI dataset.
            """
        )

st.divider()
download_frame = daily_filtered.copy()
download_frame["datetime"] = download_frame["datetime"].dt.strftime(
    "%Y-%m-%d"
)
st.download_button(
    "Download filtered daily data",
    data=download_frame.to_csv(index=False).encode("utf-8"),
    file_name="filtered_daily_electricity.csv",
    mime="text/csv",
)
