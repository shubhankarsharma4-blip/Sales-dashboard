from __future__ import annotations

import csv
import io
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from statistics import median

try:
    import pandas as pd
    import plotly.express as px
    import streamlit as st
except ImportError:
    pd = None
    px = None
    st = None


DATA_FILE = Path(__file__).with_name("sales_dashboard_dataset.csv")
DATE_FORMAT = "%d-%m-%Y"


def load_sales_data(file_path: Path) -> list[dict]:
    if not file_path.exists():
        raise FileNotFoundError(f"Dataset not found: {file_path}")

    rows: list[dict] = []
    with file_path.open("r", newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        required_columns = {"Date", "Product", "Category", "Quantity", "Revenue", "Cost"}

        if reader.fieldnames is None or not required_columns.issubset(reader.fieldnames):
            raise ValueError(
                "CSV must contain these columns: Date, Product, Category, Quantity, Revenue, Cost"
            )

        for raw_row in reader:
            sale_date = datetime.strptime(raw_row["Date"], DATE_FORMAT)
            quantity = int(raw_row["Quantity"])
            revenue = int(raw_row["Revenue"])
            cost = int(raw_row["Cost"])
            profit = revenue - cost

            rows.append(
                {
                    "Date": sale_date,
                    "Product": raw_row["Product"].strip(),
                    "Category": raw_row["Category"].strip(),
                    "Quantity": quantity,
                    "Revenue": revenue,
                    "Cost": cost,
                    "Profit": profit,
                    "MarginPct": (profit / revenue * 100) if revenue else 0.0,
                }
            )

    return rows


def summarize_by(rows: list[dict], key: str) -> list[dict]:
    grouped: dict[str, dict[str, int | str | float]] = defaultdict(
        lambda: {
            key: "",
            "Quantity": 0,
            "Revenue": 0,
            "Cost": 0,
            "Profit": 0,
            "Orders": 0,
        }
    )

    for row in rows:
        bucket = grouped[row[key]]
        bucket[key] = row[key]
        bucket["Quantity"] += row["Quantity"]
        bucket["Revenue"] += row["Revenue"]
        bucket["Cost"] += row["Cost"]
        bucket["Profit"] += row["Profit"]
        bucket["Orders"] += 1
        if key == "Product":
            bucket["Category"] = row["Category"]

    total_revenue = sum(row["Revenue"] for row in rows) or 1
    summary: list[dict] = []
    for value in grouped.values():
        revenue = float(value["Revenue"])
        orders = int(value["Orders"])
        profit = float(value["Profit"])
        value["MarginPct"] = (profit / revenue * 100) if revenue else 0.0
        value["RevenueSharePct"] = revenue / total_revenue * 100
        value["AvgOrderValue"] = revenue / orders if orders else 0.0
        summary.append(dict(value))

    return sorted(summary, key=lambda item: item["Revenue"], reverse=True)


def summarize_by_month(rows: list[dict]) -> list[dict]:
    monthly: dict[str, dict[str, int | str | float]] = defaultdict(
        lambda: {"Month": "", "Quantity": 0, "Revenue": 0, "Cost": 0, "Profit": 0, "Orders": 0}
    )

    for row in rows:
        month_key = row["Date"].strftime("%Y-%m")
        bucket = monthly[month_key]
        bucket["Month"] = month_key
        bucket["Quantity"] += row["Quantity"]
        bucket["Revenue"] += row["Revenue"]
        bucket["Cost"] += row["Cost"]
        bucket["Profit"] += row["Profit"]
        bucket["Orders"] += 1

    summary: list[dict] = []
    for value in monthly.values():
        revenue = float(value["Revenue"])
        profit = float(value["Profit"])
        orders = int(value["Orders"])
        value["MarginPct"] = (profit / revenue * 100) if revenue else 0.0
        value["AvgOrderValue"] = revenue / orders if orders else 0.0
        summary.append(dict(value))

    return sorted(summary, key=lambda item: item["Month"])


def compute_overview(rows: list[dict]) -> dict:
    total_orders = len(rows)
    total_quantity = sum(row["Quantity"] for row in rows)
    total_revenue = sum(row["Revenue"] for row in rows)
    total_cost = sum(row["Cost"] for row in rows)
    total_profit = sum(row["Profit"] for row in rows)

    return {
        "Orders": total_orders,
        "Quantity": total_quantity,
        "Revenue": total_revenue,
        "Cost": total_cost,
        "Profit": total_profit,
        "ProfitMarginPct": (total_profit / total_revenue * 100) if total_revenue else 0.0,
        "AvgOrderValue": (total_revenue / total_orders) if total_orders else 0.0,
    }


def calculate_expansion_opportunities(rows: list[dict]) -> list[dict]:
    products = summarize_by(rows, "Product")
    order_counts = [item["Orders"] for item in products]
    median_orders = median(order_counts) if order_counts else 0
    opportunities: list[dict] = []

    for item in products:
        margin_pct = float(item["MarginPct"])
        order_share_pct = float(item["Orders"]) / len(rows) * 100 if rows else 0.0
        diversification_headroom = 100 - float(item["RevenueSharePct"])
        score = margin_pct * 0.45 + order_share_pct * 0.30 + diversification_headroom * 0.25

        reasons: list[str] = []
        if margin_pct >= 35:
            reasons.append("high margin")
        if int(item["Orders"]) >= median_orders:
            reasons.append("repeat demand")
        if float(item["RevenueSharePct"]) < 15:
            reasons.append("low concentration risk")
        if not reasons:
            reasons.append("stable contributor")

        opportunities.append(
            {
                **item,
                "ExpansionScore": round(score, 1),
                "WhyScale": ", ".join(reasons),
            }
        )

    return sorted(opportunities, key=lambda item: item["ExpansionScore"], reverse=True)


def calculate_growth_scenarios(rows: list[dict], products_to_expand: list[str], growth_pct: int) -> list[dict]:
    summary = summarize_by(rows, "Product")
    multiplier = growth_pct / 100
    scenarios: list[dict] = []

    for item in summary:
        if item["Product"] not in products_to_expand:
            continue
        scenarios.append(
            {
                "Product": item["Product"],
                "Category": item["Category"],
                "GrowthPct": growth_pct,
                "ProjectedRevenueLift": round(item["Revenue"] * multiplier, 2),
                "ProjectedProfitLift": round(item["Profit"] * multiplier, 2),
            }
        )

    return sorted(scenarios, key=lambda item: item["ProjectedProfitLift"], reverse=True)


def generate_business_insights(rows: list[dict]) -> list[str]:
    overview = compute_overview(rows)
    product_summary = summarize_by(rows, "Product")
    category_summary = summarize_by(rows, "Category")
    monthly_summary = summarize_by_month(rows)
    opportunities = calculate_expansion_opportunities(rows)

    messages = [
        (
            f"{product_summary[0]['Product']} contributes {product_summary[0]['RevenueSharePct']:.1f}% of revenue, "
            f"so the business is too dependent on one product."
        ),
        (
            f"{category_summary[0]['Category']} leads revenue, but "
            f"{max(category_summary, key=lambda item: item['MarginPct'])['Category']} has the strongest margin profile."
        ),
        (
            f"Best products to scale first: {', '.join(item['Product'] for item in opportunities[:3])}. "
            "They balance margin, repeat demand, and lower concentration risk."
        ),
    ]

    if len(monthly_summary) >= 2:
        prev_month = monthly_summary[-2]
        current_month = monthly_summary[-1]
        revenue_change = (
            (current_month["Revenue"] - prev_month["Revenue"]) / prev_month["Revenue"] * 100
            if prev_month["Revenue"]
            else 0.0
        )
        messages.append(
            f"Revenue changed by {revenue_change:.1f}% from {prev_month['Month']} to {current_month['Month']}, so demand momentum should be monitored before expanding inventory."
        )

    messages.append(
        f"Overall profit margin is {overview['ProfitMarginPct']:.1f}%. Expanding high-margin fashion and accessories can improve this faster than relying on laptop sales alone."
    )
    return messages


def filter_rows(
    rows: list[dict],
    selected_categories: list[str],
    selected_products: list[str],
    selected_dates: tuple[date, date],
) -> list[dict]:
    filtered: list[dict] = []
    for row in rows:
        row_date = row["Date"].date()
        if selected_categories and row["Category"] not in selected_categories:
            continue
        if selected_products and row["Product"] not in selected_products:
            continue
        if row_date < selected_dates[0] or row_date > selected_dates[1]:
            continue
        filtered.append(row)
    return filtered


def rows_to_dataframe(rows: list[dict]) -> "pd.DataFrame | None":
    if pd is None:
        return None

    normalized: list[dict] = []
    for row in rows:
        normalized.append(
            {
                "Date": row["Date"].strftime(DATE_FORMAT),
                "Product": row["Product"],
                "Category": row["Category"],
                "Quantity": row["Quantity"],
                "Revenue": row["Revenue"],
                "Cost": row["Cost"],
                "Profit": row["Profit"],
                "MarginPct": round(row["MarginPct"], 2),
            }
        )
    return pd.DataFrame(normalized)


def csv_bytes_from_rows(rows: list[dict]) -> bytes:
    output = io.StringIO()
    fieldnames = ["Date", "Product", "Category", "Quantity", "Revenue", "Cost", "Profit", "MarginPct"]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                "Date": row["Date"].strftime(DATE_FORMAT),
                "Product": row["Product"],
                "Category": row["Category"],
                "Quantity": row["Quantity"],
                "Revenue": row["Revenue"],
                "Cost": row["Cost"],
                "Profit": row["Profit"],
                "MarginPct": round(row["MarginPct"], 2),
            }
        )
    return output.getvalue().encode("utf-8")


