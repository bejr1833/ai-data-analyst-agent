import io
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

from app.services.data_loader import Dataset
from app.services import profiler


def _title_page(pdf: PdfPages, overview: dict):
    fig, ax = plt.subplots(figsize=(11, 8.5))
    ax.axis("off")
    lines = [
        "AI Data Analyst Agent — EDA Report",
        "",
        f"Dataset: {overview['filename']}",
        f"Rows: {overview['row_count']:,}    Columns: {overview['column_count']}",
        f"Duplicate rows: {overview['duplicate_rows']:,}",
        f"Missing cells: {overview['total_missing_cells']:,} ({overview['missing_cell_pct']}%)",
        f"Numeric columns: {overview['numeric_column_count']}   "
        f"Categorical columns: {overview['categorical_column_count']}   "
        f"Datetime columns: {overview['datetime_column_count']}",
    ]
    ax.text(0.05, 0.9, lines[0], fontsize=20, weight="bold", va="top")
    ax.text(0.05, 0.78, "\n".join(lines[2:]), fontsize=12, va="top", linespacing=2.0)
    pdf.savefig(fig)
    plt.close(fig)


def _column_table_page(pdf: PdfPages, columns: list[dict]):
    rows_per_page = 25
    for start in range(0, len(columns), rows_per_page):
        chunk = columns[start:start + rows_per_page]
        fig, ax = plt.subplots(figsize=(11, 8.5))
        ax.axis("off")
        table_data = []
        for c in chunk:
            if c["type"] == "numeric":
                extra = f"mean={c.get('mean')} std={c.get('std')} min={c.get('min')} max={c.get('max')}"
            else:
                extra = f"distinct={c['distinct_count']}"
            table_data.append([c["column"], c["dtype"], f"{c['missing_pct']}%", extra])
        table = ax.table(
            cellText=table_data,
            colLabels=["Column", "Type", "Missing %", "Stats"],
            loc="center",
            cellLoc="left",
        )
        table.auto_set_font_size(False)
        table.set_fontsize(8)
        table.scale(1, 1.4)
        ax.set_title("Column Profile", fontsize=14, weight="bold")
        pdf.savefig(fig)
        plt.close(fig)


def _histogram_page(pdf: PdfPages, hist: dict):
    if not hist["counts"]:
        return
    fig, ax = plt.subplots(figsize=(11, 6))
    edges = hist["bin_edges"]
    centers = [(edges[i] + edges[i + 1]) / 2 for i in range(len(edges) - 1)] if len(edges) > 1 else edges
    widths = [(edges[i + 1] - edges[i]) for i in range(len(edges) - 1)] if len(edges) > 1 else [1]
    ax.bar(centers, hist["counts"], width=widths, edgecolor="black", alpha=0.75)
    ax.set_title(f"Distribution: {hist['column']}")
    ax.set_xlabel(hist["column"])
    ax.set_ylabel("Count")
    pdf.savefig(fig)
    plt.close(fig)


def _bar_page(pdf: PdfPages, cat: dict):
    if not cat["categories"]:
        return
    fig, ax = plt.subplots(figsize=(11, 6))
    ax.barh(cat["categories"][::-1], cat["counts"][::-1], color="#4C72B0")
    ax.set_title(f"Top categories: {cat['column']}")
    ax.set_xlabel("Count")
    pdf.savefig(fig)
    plt.close(fig)


def _missing_page(pdf: PdfPages, missing: dict):
    if not missing["columns"]:
        return
    fig, ax = plt.subplots(figsize=(11, 6))
    ax.barh(missing["columns"][::-1], missing["missing_pct"][::-1], color="#C44E52")
    ax.set_title("Missing values by column (%)")
    ax.set_xlabel("% missing")
    pdf.savefig(fig)
    plt.close(fig)


def _correlation_page(pdf: PdfPages, corr: dict):
    if not corr or len(corr["columns"]) < 2:
        return
    fig, ax = plt.subplots(figsize=(9, 8))
    im = ax.imshow(corr["matrix"], cmap="coolwarm", vmin=-1, vmax=1)
    ax.set_xticks(range(len(corr["columns"])))
    ax.set_yticks(range(len(corr["columns"])))
    ax.set_xticklabels(corr["columns"], rotation=90, fontsize=7)
    ax.set_yticklabels(corr["columns"], fontsize=7)
    ax.set_title("Correlation matrix (numeric columns)")
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    pdf.savefig(fig)
    plt.close(fig)


def generate_pdf_report(dataset: Dataset) -> bytes:
    data = profiler.build_full_report_data(dataset)
    buf = io.BytesIO()
    with PdfPages(buf) as pdf:
        _title_page(pdf, data["overview"])
        _column_table_page(pdf, data["columns"])
        for hist in data["histograms"]:
            _histogram_page(pdf, hist)
        for cat in data["categorical_charts"]:
            _bar_page(pdf, cat)
        _missing_page(pdf, data["missing_chart"])
        _correlation_page(pdf, data["correlation"])
    buf.seek(0)
    return buf.read()
