"""Diagram creator tool for cheatsheet generation."""

from __future__ import annotations

import uuid
from pathlib import Path

DIAGRAMS_DIR = Path("data/diagrams")

CREATE_DIAGRAM_TOOL_SCHEMA = {
    "name": "create_diagram",
    "description": (
        "Create a diagram image (flowchart, comparison table, or linear pathway) "
        "that will be embedded in the cheatsheet PDF. "
        "Use for complex multi-step processes, comparative data, or signalling pathways."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "diagram_type": {
                "type": "string",
                "enum": ["flowchart", "table", "pathway"],
                "description": "flowchart=nodes+edges, table=headers+rows, pathway=linear steps",
            },
            "title": {"type": "string", "description": "Short diagram title (≤6 words)"},
            "nodes": {
                "type": "array",
                "items": {"type": "string"},
                "description": "flowchart/pathway: step labels (≤4 words each, max 8)",
            },
            "edges": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "from": {"type": "integer"},
                        "to":   {"type": "integer"},
                    },
                },
                "description": "flowchart only: directed edges by node index",
            },
            "headers": {
                "type": "array",
                "items": {"type": "string"},
                "description": "table: column headers (max 4 columns)",
            },
            "rows": {
                "type": "array",
                "items": {"type": "array", "items": {"type": "string"}},
                "description": "table: cell values (max 6 rows)",
            },
        },
        "required": ["diagram_type", "title"],
    },
}


def create_diagram(
    diagram_type: str,
    title: str,
    nodes: list[str] | None = None,
    edges: list[dict] | None = None,
    headers: list[str] | None = None,
    rows: list[list[str]] | None = None,
) -> str:
    """Render a diagram to PNG and return its static URL (/static/diagrams/<id>.png)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    DIAGRAMS_DIR.mkdir(parents=True, exist_ok=True)
    diagram_id = uuid.uuid4().hex[:8]
    output_path = DIAGRAMS_DIR / f"{diagram_id}.png"

    fig, ax = plt.subplots(figsize=(5.5, 3.2), dpi=150)
    ax.axis("off")
    ax.set_title(title, fontsize=9, fontweight="bold", color="#003262", pad=6)

    if diagram_type == "table" and headers and rows:
        _draw_table(ax, headers, rows)
    elif diagram_type == "pathway" and nodes:
        _draw_pathway(ax, nodes)
    elif diagram_type == "flowchart" and nodes:
        _draw_flowchart(ax, nodes, edges or [])

    plt.tight_layout(pad=0.5)
    plt.savefig(str(output_path), dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)

    return f"/static/diagrams/{diagram_id}.png"


def _draw_table(ax, headers: list[str], rows: list[list[str]]) -> None:
    import matplotlib.pyplot as plt

    n_cols = len(headers)
    col_w = 1.0 / n_cols

    for j, h in enumerate(headers):
        ax.add_patch(plt.Rectangle((j * col_w, 0.85), col_w, 0.13,
                                   facecolor="#003262", transform=ax.transAxes, clip_on=False))
        ax.text((j + 0.5) * col_w, 0.915, h, ha="center", va="center",
                fontsize=7, fontweight="bold", color="white", transform=ax.transAxes)

    n_rows = min(len(rows), 6)
    row_h = 0.85 / n_rows if n_rows else 0.85
    for i, row in enumerate(rows[:n_rows]):
        y = 0.85 - (i + 1) * row_h
        bg = "#f0f4f8" if i % 2 == 0 else "white"
        for j, cell in enumerate(row[:n_cols]):
            ax.add_patch(plt.Rectangle((j * col_w, y), col_w, row_h,
                                       facecolor=bg, edgecolor="#cccccc", linewidth=0.5,
                                       transform=ax.transAxes, clip_on=False))
            ax.text((j + 0.5) * col_w, y + row_h / 2, str(cell),
                    ha="center", va="center", fontsize=6.5, transform=ax.transAxes, wrap=True)

    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)


def _draw_pathway(ax, nodes: list[str]) -> None:
    n = len(nodes)
    xs = [i / max(n - 1, 1) for i in range(n)]
    for i, (x, label) in enumerate(zip(xs, nodes)):
        ax.text(x, 0.5, label, ha="center", va="center", fontsize=7.5,
                bbox=dict(boxstyle="round,pad=0.3", facecolor="#FDB515",
                          edgecolor="#003262", linewidth=1.5),
                transform=ax.transAxes)
        if i < n - 1:
            ax.annotate(
                "", xy=(xs[i + 1] - 0.06, 0.5), xytext=(x + 0.06, 0.5),
                xycoords="axes fraction", textcoords="axes fraction",
                arrowprops=dict(arrowstyle="->", color="#003262", lw=1.5),
            )
    ax.set_xlim(0, 1)
    ax.set_ylim(0.2, 0.8)


def _draw_flowchart(ax, nodes: list[str], edges: list[dict]) -> None:
    n = len(nodes)
    cols = min(3, n)
    n_rows = (n + cols - 1) // cols

    positions: dict[int, tuple[float, float]] = {}
    for i, label in enumerate(nodes):
        col_i = i % cols
        row_i = i // cols
        x = (col_i + 0.5) / cols
        y = 1.0 - (row_i + 0.5) / n_rows
        positions[i] = (x, y)
        ax.text(x, y, label, ha="center", va="center", fontsize=7,
                bbox=dict(boxstyle="round,pad=0.25", facecolor="#e8f0fe",
                          edgecolor="#003262", linewidth=1.2),
                transform=ax.transAxes)

    for edge in edges:
        src, dst = edge.get("from", 0), edge.get("to", 0)
        if src in positions and dst in positions:
            x0, y0 = positions[src]
            x1, y1 = positions[dst]
            ax.annotate(
                "", xy=(x1, y1), xytext=(x0, y0),
                xycoords="axes fraction", textcoords="axes fraction",
                arrowprops=dict(arrowstyle="->", color="#003262", lw=1.2,
                                connectionstyle="arc3,rad=0.05"),
            )

    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