def csv_bytes_from_summary(rows: list[dict]) -> bytes:
    if not rows:
        return b""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


def build_text_report(overview: dict, insights: list[str], opportunities: list[dict], scenarios: list[dict]) -> str:
    lines = [
        "Sales Growth and Expansion Report",
        "================================",
        f"Revenue: Rs. {overview['Revenue']:,}",
        f"Profit: Rs. {overview['Profit']:,}",
        f"Profit Margin: {overview['ProfitMarginPct']:.1f}%",
        f"Orders: {overview['Orders']}",
        "",
        "Top Expansion Candidates:",
    ]
    for item in opportunities[:5]:
        lines.append(f"- {item['Product']}: score {item['ExpansionScore']}, reason: {item['WhyScale']}")
    lines.append("")
    lines.append("Key Insights:")
    for item in insights:
        lines.append(f"- {item}")
    if scenarios:
        lines.append("")
        lines.append("Growth Simulation:")
        for item in scenarios:
            lines.append(
                f"- {item['Product']}: +Rs. {item['ProjectedRevenueLift']:,} revenue, +Rs. {item['ProjectedProfitLift']:,} profit"
            )
    return "\n".join(lines)


def apply_theme() -> None:
    st.markdown(
        """
        <style>
        .stApp {
            background: #f8fafc;
        }
        section[data-testid="stSidebar"] {
            background: #ffffff;
        }
        .block-container {
            padding-top: 2rem;
            padding-bottom: 2rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def run_streamlit_app() -> None:
    st.set_page_config(page_title="Sales Dashboard", page_icon=":bar_chart:", layout="wide")
    apply_theme()

    all_rows = load_sales_data(DATA_FILE)
    min_date = min(row["Date"].date() for row in all_rows)
    max_date = max(row["Date"].date() for row in all_rows)
    all_categories = sorted({row["Category"] for row in all_rows})
    all_products = sorted({row["Product"] for row in all_rows})

    st.title("Sales Growth Dashboard")
    st.caption("Simple sales analytics and business expansion insights")

    st.sidebar.header("Filters")
    selected_dates = st.sidebar.date_input(
        "Date range", value=(min_date, max_date), min_value=min_date, max_value=max_date
    )
    date_range = selected_dates if isinstance(selected_dates, tuple) and len(selected_dates) == 2 else (min_date, max_date)
    selected_categories = st.sidebar.multiselect("Category", all_categories, default=all_categories)
    filtered_products = sorted({row["Product"] for row in all_rows if row["Category"] in selected_categories}) or all_products
    selected_products = st.sidebar.multiselect("Product", filtered_products, default=filtered_products)

    filtered_rows = filter_rows(all_rows, selected_categories, selected_products, date_range)
    if not filtered_rows:
        st.warning("No records match the selected filters.")
        return

    overview = compute_overview(filtered_rows)
    product_summary = summarize_by(filtered_rows, "Product")
    category_summary = summarize_by(filtered_rows, "Category")
    monthly_summary = summarize_by_month(filtered_rows)
    opportunities = calculate_expansion_opportunities(filtered_rows)
    insights = generate_business_insights(filtered_rows)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Revenue", f"Rs. {overview['Revenue']:,}")
    m2.metric("Profit", f"Rs. {overview['Profit']:,}")
    m3.metric("Margin", f"{overview['ProfitMarginPct']:.1f}%")
    m4.metric("Orders", f"{overview['Orders']}")

    st.subheader("Expansion Recommendation")
    st.info(
        f"Scale {opportunities[0]['Product']} first. It has {opportunities[0]['MarginPct']:.1f}% margin and lower concentration risk than the current top seller."
    )

    chart_col1, chart_col2 = st.columns(2)
    if pd is not None and px is not None:
        product_df = pd.DataFrame(product_summary)
        category_df = pd.DataFrame(category_summary)
        monthly_df = pd.DataFrame(monthly_summary)

        with chart_col1:
            st.subheader("Revenue by Product")
            fig = px.bar(product_df, x="Product", y="Revenue", color="Category")
            fig.update_layout(margin=dict(l=10, r=10, t=20, b=10), height=320)
            st.plotly_chart(fig, use_container_width=True)

        with chart_col2:
            st.subheader("Profit by Category")
            fig = px.bar(category_df, x="Category", y="Profit", color="Category")
            fig.update_layout(showlegend=False, margin=dict(l=10, r=10, t=20, b=10), height=320)
            st.plotly_chart(fig, use_container_width=True)

        st.subheader("Monthly Trend")
        fig = px.line(monthly_df, x="Month", y=["Revenue", "Profit"], markers=True)
        fig.update_layout(margin=dict(l=10, r=10, t=20, b=10), height=320)
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Business Insights")
    for item in insights:
        st.write(f"- {item}")

    st.subheader("Growth Simulator")
    sim_col1, sim_col2 = st.columns(2)
    with sim_col1:
        target_products = st.multiselect(
            "Products to scale",
            options=[item["Product"] for item in opportunities],
            default=[item["Product"] for item in opportunities[:2]],
        )
    with sim_col2:
        growth_pct = st.slider("Expected sales growth (%)", min_value=5, max_value=100, value=20, step=5)

    scenarios = calculate_growth_scenarios(filtered_rows, target_products, growth_pct)
    if scenarios:
        scenario_df = pd.DataFrame(scenarios) if pd is not None else None
        total_revenue_lift = sum(item["ProjectedRevenueLift"] for item in scenarios)
        total_profit_lift = sum(item["ProjectedProfitLift"] for item in scenarios)
        st.success(
            f"Estimated impact: +Rs. {total_revenue_lift:,.0f} revenue and +Rs. {total_profit_lift:,.0f} profit."
        )
        if scenario_df is not None:
            st.dataframe(scenario_df, use_container_width=True, hide_index=True)

    st.subheader("Downloads")
    d1, d2, d3 = st.columns(3)
    with d1:
        st.download_button(
            "Filtered transactions CSV",
            data=csv_bytes_from_rows(filtered_rows),
            file_name="filtered_sales_transactions.csv",
            mime="text/csv",
            use_container_width=True,
        )
    with d2:
        st.download_button(
            "Product summary CSV",
            data=csv_bytes_from_summary(product_summary),
            file_name="product_summary.csv",
            mime="text/csv",
            use_container_width=True,
        )
    with d3:
        st.download_button(
            "Strategy report TXT",
            data=build_text_report(overview, insights, opportunities, scenarios).encode("utf-8"),
            file_name="sales_expansion_report.txt",
            mime="text/plain",
            use_container_width=True,
        )

    st.subheader("Detailed Data")
    tab1, tab2, tab3 = st.tabs(["Products", "Categories", "Months"])
    with tab1:
        st.dataframe(pd.DataFrame(product_summary), use_container_width=True, hide_index=True)
    with tab2:
        st.dataframe(pd.DataFrame(category_summary), use_container_width=True, hide_index=True)
    with tab3:
        st.dataframe(pd.DataFrame(monthly_summary), use_container_width=True, hide_index=True)


def run_cli_fallback() -> None:
    rows = load_sales_data(DATA_FILE)
    overview = compute_overview(rows)
    print("Sales Dashboard")
    print("================")
    print(f"Revenue: Rs. {overview['Revenue']:,}")
    print(f"Profit: Rs. {overview['Profit']:,}")
    print(f"Margin: {overview['ProfitMarginPct']:.1f}%")
    print("Install Streamlit and run: py -m streamlit run main.py")


def main() -> None:
    if st is None or pd is None or px is None:
        run_cli_fallback()
    else:
        run_streamlit_app()


if __name__ == "__main__":
    main()
