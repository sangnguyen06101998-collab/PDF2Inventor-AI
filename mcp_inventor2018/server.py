"""Local MCP server for Autodesk Inventor 2018 and PDF drawing inspection.

Run on the Windows workstation where Inventor 2018 is installed.
The MCP host/LLM is responsible for interpreting the returned drawing evidence.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import fitz
from mcp.server.fastmcp import FastMCP, Image

from inventor_bridge import InventorBridge, InventorBridgeError

mcp = FastMCP("Inventor 2018 CAD Bridge")
bridge = InventorBridge()


def _pdf_path(path: str) -> Path:
    p = Path(path).expanduser().resolve()
    if not p.is_file() or p.suffix.lower() != ".pdf":
        raise ValueError("PDF path is invalid or file does not exist.")
    return p


@mcp.tool()
def inspect_pdf(path: str) -> dict[str, Any]:
    """Read PDF metadata and extract selectable text page by page.

    Returns page count, dimensions and text. Scanned pages may have no text;
    use render_pdf_page so the vision-capable model can inspect the drawing.
    """
    p = _pdf_path(path)
    pages = []
    with fitz.open(p) as doc:
        for index, page in enumerate(doc):
            pages.append({
                "page": index + 1,
                "width_pt": round(page.rect.width, 2),
                "height_pt": round(page.rect.height, 2),
                "text": page.get_text("text")[:30000],
            })
        return {
            "file": str(p),
            "page_count": len(doc),
            "metadata": doc.metadata or {},
            "pages": pages,
        }


@mcp.tool()
def render_pdf_page(path: str, page_number: int, dpi: int = 180) -> Image:
    """Render one PDF page as an image for visual drawing analysis.

    page_number is 1-based. dpi is clamped to 90..300.
    """
    p = _pdf_path(path)
    dpi = max(90, min(int(dpi), 300))
    with fitz.open(p) as doc:
        if page_number < 1 or page_number > len(doc):
            raise ValueError(f"Page must be between 1 and {len(doc)}.")
        pix = doc[page_number - 1].get_pixmap(
            matrix=fitz.Matrix(dpi / 72, dpi / 72),
            alpha=False,
        )
        return Image(data=pix.tobytes("png"), format="png")


@mcp.tool()
def inventor_status() -> dict[str, Any]:
    """Connect to the running Inventor instance and report its active document."""
    try:
        return bridge.status()
    except InventorBridgeError as exc:
        return {"connected": False, "error": str(exc)}


@mcp.tool()
def inventor_list_parameters() -> dict[str, Any]:
    """Read user/model parameters from the active Inventor part document."""
    return bridge.list_parameters()


@mcp.tool()
def inventor_create_extruded_rectangle(
    length_mm: float,
    width_mm: float,
    thickness_mm: float,
    output_ipt: str,
) -> dict[str, Any]:
    """Create and save a dimensioned rectangular solid as a new IPT.

    This is the first geometry primitive used to validate the local MCP-to-COM
    path. It does not claim to reconstruct an arbitrary PDF drawing.
    """
    return bridge.create_extruded_rectangle(
        length_mm, width_mm, thickness_mm, output_ipt
    )


if __name__ == "__main__":
    # MCP stdio transport: stdout is reserved for protocol messages.
    mcp.run(transport="stdio")
