from __future__ import annotations

import io
import math
import textwrap
from datetime import date, datetime

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import FancyBboxPatch
import numpy as np


PAGE = (11.69, 8.27)  # A4 landscape
NAVY = "#0F172A"
NAVY_2 = "#172033"
PANEL = "#F8FAFC"
BORDER = "#DCE3EC"
TEXT = "#172033"
MUTED = "#64748B"
BLUE = "#2563EB"
BLUE_2 = "#3B82F6"
GREEN = "#15803D"
AMBER = "#B45309"
RED = "#B91C1C"
WHITE = "#FFFFFF"
GRID = "#E8EDF3"


def _q(name):
    return '"' + str(name).replace('"', '""') + '"'


def _safe(v):
    if v is None:
        return "-"
    if isinstance(v, (datetime, date)):
        return v.strftime("%Y-%m-%d")
    return str(v)


def _fmt(v):
    if v is None:
        return "-"
    try:
        x = float(v)
        if math.isnan(x):
            return "-"
        if abs(x) >= 1_000_000:
            return f"{x:,.0f}"
        if abs(x) >= 1_000:
            return f"{x:,.1f}"
        if abs(x) >= 100:
            return f"{x:,.1f}"
        if abs(x) >= 10:
            return f"{x:,.2f}"
        return f"{x:,.3f}".rstrip("0").rstrip(".")
    except Exception:
        return _safe(v)


def _short(v, n=24):
    s = _safe(v).replace("\n", " ")
    return s if len(s) <= n else s[: n - 1] + "..."


def _title(fig, title, subtitle=None, section=None):
    fig.patch.set_facecolor(WHITE)
    fig.text(0.055, 0.925, title, fontsize=22, fontweight="bold", color=TEXT, va="top")
    if subtitle:
        fig.text(0.055, 0.885, subtitle, fontsize=9.5, color=MUTED, va="top")
    if section:
        fig.text(0.945, 0.925, section.upper(), fontsize=8, color=BLUE, ha="right", va="top", fontweight="bold")
    fig.lines.append(plt.Line2D([0.055, 0.945], [0.855, 0.855], transform=fig.transFigure, color=BORDER, linewidth=0.8))


def _footer(fig, page_no):
    fig.text(0.055, 0.025, "ALTA SCIENTIA AI  *  Automated Exploratory Data Analysis", fontsize=7.2, color=MUTED)
    fig.text(0.945, 0.025, f"Page {page_no}", fontsize=7.2, color=MUTED, ha="right")


def _card(fig, x, y, w, h, label, value, detail="", accent=BLUE, value_size=20):
    fig.patches.append(
        FancyBboxPatch(
            (x, y),
            w,
            h,
            boxstyle="round,pad=0.006,rounding_size=0.012",
            transform=fig.transFigure,
            facecolor=WHITE,
            edgecolor=BORDER,
            linewidth=0.8,
        )
    )

    # Accent strip
    fig.patches.append(
        FancyBboxPatch(
            (x, y),
            0.007,
            h,
            boxstyle="round,pad=0,rounding_size=0.004",
            transform=fig.transFigure,
            facecolor=accent,
            edgecolor=accent,
        )
    )

    # Label
    fig.text(
        x + 0.022,
        y + h - 0.025,
        label.upper(),
        fontsize=7.0,
        color=MUTED,
        fontweight="bold",
        va="top",
    )

    # Main value
    fig.text(
        x + 0.022,
        y + h - 0.064,
        str(value),
        fontsize=value_size,
        color=TEXT,
        fontweight="bold",
        va="top",
    )

    # Supporting detail
    if detail:
        fig.text(
            x + 0.022,
            y + 0.018,
            str(detail),
            fontsize=7.0,
            color=MUTED,
            va="bottom",
        )

def _new_page(pdf, page_no, title, subtitle=None, section=None):
    fig = plt.figure(figsize=PAGE, dpi=150)
    _title(fig, title, subtitle, section)
    _footer(fig, page_no)
    return fig


def _save(pdf, fig):
    pdf.savefig(fig, facecolor=fig.get_facecolor())
    plt.close(fig)


def _table(ax, data, columns, fontsize=7.2, header_color=NAVY):
    ax.axis("off")
    tbl = ax.table(cellText=data, colLabels=columns, loc="center", cellLoc="left", colLoc="left", edges="closed")
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(fontsize)
    tbl.scale(1, 1.55)
    for (r, c), cell in tbl.get_celld().items():
        cell.set_edgecolor(BORDER)
        cell.set_linewidth(0.45)
        if r == 0:
            cell.set_facecolor(header_color)
            cell.get_text().set_color(WHITE)
            cell.get_text().set_fontweight("bold")
        else:
            cell.set_facecolor(WHITE if r % 2 else PANEL)
            cell.get_text().set_color(TEXT)
    return tbl


def _schema(dataset):
    rows = dataset.con.execute("DESCRIBE main_table").fetchall()
    return [(str(r[0]), str(r[1])) for r in rows]


def _classify(schema):
    numeric = []
    categorical = []
    dates = []
    for name, typ in schema:
        t = typ.upper()
        if any(k in t for k in ("DATE", "TIMESTAMP", "TIME")):
            dates.append(name)
        elif any(k in t for k in ("INT", "DECIMAL", "NUMERIC", "DOUBLE", "FLOAT", "REAL", "HUGEINT")) and "BOOL" not in t:
            numeric.append(name)
        else:
            categorical.append(name)
    return numeric, categorical, dates


