from __future__ import annotations

import csv
import html
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
                    "UnitPrice": (revenue / quantity) if quantity else 0.0,
                    "UnitCost": (cost / quantity) if quantity else 0.0,
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
        quantity = int(value["Quantity"])
        profit = float(value["Profit"])
        value["MarginPct"] = (profit / revenue * 100) if revenue else 0.0
        value["RevenueSharePct"] = revenue / total_revenue * 100
        value["ProfitPerOrder"] = profit / orders if orders else 0.0
        value["AvgOrderValue"] = revenue / orders if orders else 0.0
        value["AvgUnitsPerOrder"] = quantity / orders if orders else 0.0
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
        orders = int(value["Orders"])
        profit = float(value["Profit"])
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
            reasons.append("strong margin profile")
        if int(item["Orders"]) >= median_orders:
            reasons.append("repeatable demand")
        if float(item["RevenueSharePct"]) < 15:
            reasons.append("room to scale without concentration risk")
        if not reasons:
            reasons.append("stable contributor")

        opportunities.append(
            {
                **item,
                "ExpansionScore": score,
                "WhyScale": ", ".join(reasons),
            }
        )

    return sorted(opportunities, key=lambda item: item["ExpansionScore"], reverse=True)


def calculate_growth_scenarios(rows: list[dict], products_to_expand: list[str], growth_pct: int) -> list[dict]:
    if not products_to_expand:
        return []

    summary = summarize_by(rows, "Product")
    scenarios: list[dict] = []
    multiplier = growth_pct / 100

    for item in summary:
        if item["Product"] not in products_to_expand:
            continue

        additional_revenue = item["Revenue"] * multiplier
        additional_cost = item["Cost"] * multiplier
        additional_profit = item["Profit"] * multiplier
        scenarios.append(
            {
                "Product": item["Product"],
                "Category": item["Category"],
                "CurrentRevenue": item["Revenue"],
                "CurrentProfit": item["Profit"],
                "GrowthPct": growth_pct,
                "ProjectedRevenueLift": round(additional_revenue, 2),
                "ProjectedProfitLift": round(additional_profit, 2),
                "ProjectedCostLift": round(additional_cost, 2),
            }
        )

    return sorted(scenarios, key=lambda item: item["ProjectedProfitLift"], reverse=True)


def generate_business_insights(rows: list[dict]) -> list[dict]:
    overview = compute_overview(rows)
    product_summary = summarize_by(rows, "Product")
    category_summary = summarize_by(rows, "Category")
    monthly_summary = summarize_by_month(rows)

    top_revenue_product = product_summary[0]
    top_margin_product = max(product_summary, key=lambda item: item["MarginPct"])
    highest_margin_category = max(category_summary, key=lambda item: item["MarginPct"])
    highest_volume_category = max(category_summary, key=lambda item: item["Quantity"])
    opportunities = calculate_expansion_opportunities(rows)[:3]

    insights: list[dict] = [
        {
            "title": "Reduce concentration risk",
            "detail": (
                f"{top_revenue_product['Product']} drives {top_revenue_product['RevenueSharePct']:.1f}% of revenue "
                f"but runs at only {top_revenue_product['MarginPct']:.1f}% margin, below the overall "
                f"{overview['ProfitMarginPct']:.1f}% margin."
            ),
            "action": "Use this product as the acquisition anchor, but attach higher-margin products to each sale.",
        },
        {
            "title": "Scale margin-rich categories first",
            "detail": (
                f"{highest_margin_category['Category']} has the best category margin at "
                f"{highest_margin_category['MarginPct']:.1f}% while {highest_volume_category['Category']} "
                f"already leads in unit demand."
            ),
            "action": "Prioritize budget, inventory, and campaigns around products with proven demand and margin.",
        },
        {
            "title": "Promote the best expansion candidates",
            "detail": (
                "The current data favors "
                + ", ".join(item["Product"] for item in opportunities)
                + " because they combine stronger margins with repeatable demand."
            ),
            "action": "Push bundles, repeat-purchase offers, and marketplace expansion around those SKUs first.",
        },
    ]

    if len(monthly_summary) >= 2:
        previous_month = monthly_summary[-2]
        current_month = monthly_summary[-1]
        revenue_change_pct = (
            (current_month["Revenue"] - previous_month["Revenue"]) / previous_month["Revenue"] * 100
            if previous_month["Revenue"]
            else 0.0
        )
        profit_change_pct = (
            (current_month["Profit"] - previous_month["Profit"]) / previous_month["Profit"] * 100
            if previous_month["Profit"]
            else 0.0
        )
        insights.append(
            {
                "title": "Watch the monthly slowdown",
                "detail": (
                    f"Revenue moved from {previous_month['Revenue']} in {previous_month['Month']} to "
                    f"{current_month['Revenue']} in {current_month['Month']} ({revenue_change_pct:.1f}%), and "
                    f"profit shifted by {profit_change_pct:.1f}%."
                ),
                "action": "Treat expansion as both growth and recovery: refresh campaigns and review stock depth before scaling.",
            }
        )

    return insights


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
                **row,
                "Date": row["Date"].strftime(DATE_FORMAT),
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
    fieldnames = list(rows[0].keys())
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return output.getvalue().encode("utf-8")


