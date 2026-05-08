"""DISABLED 2026-05-08 — Gemini-era batch ingester, retired.

This script previously read chain_pdf_sources.json and called the Gemini PDF
extraction pipeline. The deterministic pipeline replaces it:

    Cached PDFs (preferred):
        python3 tools/reingest_cached_pdfs.py --stage-only
        python3 tools/reingest_cached_pdfs.py --commit \\
            --chain-market subway::IN

    One-off PDF (local file or URL):
        python3 tools/ingest_chain_from_pdf.py \\
            --chain mcdonalds --market US \\
            --pdf-url https://example.com/nutrition.pdf

    Live URL crawl (HTML / JSON / linked PDFs):
        python3 tools/ingest_chain_from_url.py \\
            --chain pizza_hut --market TH \\
            --url https://www.pizzahut.co.th/menu

Running this entry point now exits 1 with a pointer message — no Gemini call.
The original Gemini-era logic is in git history at commit 32582208^ if ever
needed.
"""

from __future__ import annotations

import sys

_DISABLED_MESSAGE = (
    "tools/batch_pdf_ingest.py is DISABLED — Gemini-era ingester is retired.\n\n"
    "Use one of these instead:\n"
    "  - Re-process cached PDFs deterministically:\n"
    "      python3 tools/reingest_cached_pdfs.py --stage-only\n"
    "  - One-off PDF (local file or URL):\n"
    "      python3 tools/ingest_chain_from_pdf.py --chain X --market Y \\\n"
    "          --pdf-url https://...\n"
    "  - Live URL crawl (HTML / JSON / linked PDFs):\n"
    "      python3 tools/ingest_chain_from_url.py --chain X --market Y \\\n"
    "          --url https://...\n"
)


def main() -> int:
    print(_DISABLED_MESSAGE, file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