def _column_stats(dataset, schema):
    out = []
    for name, typ in schema:
        q = _q(name)
        row = dataset.con.execute(f"SELECT COUNT(*) - COUNT({q}), COUNT(DISTINCT {q}) FROM main_table").fetchone()
        nulls = int(row[0] or 0)
        distinct = int(row[1] or 0)
        min_v = max_v = None
        if "BOOL" not in typ.upper():
            try:
                min_v, max_v = dataset.con.execute(f"SELECT MIN({q}), MAX({q}) FROM main_table").fetchone()
            except Exception:
                pass
        out.append({"name": name, "type": typ, "nulls": nulls, "distinct": distinct, "min": min_v, "max": max_v})
    return out


def _numeric_values(dataset, col, limit=5000):
    q = _q(col)
    rows = dataset.con.execute(f"SELECT TRY_CAST({q} AS DOUBLE) FROM main_table WHERE TRY_CAST({q} AS DOUBLE) IS NOT NULL LIMIT {int(limit)}").fetchall()
    return np.array([float(r[0]) for r in rows], dtype=float)


def _category_counts(dataset, col, limit=8):
    q = _q(col)
    rows = dataset.con.execute(f"SELECT COALESCE(CAST({q} AS VARCHAR),'(null)') AS value, COUNT(*) AS n FROM main_table GROUP BY 1 ORDER BY n DESC LIMIT {int(limit)}").fetchall()
    return [(str(r[0]), int(r[1])) for r in rows]


def _date_series(dataset, date_col, metric_col=None):
    dq = _q(date_col)
    if metric_col:
        mq = _q(metric_col)
        sql = f"SELECT CAST({dq} AS DATE), SUM(TRY_CAST({mq} AS DOUBLE)) FROM main_table WHERE {dq} IS NOT NULL GROUP BY 1 ORDER BY 1"
    else:
        sql = f"SELECT CAST({dq} AS DATE), COUNT(*) FROM main_table WHERE {dq} IS NOT NULL GROUP BY 1 ORDER BY 1"
    return dataset.con.execute(sql).fetchall()


def _choose_metric(numeric):
    preferred = ("revenue", "sales", "amount", "total", "profit", "income", "units_sold", "quantity")
    for key in preferred:
        for c in numeric:
            if key in c.lower():
                return c
    return numeric[0] if numeric else None


def _correlations(dataset, numeric):
    pairs = []
    for i, a in enumerate(numeric):
        for b in numeric[i + 1:]:
            try:
                r = dataset.con.execute(f"SELECT CORR(TRY_CAST({_q(a)} AS DOUBLE), TRY_CAST({_q(b)} AS DOUBLE)) FROM main_table").fetchone()[0]
                if r is not None and math.isfinite(float(r)):
                    pairs.append((a, b, float(r)))
            except Exception:
                pass
    pairs.sort(key=lambda x: abs(x[2]), reverse=True)
    return pairs


def _cover(pdf, dataset, schema, numeric, categorical, dates):
    fig = plt.figure(figsize=PAGE, dpi=150)
    fig.patch.set_facecolor(NAVY)

    fig.patches.append(
        FancyBboxPatch(
            (0.07, 0.12),
            0.86,
            0.76,
            boxstyle="round,pad=0.015,rounding_size=0.025",
            transform=fig.transFigure,
            facecolor=NAVY_2,
            edgecolor="#334155",
            linewidth=1.2,
        )
    )

    fig.text(
        0.10,
        0.80,
        "ALTA SCIENTIA AI",
        fontsize=9,
        color="#93C5FD",
        fontweight="bold",
    )

    fig.text(
        0.10,
        0.69,
        "DATA ANALYTICS",
        fontsize=30,
        color=WHITE,
        fontweight="bold",
    )

    fig.text(
        0.10,
        0.625,
        "Exploratory Data Analysis Report",
        fontsize=16,
        color="#CBD5E1",
    )

    fig.text(
        0.10,
        0.545,
        "Professional automated dataset assessment",
        fontsize=10,
        color="#94A3B8",
    )

    filename = getattr(dataset, "filename", "Dataset")

    fig.text(
        0.10,
        0.47,
        str(filename),
        fontsize=13,
        color=WHITE,
        fontweight="bold",
    )

    rows = int(getattr(dataset, "row_count", 0))
    columns = int(len(schema))
    numeric_count = int(len(numeric))
    categorical_count = int(len(categorical))
    date_count = int(len(dates))

    _card(
        fig,
        0.10,
        0.23,
        0.18,
        0.13,
        "Rows",
        f"{rows:,}",
        "records",
        BLUE_2,
        value_size=18,
    )

    _card(
        fig,
        0.30,
        0.23,
        0.18,
        0.13,
        "Columns",
        f"{columns:,}",
        "fields",
        GREEN,
        value_size=18,
    )

    _card(
        fig,
        0.50,
        0.23,
        0.18,
        0.13,
        "Numeric",
        f"{numeric_count:,}",
        "numeric fields",
        BLUE_2,
        value_size=18,
    )

    _card(
        fig,
        0.70,
        0.23,
        0.18,
        0.13,
        "Categorical",
        f"{categorical_count:,}",
        "categorical fields",
        AMBER,
        value_size=18,
    )

    fig.text(
        0.10,
        0.175,
        f"Date / time fields: {date_count:,}",
        fontsize=8,
        color="#94A3B8",
    )

    fig.text(
        0.945,
        0.055,
        "Automated report * Generated from the uploaded dataset",
        fontsize=7.5,
        color="#64748B",
        ha="right",
    )

    _save(pdf, fig)