def build_text_report(
    overview: dict,
    insights: list[dict],
    opportunities: list[dict],
    scenarios: list[dict],
) -> str:
    lines = [
        "Sales Growth and Expansion Report",
        "================================",
        "",
        f"Revenue: {format_currency(overview['Revenue'])}",
        f"Profit: {format_currency(overview['Profit'])}",
        f"Profit Margin: {format_pct(overview['ProfitMarginPct'])}",
        f"Orders: {overview['Orders']}",
        "",
        "Top Expansion Candidates",
        "------------------------",
    ]

    for item in opportunities[:5]:
        lines.append(
            f"- {item['Product']} ({item['Category']}): score {item['ExpansionScore']:.1f}, "
            f"margin {item['MarginPct']:.1f}%, revenue share {item['RevenueSharePct']:.1f}%"
        )

    lines.extend(["", "Strategic Insights", "------------------"])
    for insight in insights:
        lines.append(f"- {insight['title']}: {insight['detail']} {insight['action']}")

    if scenarios:
        lines.extend(["", "Growth Simulator", "----------------"])
        for item in scenarios:
            lines.append(
                f"- {item['Product']}: +{format_currency(item['ProjectedRevenueLift'])} revenue, "
                f"+{format_currency(item['ProjectedProfitLift'])} profit at {item['GrowthPct']}% growth"
            )

    return "\n".join(lines)


def format_currency(value: float | int) -> str:
    return f"Rs. {value:,.0f}"


def format_pct(value: float) -> str:
    return f"{value:.1f}%"


def build_metric_card(title: str, value: str, subtitle: str, tone: str = "blue") -> str:
    return f"""
    <div class="metric-card {tone}">
        <div class="metric-title">{html.escape(title)}</div>
        <div class="metric-value">{html.escape(value)}</div>
        <div class="metric-subtitle">{html.escape(subtitle)}</div>
    </div>
    """


def render_metric_cards(overview: dict) -> None:
    cards = [
        build_metric_card("Revenue", format_currency(overview["Revenue"]), "Top-line sales", "blue"),
        build_metric_card("Profit", format_currency(overview["Profit"]), "Bottom-line contribution", "green"),
        build_metric_card("Margin", format_pct(overview["ProfitMarginPct"]), "Blended profit margin", "orange"),
        build_metric_card("Orders", f"{overview['Orders']}", "Transactions in view", "slate"),
    ]
    st.markdown(f"<div class='metric-grid'>{''.join(cards)}</div>", unsafe_allow_html=True)


def render_bar_rank(title: str, rows: list[dict], label_key: str, value_key: str, color: str, suffix: str = "") -> None:
    st.markdown(f"#### {title}")
    if not rows:
        st.info("No data available for this view.")
        return

    max_value = max(float(row[value_key]) for row in rows) or 1
    parts: list[str] = ["<div class='rank-list'>"]
    for row in rows:
        value = float(row[value_key])
        width = max(8.0, value / max_value * 100)
        parts.append(
            f"""
            <div class="rank-item">
                <div class="rank-header">
                    <span>{html.escape(str(row[label_key]))}</span>
                    <span>{html.escape(format_currency(value) if 'Revenue' in value_key or 'Profit' in value_key else f"{value:.1f}{suffix}")}</span>
                </div>
                <div class="rank-track">
                    <div class="rank-fill" style="width:{width:.1f}%; background:{color};"></div>
                </div>
            </div>
            """
        )
    parts.append("</div>")
    st.markdown("".join(parts), unsafe_allow_html=True)