def _executive(pdf, dataset, stats, numeric, categorical, dates, page):
    fig = _new_page(
        pdf,
        page,
        "Executive Dashboard",
        "A high-level view of structure, completeness and analytical readiness.",
        "Overview",
    )

    rows = int(getattr(dataset, "row_count", 0))
    cols = int(len(stats))

    missing = sum(
        int(s["nulls"])
        for s in stats
    )

    total_cells = rows * cols

    missing_pct = (
        (missing / total_cells * 100)
        if total_cells
        else 0
    )

    duplicates = 0

    try:
        unique_rows = int(
            dataset.con.execute(
                "SELECT COUNT(*) FROM (SELECT * FROM main_table GROUP BY ALL)"
            ).fetchone()[0]
        )

        duplicates = max(
            0,
            rows - unique_rows,
        )

    except Exception:
        duplicates = 0

    # ---------------------------------------------------------
    # KPI CARDS
    # ---------------------------------------------------------

    _card(
        fig,
        0.055,
        0.705,
        0.195,
        0.125,
        "Rows",
        f"{rows:,}",
        "records loaded",
        BLUE,
        value_size=19,
    )

    _card(
        fig,
        0.260,
        0.705,
        0.195,
        0.125,
        "Columns",
        f"{cols:,}",
        "fields detected",
        GREEN,
        value_size=19,
    )

    _card(
        fig,
        0.465,
        0.705,
        0.195,
        0.125,
        "Missing cells",
        f"{missing_pct:.2f}%",
        f"{missing:,} of {total_cells:,}",
        AMBER,
        value_size=17,
    )

    _card(
        fig,
        0.670,
        0.705,
        0.195,
        0.125,
        "Duplicates",
        f"{duplicates:,}",
        "duplicate records",
        RED if duplicates else GREEN,
        value_size=19,
    )

    # ---------------------------------------------------------
    # DATASET COMPOSITION
    # ---------------------------------------------------------

    ax = fig.add_axes(
        [0.055, 0.165, 0.415, 0.445]
    )

    ax.axis("off")

    ax.text(
        0,
        1.04,
        "DATASET COMPOSITION",
        fontsize=9,
        color=TEXT,
        fontweight="bold",
        transform=ax.transAxes,
    )

    labels = [
        "Numeric",
        "Categorical",
        "Date / time",
    ]

    vals = [
        int(len(numeric)),
        int(len(categorical)),
        int(len(dates)),
    ]

    colors = [
        BLUE,
        AMBER,
        GREEN,
    ]

    total = max(
        sum(vals),
        1,
    )

    left = 0

    for label, val, c in zip(
        labels,
        vals,
        colors,
    ):
        ax.barh(
            [0],
            [val],
            left=left,
            height=0.30,
            color=c,
        )

        if val:
            ax.text(
                left + val / 2,
                0,
                str(val),
                ha="center",
                va="center",
                color=WHITE,
                fontsize=9,
                fontweight="bold",
            )

        left += val

    ax.set_xlim(
        0,
        total,
    )

    ax.set_yticks([])

    ax.set_xticks(
        range(
            0,
            total + 1,
            max(
                1,
                total // 5,
            ),
        )
    )

    ax.grid(
        axis="x",
        color=GRID,
        linewidth=0.6,
    )

    for spine in ax.spines.values():
        spine.set_visible(False)

    # Legend-style labels
    legend_y = -0.34

    for i, (label, val, c) in enumerate(
        zip(labels, vals, colors)
    ):
        x = 0.02 + i * 0.32

        ax.add_patch(
            plt.Rectangle(
                (x, legend_y + 0.005),
                0.018,
                0.018,
                transform=ax.transAxes,
                color=c,
                clip_on=False,
            )
        )

        ax.text(
            x + 0.028,
            legend_y,
            f"{label}: {val}",
            transform=ax.transAxes,
            fontsize=7.7,
            color=MUTED,
        )

    # ---------------------------------------------------------
    # DATA QUALITY SNAPSHOT
    # ---------------------------------------------------------

    ax2 = fig.add_axes(
        [0.535, 0.165, 0.375, 0.445]
    )

    ax2.axis("off")

    ax2.text(
        0,
        1.04,
        "DATA QUALITY SNAPSHOT",
        fontsize=9,
        color=TEXT,
        fontweight="bold",
        transform=ax2.transAxes,
    )

    completeness = max(
        0.0,
        min(
            100.0,
            100.0 - missing_pct,
        ),
    )

    duplicate_free = (
        100.0
        if rows == 0
        else max(
            0.0,
            min(
                100.0,
                100.0 - (duplicates / rows * 100.0),
            ),
        )
    )

    metrics = [
        (
            "Completeness",
            completeness,
            GREEN,
        ),
        (
            "Duplicate-free",
            duplicate_free,
            BLUE,
        ),
    ]

    for i, (label, value, color) in enumerate(metrics):

        y = 0.70 - i * 0.31

        ax2.text(
            0,
            y + 0.10,
            label,
            fontsize=8,
            color=MUTED,
            transform=ax2.transAxes,
        )

        ax2.add_patch(
            plt.Rectangle(
                (0, y),
                0.72,
                0.10,
                transform=ax2.transAxes,
                facecolor=GRID,
                edgecolor="none",
                clip_on=False,
            )
        )

        ax2.add_patch(
            plt.Rectangle(
                (0, y),
                0.72 * value / 100.0,
                0.10,
                transform=ax2.transAxes,
                facecolor=color,
                edgecolor="none",
                clip_on=False,
            )
        )

        ax2.text(
            0.77,
            y + 0.05,
            f"{value:.1f}%",
            fontsize=9,
            color=TEXT,
            fontweight="bold",
            va="center",
            transform=ax2.transAxes,
        )

    # Overall readiness
    ready = (
        missing == 0
        and duplicates == 0
    )

    ax2.text(
        0,
        0.055,
        "ANALYTICAL READINESS",
        fontsize=7.5,
        color=MUTED,
        fontweight="bold",
        transform=ax2.transAxes,
    )

    ax2.text(
        0.77,
        0.055,
        "READY" if ready else "REVIEW",
        fontsize=8,
        color=GREEN if ready else AMBER,
        fontweight="bold",
        ha="right",
        transform=ax2.transAxes,
    )

    _save(pdf, fig)

def _findings(pdf, dataset, stats, numeric, categorical, dates, page):
    fig = _new_page(pdf, page, "Key Findings", "Automatically generated observations from the dataset profile and statistical relationships.", "Insights")
    rows = int(getattr(dataset, "row_count", 0))
    missing = sum(s["nulls"] for s in stats)
    pairs = _correlations(dataset, numeric)
    metric = _choose_metric(numeric)
    findings = []
    findings.append(("Completeness", f"{missing} missing cells detected across {len(stats)} columns.", GREEN if missing == 0 else AMBER))
    findings.append(("Duplicate records", "No duplicate records detected." if rows == int(dataset.con.execute("SELECT COUNT(*) FROM (SELECT * FROM main_table GROUP BY ALL)").fetchone()[0]) else "Duplicate records are present and should be reviewed.", GREEN if rows == int(dataset.con.execute("SELECT COUNT(*) FROM (SELECT * FROM main_table GROUP BY ALL)").fetchone()[0]) else RED))
    if pairs:
        a,b,r = pairs[0]
        findings.append(("Strongest relationship", f"{a} and {b} show Pearson correlation of {r:.2f}.", BLUE))
    if metric:
        try:
            avg = dataset.con.execute(f"SELECT AVG(TRY_CAST({_q(metric)} AS DOUBLE)) FROM main_table").fetchone()[0]
            findings.append(("Primary numeric metric", f"{metric} has an average of {_fmt(avg)} across {rows:,} records.", BLUE))
        except Exception:
            pass
    if categorical:
        c = categorical[0]
        try:
            distinct = next(s["distinct"] for s in stats if s["name"] == c)
            findings.append(("Category diversity", f"{c} contains {distinct} distinct values.", AMBER if distinct > 10 else BLUE))
        except Exception:
            pass
    if dates:
        findings.append(("Time dimension", f"{dates[0]} is available for time-based analysis.", GREEN))
    for i, (head, body, accent) in enumerate(findings[:6]):
        y = 0.74 - i*0.105
        fig.patches.append(FancyBboxPatch((0.075, y), 0.85, 0.075, boxstyle="round,pad=0.004,rounding_size=0.008", transform=fig.transFigure, facecolor=PANEL, edgecolor=BORDER, linewidth=0.6))
        fig.patches.append(FancyBboxPatch((0.075, y), 0.008, 0.075, boxstyle="round,pad=0,rounding_size=0.004", transform=fig.transFigure, facecolor=accent, edgecolor=accent))
        fig.text(0.105, y+0.047, head, fontsize=9, color=TEXT, fontweight="bold", va="center")
        fig.text(0.105, y+0.022, body, fontsize=8.2, color=MUTED, va="center")
    _save(pdf, fig)


def _profile(pdf, stats, page):
    fig = _new_page(
        pdf,
        page,
        "Column Profile",
        "Detailed profile of every field: type, completeness, cardinality and observed range.",
        "Data Dictionary",
    )

    ax = fig.add_axes(
        [0.055, 0.105, 0.89, 0.715]
    )

    data = []

    for s in stats:
        data.append(
            [
                _short(s["name"], 20),
                _short(s["type"], 14),
                f"{int(s['nulls']):,}",
                f"{int(s['distinct']):,}",
                _short(s["min"], 18),
                _short(s["max"], 18),
            ]
        )

    _table(
        ax,
        data,
        [
            "Column",
            "Type",
            "Missing",
            "Distinct",
            "Minimum / First",
            "Maximum / Last",
        ],
        fontsize=7.0,
    )

    # Small explanatory note below the table
    fig.text(
        0.055,
        0.065,
        "Numeric fields show observed minimum and maximum values; "
        "non-numeric fields show the first and last observed values.",
        fontsize=7.2,
        color=MUTED,
    )

    _save(pdf, fig)