def render_plotly_monthly_trend(monthly_summary: list[dict]) -> None:
    if not monthly_summary or px is None or pd is None:
        st.info("No monthly trend available.")
        return

    frame = pd.DataFrame(monthly_summary)
    fig = px.line(
        frame,
        x="Month",
        y=["Revenue", "Profit"],
        markers=True,
        color_discrete_sequence=["#0f766e", "#f97316"],
    )
    fig.update_layout(
        height=320,
        margin=dict(l=10, r=10, t=10, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(255,255,255,0.0)",
        legend_title_text="Metric",
        xaxis_title="Month",
        yaxis_title="Amount",
    )
    st.plotly_chart(fig, use_container_width=True)


def render_plotly_product_mix(product_summary: list[dict]) -> None:
    if not product_summary or px is None or pd is None:
        st.info("No product mix available.")
        return

    frame = pd.DataFrame(product_summary)
    fig = px.bar(
        frame,
        x="Product",
        y="Revenue",
        color="Category",
        text="Revenue",
        color_discrete_sequence=["#0ea5e9", "#22c55e", "#f97316", "#334155"],
    )
    fig.update_traces(texttemplate="%{text:.0f}", textposition="outside")
    fig.update_layout(
        height=340,
        margin=dict(l=10, r=10, t=10, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(255,255,255,0.0)",
        xaxis_title="Product",
        yaxis_title="Revenue",
    )
    st.plotly_chart(fig, use_container_width=True)


def render_plotly_margin_bubble(product_summary: list[dict]) -> None:
    if not product_summary or px is None or pd is None:
        st.info("No margin scatter available.")
        return

    frame = pd.DataFrame(product_summary)
    fig = px.scatter(
        frame,
        x="RevenueSharePct",
        y="MarginPct",
        size="Profit",
        color="Category",
        hover_name="Product",
        text="Product",
        size_max=60,
        color_discrete_sequence=["#0ea5e9", "#22c55e", "#f97316", "#334155"],
    )
    fig.update_traces(textposition="top center")
    fig.update_layout(
        height=340,
        margin=dict(l=10, r=10, t=10, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(255,255,255,0.0)",
        xaxis_title="Revenue Share (%)",
        yaxis_title="Margin (%)",
    )
    st.plotly_chart(fig, use_container_width=True)


def render_html_table(title: str, rows: list[dict], columns: list[str]) -> None:
    st.markdown(f"#### {title}")
    if not rows:
        st.info("No rows available.")
        return

    header = "".join(f"<th>{html.escape(column)}</th>" for column in columns)
    body_parts: list[str] = []
    for row in rows:
        cells: list[str] = []
        for column in columns:
            value = row.get(column, "")
            if isinstance(value, float):
                if "Pct" in column:
                    display = format_pct(value)
                elif "Revenue" in column or "Profit" in column or "Cost" in column:
                    display = format_currency(value)
                else:
                    display = f"{value:.2f}"
            elif isinstance(value, int):
                if "Revenue" in column or "Profit" in column or "Cost" in column:
                    display = format_currency(value)
                else:
                    display = f"{value}"
            else:
                display = str(value)
            cells.append(f"<td>{html.escape(display)}</td>")
        body_parts.append(f"<tr>{''.join(cells)}</tr>")

    table_html = f"""
    <div class="table-card">
        <table class="insight-table">
            <thead><tr>{header}</tr></thead>
            <tbody>{''.join(body_parts)}</tbody>
        </table>
    </div>
    """
    st.markdown(table_html, unsafe_allow_html=True)


def render_strategy_cards(insights: list[dict]) -> None:
    st.markdown("### Expansion Insights")
    cards = []
    for insight in insights:
        cards.append(
            f"""
            <div class="insight-card">
                <div class="insight-title">{html.escape(insight['title'])}</div>
                <div class="insight-detail">{html.escape(insight['detail'])}</div>
                <div class="insight-action">{html.escape(insight['action'])}</div>
            </div>
            """
        )
    st.markdown(f"<div class='insight-grid'>{''.join(cards)}</div>", unsafe_allow_html=True)


def apply_theme() -> None:
    st.markdown(
        """
        <style>
        :root {
            --ink: #102a43;
            --mist: #f5f7fb;
            --accent: #0f766e;
            --accent-2: #ea580c;
            --panel: rgba(255, 255, 255, 0.88);
        }
        .stApp {
            background:
                radial-gradient(circle at top left, rgba(16, 185, 129, 0.16), transparent 26%),
                radial-gradient(circle at 85% 0%, rgba(249, 115, 22, 0.15), transparent 24%),
                linear-gradient(180deg, #fffaf5 0%, #eef9f6 52%, #f6f7fb 100%);
        }
        .block-container {
            padding-top: 1.6rem;
            padding-bottom: 3rem;
        }
        section[data-testid="stSidebar"] {
            background: linear-gradient(180deg, rgba(255,255,255,0.94), rgba(240,249,255,0.9));
            border-right: 1px solid rgba(148, 163, 184, 0.16);
        }
        .hero {
            padding: 1.7rem 1.8rem;
            border-radius: 28px;
            background:
                radial-gradient(circle at top right, rgba(255,255,255,0.16), transparent 26%),
                linear-gradient(135deg, #102a43 0%, #0f766e 54%, #ea580c 100%);
            color: white;
            box-shadow: 0 24px 60px rgba(16, 42, 67, 0.18);
            margin-bottom: 1.25rem;
        }
        .hero h1 {
            margin: 0;
            font-size: 2.15rem;
            letter-spacing: -0.03em;
        }
        .hero p {
            margin: 0.7rem 0 0;
            color: rgba(255, 255, 255, 0.82);
            max-width: 760px;
            line-height: 1.5;
        }
        .hero-badge {
            display: inline-block;
            padding: 0.35rem 0.7rem;
            border-radius: 999px;
            background: rgba(255,255,255,0.14);
            font-size: 0.82rem;
            letter-spacing: 0.06em;
            text-transform: uppercase;
            margin-bottom: 0.75rem;
        }
        .metric-grid {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 0.9rem;
            margin: 1rem 0 1.5rem;
        }
        .metric-card, .insight-card, .table-card, .chart-card {
            border-radius: 22px;
            background: var(--panel);
            border: 1px solid rgba(148, 163, 184, 0.18);
            box-shadow: 0 16px 40px rgba(15, 23, 42, 0.08);
            backdrop-filter: blur(10px);
        }
        .metric-card {
            padding: 1.05rem 1.15rem;
        }
        .metric-title {
            color: #475569;
            font-size: 0.88rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.06em;
        }
        .metric-value {
            margin-top: 0.35rem;
            font-size: 1.7rem;
            font-weight: 800;
            color: #0f172a;
        }
        .metric-subtitle {
            margin-top: 0.15rem;
            color: #64748b;
            font-size: 0.92rem;
        }
        .metric-card.blue { border-top: 4px solid #0ea5e9; }
        .metric-card.green { border-top: 4px solid #22c55e; }
        .metric-card.orange { border-top: 4px solid #f97316; }
        .metric-card.slate { border-top: 4px solid #334155; }
        .rank-list {
            background: var(--panel);
            padding: 1rem;
            border-radius: 22px;
            box-shadow: 0 16px 40px rgba(15, 23, 42, 0.08);
        }
        .rank-item + .rank-item {
            margin-top: 0.9rem;
        }
        .rank-header {
            display: flex;
            justify-content: space-between;
            gap: 1rem;
            font-size: 0.94rem;
            color: #0f172a;
            margin-bottom: 0.35rem;
        }
        .rank-track {
            height: 10px;
            border-radius: 999px;
            background: #e2e8f0;
            overflow: hidden;
        }
        .rank-fill {
            height: 100%;
            border-radius: 999px;
        }
        .chart-card {
            padding: 0.35rem 0.5rem;
        }
        .insight-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 1rem;
            margin-top: 0.75rem;
        }
        .insight-card {
            padding: 1rem 1.1rem;
        }
        .insight-title {
            font-size: 1rem;
            font-weight: 800;
            color: #0f172a;
        }
        .insight-detail {
            margin-top: 0.45rem;
            color: #334155;
            line-height: 1.5;
        }
        .insight-action {
            margin-top: 0.7rem;
            color: #0f766e;
            font-weight: 700;
            line-height: 1.5;
        }
        .table-card {
            padding: 0.6rem;
            overflow-x: auto;
        }
        .download-strip {
            display: grid;
            grid-template-columns: 1.2fr 1fr;
            gap: 1rem;
            margin: 1rem 0 1.35rem;
        }
        .callout-card {
            padding: 1rem 1.15rem;
            border-radius: 22px;
            background: linear-gradient(135deg, rgba(15,118,110,0.10), rgba(14,165,233,0.12));
            border: 1px solid rgba(15,118,110,0.16);
            color: var(--ink);
            box-shadow: 0 16px 40px rgba(15, 23, 42, 0.07);
        }
        .callout-card strong {
            display: block;
            margin-bottom: 0.35rem;
            font-size: 1rem;
        }
        .insight-table {
            width: 100%;
            border-collapse: collapse;
            font-size: 0.92rem;
        }
        .insight-table th {
            text-align: left;
            color: #475569;
            font-weight: 700;
            padding: 0.75rem 0.8rem;
            border-bottom: 1px solid #e2e8f0;
        }
        .insight-table td {
            padding: 0.72rem 0.8rem;
            border-bottom: 1px solid #f1f5f9;
            color: #0f172a;
        }
        @media (max-width: 900px) {
            .metric-grid, .insight-grid, .download-strip {
                grid-template-columns: 1fr;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def run_streamlit_app() -> None:
    st.set_page_config(page_title="Sales Expansion Dashboard", page_icon=":bar_chart:", layout="wide")
    apply_theme()

    all_rows = load_sales_data(DATA_FILE)
    if not all_rows:
        st.error("The dataset is empty.")
        return

    min_date = min(row["Date"].date() for row in all_rows)
    max_date = max(row["Date"].date() for row in all_rows)
    all_categories = sorted({row["Category"] for row in all_rows})
    all_products = sorted({row["Product"] for row in all_rows})

    st.markdown(
        """
        <div class="hero">
            <div class="hero-badge">Expansion Planning Workspace</div>
            <h1>Sales Growth & Expansion Dashboard</h1>
            <p>
                Interactive sales analytics for revenue, margin, concentration risk, and growth planning.
                This view is designed to answer the business question: what should we scale next to increase profit without becoming too dependent on one product?
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.sidebar.header("Filters")
    selected_dates = st.sidebar.date_input("Date range", value=(min_date, max_date), min_value=min_date, max_value=max_date)
    if isinstance(selected_dates, tuple) and len(selected_dates) == 2:
        date_range = selected_dates
    else:
        date_range = (min_date, max_date)

    selected_categories = st.sidebar.multiselect("Category", all_categories, default=all_categories)
    filtered_products = sorted(
        {row["Product"] for row in all_rows if row["Category"] in selected_categories}
    ) or all_products
    selected_products = st.sidebar.multiselect("Product", filtered_products, default=filtered_products)

    filtered_rows = filter_rows(all_rows, selected_categories, selected_products, date_range)
    if not filtered_rows:
        st.warning("No records match the selected filters.")
        return

    overview = compute_overview(filtered_rows)
    category_summary = summarize_by(filtered_rows, "Category")
    product_summary = summarize_by(filtered_rows, "Product")
    monthly_summary = summarize_by_month(filtered_rows)
    opportunities = calculate_expansion_opportunities(filtered_rows)
    insights = generate_business_insights(filtered_rows)
    filtered_df = rows_to_dataframe(filtered_rows)

    render_metric_cards(overview)

    lead_opportunity = opportunities[0]
    st.markdown(
        f"""
        <div class="download-strip">
            <div class="callout-card">
                <strong>Best next expansion move</strong>
                Scale {html.escape(lead_opportunity['Product'])} first. It combines {lead_opportunity['MarginPct']:.1f}% margin,
                repeat demand, and low concentration risk compared with the current laptop-heavy revenue mix.
            </div>
            <div class="callout-card">
                <strong>Why this matters</strong>
                The business is profitable, but {product_summary[0]['Product']} still contributes {product_summary[0]['RevenueSharePct']:.1f}% of revenue.
                Expansion should improve margin mix, not only top-line sales.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col_left, col_right = st.columns((1.15, 0.85))
    with col_left:
        st.markdown("### Revenue Mix")
        render_plotly_product_mix(product_summary)
    with col_right:
        st.markdown("### Category Profit")
        render_bar_rank("Profit by Category", category_summary, "Category", "Profit", "#22c55e")

    trend_col, score_col = st.columns((1.05, 0.95))
    with trend_col:
        st.markdown("### Revenue and Profit Trend")
        render_plotly_monthly_trend(monthly_summary)
    with score_col:
        st.markdown("### Margin vs Concentration")
        render_plotly_margin_bubble(product_summary)

    st.markdown("### Expansion Priority")
    render_bar_rank(
        "Heuristic score based on margin, repeatability, and diversification",
        opportunities[:5],
        "Product",
        "ExpansionScore",
        "#f97316",
    )

    render_strategy_cards(insights)

    st.markdown("### Growth Simulator")
    sim_col1, sim_col2 = st.columns((1, 1))
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
        total_revenue_lift = sum(item["ProjectedRevenueLift"] for item in scenarios)
        total_profit_lift = sum(item["ProjectedProfitLift"] for item in scenarios)
        st.info(
            f"If the selected products grow by {growth_pct}%, this dataset suggests an extra "
            f"{format_currency(total_revenue_lift)} in revenue and {format_currency(total_profit_lift)} in profit, "
            "assuming similar pricing and cost structure."
        )
        render_html_table(
            "Projected uplift by product",
            scenarios,
            ["Product", "Category", "GrowthPct", "ProjectedRevenueLift", "ProjectedProfitLift"],
        )

    st.markdown("### Download Reports")
    export_col1, export_col2, export_col3 = st.columns(3)
    with export_col1:
        st.download_button(
            "Download filtered transactions CSV",
            data=csv_bytes_from_rows(filtered_rows),
            file_name="filtered_sales_transactions.csv",
            mime="text/csv",
            use_container_width=True,
        )
    with export_col2:
        st.download_button(
            "Download product summary CSV",
            data=csv_bytes_from_summary(product_summary),
            file_name="product_summary.csv",
            mime="text/csv",
            use_container_width=True,
        )
    with export_col3:
        st.download_button(
            "Download strategy report TXT",
            data=build_text_report(overview, insights, opportunities, scenarios).encode("utf-8"),
            file_name="sales_expansion_report.txt",
            mime="text/plain",
            use_container_width=True,
        )

    st.markdown("### Detailed Views")
    tab1, tab2, tab3 = st.tabs(["Products", "Categories", "Months"])
    with tab1:
        if filtered_df is not None:
            st.dataframe(pd.DataFrame(product_summary), use_container_width=True, hide_index=True)
        else:
            render_html_table(
                "Product performance",
                product_summary,
                ["Product", "Category", "Orders", "Quantity", "Revenue", "Profit", "MarginPct", "RevenueSharePct"],
            )
    with tab2:
        if filtered_df is not None:
            st.dataframe(pd.DataFrame(category_summary), use_container_width=True, hide_index=True)
        else:
            render_html_table(
                "Category performance",
                category_summary,
                ["Category", "Orders", "Quantity", "Revenue", "Profit", "MarginPct", "RevenueSharePct"],
            )
    with tab3:
        if filtered_df is not None:
            st.dataframe(pd.DataFrame(monthly_summary), use_container_width=True, hide_index=True)
        else:
            render_html_table(
                "Monthly performance",
                monthly_summary,
                ["Month", "Orders", "Quantity", "Revenue", "Profit", "MarginPct", "AvgOrderValue"],
            )

    st.caption(
        "Expansion score is a heuristic that rewards margin strength, repeat demand, and lower concentration risk."
    )


def run_cli_fallback() -> None:
    rows = load_sales_data(DATA_FILE)
    overview = compute_overview(rows)
    opportunities = calculate_expansion_opportunities(rows)[:3]
    insights = generate_business_insights(rows)

    print("Sales Expansion Analysis")
    print("========================")
    print(f"Orders        : {overview['Orders']}")
    print(f"Revenue       : {overview['Revenue']}")
    print(f"Profit        : {overview['Profit']}")
    print(f"Profit Margin : {overview['ProfitMarginPct']:.2f}%")
    print()
    print("Top Expansion Candidates")
    for item in opportunities:
        print(
            f"- {item['Product']}: score {item['ExpansionScore']:.1f}, "
            f"margin {item['MarginPct']:.1f}%, why: {item['WhyScale']}"
        )
    print()
    print("Business Expansion Insights")
    for insight in insights:
        print(f"- {insight['title']}: {insight['detail']} {insight['action']}")
    print()
    print("To launch the interactive dashboard, install Streamlit and run:")
    print("streamlit run main.py")


def main() -> None:
    if st is None:
        run_cli_fallback()
    else:
        run_streamlit_app()


if __name__ == "__main__":
    main()