def _missing(pdf, stats, page):
    fig = _new_page(
        pdf,
        page,
        "Data Quality & Missing Values",
        "Missing-cell distribution and overall dataset quality assessment.",
        "Data Quality",
    )

    items = [
        (s["name"], int(s["nulls"]))
        for s in stats
        if int(s["nulls"]) > 0
    ]

    total_missing = sum(value for _, value in items)

    if not items:
        ax = fig.add_axes([0.055, 0.235, 0.42, 0.42])
        ax.axis("off")

        circle = plt.Circle(
            (0.5, 0.56),
            0.19,
            transform=ax.transAxes,
            facecolor="#E8F7EE",
            edgecolor="#22C55E",
            linewidth=2.0,
        )
        ax.add_patch(circle)

        ax.text(
            0.5,
            0.56,
            "OK",
            ha="center",
            va="center",
            fontsize=18,
            fontweight="bold",
            color="#15803D",
            transform=ax.transAxes,
        )

        ax.text(
            0.5,
            0.19,
            "DATASET COMPLETE",
            ha="center",
            va="center",
            fontsize=10,
            fontweight="bold",
            color=TEXT,
            transform=ax.transAxes,
        )

        ax.text(
            0.5,
            0.08,
            "No missing values were detected across the uploaded fields.",
            ha="center",
            va="center",
            fontsize=7.5,
            color=MUTED,
            transform=ax.transAxes,
        )

    else:
        ax = fig.add_axes([0.055, 0.235, 0.50, 0.42])

        names = [_short(name, 22) for name, _ in items]
        values = [value for _, value in items]

        y = np.arange(len(names))

        ax.barh(
            y,
            values,
            height=0.55,
            color=BLUE,
        )

        ax.set_yticks(y)
        ax.set_yticklabels(names, fontsize=7.5)
        ax.invert_yaxis()

        ax.set_xlabel(
            "Missing cells",
            fontsize=7.5,
            color=MUTED,
        )

        ax.tick_params(
            axis="x",
            labelsize=7,
            colors=MUTED,
        )

        ax.tick_params(
            axis="y",
            colors=TEXT,
        )

        ax.grid(
            axis="x",
            alpha=0.18,
        )

        ax.set_axisbelow(True)

        for spine in ax.spines.values():
            spine.set_visible(False)

        for yi, value in zip(y, values):
            ax.text(
                value,
                yi,
                f"  {value:,}",
                va="center",
                fontsize=7,
                color=TEXT,
            )

    summary_x = 0.62
    summary_y = 0.235
    summary_w = 0.325
    summary_h = 0.42

    fig.patches.append(
        FancyBboxPatch(
            (summary_x, summary_y),
            summary_w,
            summary_h,
            boxstyle="round,pad=0.006,rounding_size=0.012",
            transform=fig.transFigure,
            facecolor=WHITE,
            edgecolor=BORDER,
            linewidth=0.8,
        )
    )

    fig.text(
        summary_x + 0.025,
        summary_y + summary_h - 0.045,
        "QUALITY SUMMARY",
        fontsize=8,
        fontweight="bold",
        color=TEXT,
    )

    status = "Complete" if not items else "Review"
    status_color = "#15803D" if not items else "#B45309"

    fig.text(
        summary_x + 0.025,
        summary_y + summary_h - 0.105,
        "STATUS",
        fontsize=7,
        fontweight="bold",
        color=MUTED,
    )

    fig.text(
        summary_x + 0.025,
        summary_y + summary_h - 0.145,
        status,
        fontsize=16,
        fontweight="bold",
        color=status_color,
    )

    fig.text(
        summary_x + 0.025,
        summary_y + summary_h - 0.205,
        "Missing cells",
        fontsize=7,
        color=MUTED,
    )

    fig.text(
        summary_x + 0.025,
        summary_y + summary_h - 0.235,
        f"{total_missing:,}",
        fontsize=11,
        fontweight="bold",
        color=TEXT,
    )

    fig.text(
        summary_x + 0.025,
        summary_y + summary_h - 0.295,
        "Fields assessed",
        fontsize=7,
        color=MUTED,
    )

    fig.text(
        summary_x + 0.025,
        summary_y + summary_h - 0.325,
        f"{len(stats):,}",
        fontsize=11,
        fontweight="bold",
        color=TEXT,
    )

    note = (
        "All fields complete"
        if not items
        else f"{len(items):,} field(s) need review"
    )

    fig.text(
        summary_x + 0.025,
        summary_y + 0.045,
        note,
        fontsize=7.2,
        color=MUTED,
    )

    _save(pdf, fig)

def _distributions(pdf, dataset, numeric, page_start):
    page = page_start
    cols = numeric[:12]
    for start in range(0, len(cols), 4):
        chunk = cols[start:start+4]
        fig = _new_page(pdf, page, "Numeric Distributions", "Frequency distributions with median markers and descriptive statistics.", "Distributions")
        for j, col in enumerate(chunk):
            r, c = divmod(j, 2)
            ax = fig.add_axes([0.07 + c*0.44, 0.49 - r*0.35, 0.37, 0.25])
            vals = _numeric_values(dataset, col)
            if len(vals):
                ax.hist(vals, bins=min(12, max(5, int(math.sqrt(len(vals))))), color=BLUE_2, edgecolor=WHITE, linewidth=0.6)
                med = float(np.median(vals))
                ax.axvline(med, color=RED, linewidth=1.4, linestyle="--")
                ax.text(0.98, 0.90, f"Median {_fmt(med)}", transform=ax.transAxes, ha="right", fontsize=7.5, color=RED, fontweight="bold")
            ax.set_title(_short(col, 28), loc="left", fontsize=9, fontweight="bold", color=TEXT)
            ax.tick_params(labelsize=6.5, colors=MUTED)
            ax.grid(axis="y", color=GRID, linewidth=0.55)
            for spine in ax.spines.values(): spine.set_visible(False)
        _save(pdf, fig)
        page += 1
    return page



def _boxplots(pdf, dataset, numeric, page):
    fig = _new_page(
        pdf,
        page,
        "Outlier & Spread Analysis",
        "Standardized boxplots make variation and outliers comparable across numeric fields.",
        "Distribution & Outliers",
    )

    if not numeric:
        fig.text(
            0.055,
            0.50,
            "No numeric fields are available for outlier analysis.",
            fontsize=11,
            color=MUTED,
        )
        _save(pdf, fig)
        return

    values_by_column = {}
    display_names = []

    for col in numeric:
        vals = _numeric_values(dataset, col)

        if vals.size == 0:
            continue

        vals = np.asarray(vals, dtype=float)
        vals = vals[np.isfinite(vals)]

        if vals.size == 0:
            continue

        values_by_column[col] = vals
        display_names.append(_short(col, 20))

    if not values_by_column:
        fig.text(
            0.055,
            0.50,
            "No usable numeric values are available for outlier analysis.",
            fontsize=11,
            color=MUTED,
        )
        _save(pdf, fig)
        return

    standardized = []

    for col in values_by_column:
        vals = values_by_column[col]

        mean = float(np.mean(vals))
        std = float(np.std(vals))

        if std > 0:
            z = (vals - mean) / std
        else:
            z = np.zeros_like(vals)

        standardized.append(z)

    ax = fig.add_axes(
        [0.065, 0.245, 0.86, 0.48]
    )

    box = ax.boxplot(
        standardized,
        patch_artist=True,
        vert=True,
        widths=0.58,
        showfliers=True,
        medianprops={
            "color": NAVY,
            "linewidth": 1.5,
        },
        whiskerprops={
            "color": MUTED,
            "linewidth": 0.9,
        },
        capprops={
            "color": MUTED,
            "linewidth": 0.9,
        },
        flierprops={
            "marker": "o",
            "markersize": 3,
            "markerfacecolor": BLUE,
            "markeredgecolor": BLUE,
            "alpha": 0.55,
        },
    )

    for patch in box["boxes"]:
        patch.set_facecolor("#E8F0FF")
        patch.set_edgecolor(BLUE)
        patch.set_linewidth(0.9)

    ax.set_xticks(
        np.arange(1, len(display_names) + 1)
    )

    ax.set_xticklabels(
        display_names,
        rotation=35,
        ha="right",
        fontsize=7.2,
    )

    ax.set_ylabel(
        "Standardized value (z-score)",
        fontsize=7.8,
        color=MUTED,
    )

    ax.axhline(
        0,
        color=BORDER,
        linewidth=0.8,
    )

    ax.grid(
        axis="y",
        alpha=0.18,
    )

    ax.set_axisbelow(True)

    ax.tick_params(
        axis="y",
        labelsize=7,
        colors=MUTED,
    )

    for spine in ax.spines.values():
        spine.set_visible(False)

    fig.text(
        0.065,
        0.155,
        "How to read",
        fontsize=8,
        fontweight="bold",
        color=TEXT,
    )

    fig.text(
        0.065,
        0.125,
        "The center line represents the median. The box captures the middle 50% of observations, "
        "while points beyond the whiskers indicate potential outliers.",
        fontsize=7.2,
        color=MUTED,
    )

    fig.text(
        0.065,
        0.085,
        "Values are standardized only for visual comparison across fields; original units are preserved "
        "in the column profile and analytical summary.",
        fontsize=7.2,
        color=MUTED,
    )

    _save(pdf, fig)

def _categorical(pdf, dataset, categorical, page_start):
    page = page_start

    # Date-like fields are handled by the dedicated time-series section.
    cols = [
        c for c in categorical
        if "date" not in c.lower()
        and "time" not in c.lower()
    ][:6]

    for start in range(0, len(cols), 2):
        chunk = cols[start:start + 2]

        fig = _new_page(
            pdf,
            page,
            "Categorical Analysis",
            "Distribution of the most frequent categories. Date/time fields are analyzed separately.",
            "Categories",
        )

        for j, col in enumerate(chunk):
            ax = fig.add_axes(
                [0.08 + j * 0.45, 0.28, 0.37, 0.45]
            )

            items = _category_counts(dataset, col, 8)

            if not items:
                continue

            labels = [_short(x[0], 22) for x in items][::-1]
            vals = [x[1] for x in items][::-1]

            ax.barh(
                labels,
                vals,
                color=BLUE_2,
                height=0.62,
            )

            ax.set_title(
                _short(col, 28),
                loc="left",
                fontsize=10,
                fontweight="bold",
                color=TEXT,
                pad=8,
            )

            ax.tick_params(
                labelsize=7,
                colors=MUTED,
            )

            ax.grid(
                axis="x",
                color=GRID,
                linewidth=0.55,
            )

            for spine in ax.spines.values():
                spine.set_visible(False)

            max_value = max(vals) if vals else 1

            for y, value in enumerate(vals):
                pct = value / sum(vals) * 100 if sum(vals) else 0

                ax.text(
                    value + max_value * 0.025,
                    y,
                    f"{value:,} ({pct:.0f}%)",
                    va="center",
                    fontsize=7,
                    color=TEXT,
                )

            ax.set_xlim(
                0,
                max_value * 1.28 if max_value else 1,
            )

            # Small interpretation beneath each chart.
            top_label = labels[-1] if labels else ""
            top_value = vals[-1] if vals else 0

            fig.text(
                0.08 + j * 0.45,
                0.20,
                f"Most frequent: {top_label} ({top_value:,} records)",
                fontsize=7.5,
                color=MUTED,
            )

        _save(pdf, fig)
        page += 1

    return page


def _time_series(pdf, dataset, dates, numeric, page):
    if not dates:
        return page

    date_col = dates[0]

    # Prefer business-relevant metrics when they exist.
    preferred = [
        "revenue",
        "units_sold",
        "marketing_spend",
        "returns",
        "return_rate",
    ]

    available = [
        c for c in preferred
        if c in numeric
    ]

    if not available:
        available = numeric[:3]

    if not available:
        return page

    series = []

    for metric in available[:3]:
        rows = _date_series(dataset, date_col, metric)

        if rows:
            series.append(
                (
                    metric,
                    [r[0] for r in rows],
                    [float(r[1] or 0) for r in rows],
                )
            )

    if not series:
        return page

    fig = _new_page(
        pdf,
        page,
        "Time-Series Analysis",
        f"Daily trends using {date_col}.",
        "Trend",
    )

    ax = fig.add_axes([0.09, 0.27, 0.82, 0.47])

    # Plot up to three metrics on normalized scales so different units
    # remain visually comparable.
    for metric, x, y in series:
        if not y:
            continue

        y_arr = np.asarray(y, dtype=float)

        if np.max(y_arr) == np.min(y_arr):
            normalized = np.zeros_like(y_arr)
        else:
            normalized = (
                (y_arr - np.min(y_arr))
                / (np.max(y_arr) - np.min(y_arr))
            )

        ax.plot(
            x,
            normalized,
            marker="o",
            markersize=3,
            linewidth=1.8,
            label=metric,
        )

    ax.set_ylabel(
        "Normalized metric value",
        color=MUTED,
        fontsize=8,
    )

    ax.grid(
        axis="y",
        color=GRID,
        linewidth=0.6,
    )

    ax.tick_params(
        axis="x",
        labelsize=7,
        colors=MUTED,
    )

    ax.tick_params(
        axis="y",
        labelsize=7,
        colors=MUTED,
    )

    for spine in ax.spines.values():
        spine.set_visible(False)

    ax.legend(
        loc="upper left",
        frameon=False,
        fontsize=7,
    )

    # Analytical cards beneath the chart.
    card_y = 0.10
    card_w = 0.25

    for i, (metric, x, y) in enumerate(series[:3]):
        if not y:
            continue

        peak_i = int(np.argmax(y))
        low_i = int(np.argmin(y))

        _card(
            fig,
            0.09 + i * 0.28,
            card_y,
            card_w,
            0.10,
            metric.upper(),
            _fmt(y[peak_i]),
            f"Peak: {_safe(x[peak_i])}",
            accent=BLUE if i == 0 else BLUE_2,
            value_size=13,
        )

    fig.text(
        0.09,
        0.20,
        "Lines are normalized independently because the metrics may use different units. "
        "Cards below retain the original metric values.",
        fontsize=7.2,
        color=MUTED,
    )

    _save(pdf, fig)

    return page + 1


def _correlation(pdf, dataset, numeric, page):
    fig = _new_page(
        pdf,
        page,
        "Correlation Analysis",
        "Pairwise Pearson correlations across numeric fields.",
        "Relationships",
    )

    if len(numeric) < 2:
        fig.text(
            0.055,
            0.50,
            "At least two numeric fields are required for correlation analysis.",
            fontsize=11,
            color=MUTED,
        )
        _save(pdf, fig)
        return page + 1

    pairs = _correlations(dataset, numeric)

    if not pairs:
        fig.text(
            0.055,
            0.50,
            "Correlation analysis could not be computed for the available numeric fields.",
            fontsize=11,
            color=MUTED,
        )
        _save(pdf, fig)
        return page + 1

    columns = list(numeric)
    index = {name: i for i, name in enumerate(columns)}
    n = len(columns)

    matrix = np.eye(n, dtype=float)

    for a, b, r in pairs:
        if a in index and b in index:
            i = index[a]
            j = index[b]
            matrix[i, j] = r
            matrix[j, i] = r

    labels = [
        _short(str(col), 22)
        for col in columns
    ]

    left = 0.12
    bottom = 0.22
    width = 0.76
    height = 0.58

    ax = fig.add_axes(
        [left, bottom, width, height]
    )

    image = ax.imshow(
        matrix,
        vmin=-1,
        vmax=1,
        cmap="RdBu_r",
        aspect="auto",
    )

    ax.set_xticks(np.arange(n))
    ax.set_yticks(np.arange(n))

    ax.set_xticklabels(
        labels,
        rotation=45,
        ha="right",
        fontsize=7.0,
    )

    ax.set_yticklabels(
        labels,
        fontsize=7.0,
    )

    ax.tick_params(
        length=0,
    )

    for spine in ax.spines.values():
        spine.set_visible(False)

    for i in range(n):
        for j in range(n):
            value = matrix[i, j]

            if not np.isfinite(value):
                continue

            text_color = (
                "white"
                if abs(value) >= 0.55
                else TEXT
            )

            ax.text(
                j,
                i,
                f"{value:.2f}",
                ha="center",
                va="center",
                fontsize=6.8,
                fontweight="bold",
                color=text_color,
            )

    cbar = fig.colorbar(
        image,
        ax=ax,
        fraction=0.035,
        pad=0.025,
    )

    cbar.set_label(
        "Pearson correlation",
        fontsize=7.5,
        color=MUTED,
    )

    cbar.ax.tick_params(
        labelsize=7,
        colors=MUTED,
        length=0,
    )

    fig.text(
        0.12,
        0.135,
        "Interpretation",
        fontsize=8,
        fontweight="bold",
        color=TEXT,
    )

    fig.text(
        0.12,
        0.105,
        "Values near +1 indicate a strong positive linear relationship, while values near -1 "
        "indicate a strong negative linear relationship. Values near 0 indicate weak linear association.",
        fontsize=7.2,
        color=MUTED,
    )

    fig.text(
        0.12,
        0.072,
        "Correlation measures association, not causation.",
        fontsize=7.2,
        color=MUTED,
        fontweight="bold",
    )

    _save(pdf, fig)
    return page + 1

def _scatter(pdf, dataset, numeric, page):
    pairs = _correlations(dataset, numeric)

    if not pairs:
        return page

    # Show up to the three strongest relationships on one page.
    selected = pairs[:3]

    fig = _new_page(
        pdf,
        page,
        "Relationship Analysis",
        "Scatter plots for the strongest observed numeric relationships.",
        "Relationships",
    )

    positions = [
        (0.08, 0.48, 0.38, 0.32),
        (0.54, 0.48, 0.38, 0.32),
        (0.31, 0.10, 0.38, 0.32),
    ]

    plotted = 0

    for index, (a, b, r) in enumerate(selected):
        rows = dataset.con.execute(
            f"""
            SELECT
                TRY_CAST({_q(a)} AS DOUBLE),
                TRY_CAST({_q(b)} AS DOUBLE)
            FROM main_table
            WHERE
                TRY_CAST({_q(a)} AS DOUBLE) IS NOT NULL
                AND TRY_CAST({_q(b)} AS DOUBLE) IS NOT NULL
            LIMIT 1000
            """
        ).fetchall()

        if not rows:
            continue

        x = np.array([float(z[0]) for z in rows])
        y = np.array([float(z[1]) for z in rows])

        ax = fig.add_axes(positions[plotted])

        ax.scatter(
            x,
            y,
            s=22,
            alpha=0.68,
            color=BLUE,
            edgecolors=WHITE,
            linewidths=0.35,
        )

        if len(x) >= 2 and np.std(x) > 0:
            slope, intercept = np.polyfit(x, y, 1)

            xx = np.linspace(
                x.min(),
                x.max(),
                100,
            )

            ax.plot(
                xx,
                slope * xx + intercept,
                color=RED,
                linewidth=1.5,
            )

        ax.set_title(
            f"{_short(a, 20)} vs {_short(b, 20)}",
            fontsize=8.5,
            color=TEXT,
            fontweight="bold",
            loc="left",
        )

        ax.set_xlabel(
            _short(a, 18),
            fontsize=6.5,
            color=MUTED,
        )

        ax.set_ylabel(
            _short(b, 18),
            fontsize=6.5,
            color=MUTED,
        )

        ax.tick_params(
            labelsize=6,
            colors=MUTED,
        )

        ax.grid(
            color=GRID,
            linewidth=0.5,
        )

        for spine in ax.spines.values():
            spine.set_visible(False)

        ax.text(
            0.98,
            0.96,
            f"r = {r:+.3f}",
            transform=ax.transAxes,
            ha="right",
            va="top",
            fontsize=8,
            color=BLUE if r >= 0 else RED,
            fontweight="bold",
        )

        plotted += 1

        if plotted >= len(positions):
            break

    if plotted == 0:
        plt.close(fig)
        return page

    fig.text(
        0.08,
        0.035,
        "The red line represents a simple linear fit. Association should not be interpreted as causation.",
        fontsize=7.2,
        color=MUTED,
    )

    _save(pdf, fig)

    return page + 1

def _sample(pdf, dataset, schema, page):
    cols=[x[0] for x in schema]
    rows=dataset.con.execute(f"SELECT * FROM main_table LIMIT 12").fetchall()
    fig=_new_page(pdf,page,"Data Preview","First 12 records from the uploaded dataset.","Sample")
    ax=fig.add_axes([0.045,0.12,0.91,0.70])
    display=[]
    for row in rows:
        display.append([_short(v,16) for v in row])
    _table(ax,display,[_short(c,15) for c in cols],fontsize=6.2)
    _save(pdf,fig)


def _summary(pdf, dataset, stats, numeric, categorical, dates, page):
    pairs=_correlations(dataset,numeric)
    metric=_choose_metric(numeric)
    fig=_new_page(pdf,page,"Analytical Summary","A concise interpretation of the automated exploratory analysis.","Conclusion")
    blocks=[]
    missing=sum(s["nulls"] for s in stats)
    blocks.append(("Dataset scale",f"The dataset contains {getattr(dataset,'row_count',0):,} records across {len(stats)} columns."))
    blocks.append(("Completeness", "No missing values were detected." if missing==0 else f"{missing:,} missing cells were detected and should be reviewed before downstream modeling."))
    blocks.append(("Analytical structure",f"The profile contains {len(numeric)} numeric, {len(categorical)} categorical and {len(dates)} date/time field(s)."))
    if metric:
        try:
            avg=dataset.con.execute(f"SELECT AVG(TRY_CAST({_q(metric)} AS DOUBLE)) FROM main_table").fetchone()[0]
            blocks.append(("Primary metric",f"{metric} has an observed average of {_fmt(avg)}."))
        except Exception: pass
    if pairs:
        a,b,r=pairs[0]; blocks.append(("Correlation",f"The strongest observed Pearson relationship is between {a} and {b}, with r = {r:+.3f}. Correlation describes association, not causation."))
    if dates: blocks.append(("Time dimension",f"{dates[0]} can support chronological trend analysis."))
    for i,(head,body) in enumerate(blocks[:6]):
        y=0.73-i*0.105
        fig.patches.append(FancyBboxPatch((0.075,y),0.85,0.075,boxstyle="round,pad=0.004,rounding_size=0.008",transform=fig.transFigure,facecolor=PANEL,edgecolor=BORDER,linewidth=0.6))
        fig.text(0.105,y+0.048,head,fontsize=9,color=TEXT,fontweight="bold",va="center")
        fig.text(0.105,y+0.022,"\n".join(textwrap.wrap(body,110)),fontsize=8.1,color=MUTED,va="center")
    _save(pdf,fig)



def generate_pdf_report(dataset) -> bytes:
    schema = _schema(dataset)
    numeric, categorical, dates = _classify(schema)
    stats = _column_stats(dataset, schema)

    buf = io.BytesIO()

    with PdfPages(buf) as pdf:
        pdf.infodict()["Title"] = "Data Analytics Report"
        pdf.infodict()["Author"] = "Alta Scientia AI"
        pdf.infodict()["Subject"] = "Automated Exploratory Data Analysis"

        page = 1

        # 01 - Cover
        _cover(
            pdf,
            dataset,
            schema,
            numeric,
            categorical,
            dates,
        )
        page += 1

        # 02 - Executive dashboard
        _executive(
            pdf,
            dataset,
            stats,
            numeric,
            categorical,
            dates,
            page,
        )
        page += 1

        # 03 - Key findings
        _findings(
            pdf,
            dataset,
            stats,
            numeric,
            categorical,
            dates,
            page,
        )
        page += 1

        # 04 - Column profile
        _profile(
            pdf,
            stats,
            page,
        )
        page += 1

        # 05 - Missing values / quality
        _missing(
            pdf,
            stats,
            page,
        )
        page += 1

        # 06 - Numerical distributions
        if numeric:
            page = _distributions(
                pdf,
                dataset,
                numeric,
                page,
            )

            # 07 - Outlier analysis
            _boxplots(
                pdf,
                dataset,
                numeric,
                page,
            )
            page += 1

        # 08 - Categorical analysis
        if categorical:
            page = _categorical(
                pdf,
                dataset,
                categorical,
                page,
            )

        # 09 - Time series
        page = _time_series(
            pdf,
            dataset,
            dates,
            numeric,
            page,
        )

        # 10 - Correlation
        page = _correlation(
            pdf,
            dataset,
            numeric,
            page,
        )

        # 11 - Relationship analysis
        page = _scatter(
            pdf,
            dataset,
            numeric,
            page,
        )

        # 12 - Data preview
        _sample(
            pdf,
            dataset,
            schema,
            page,
        )
        page += 1

        # 13 - Final analytical summary
        _summary(
            pdf,
            dataset,
            stats,
            numeric,
            categorical,
            dates,
            page,
        )

    buf.seek(0)
    return buf.read()










