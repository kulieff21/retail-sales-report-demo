"""Build every client deliverable: figures, Excel workbook, summary slide, executed notebook.

Usage: uv run python tools/build_reports.py   (needs results/*.json and $RETAIL_DATA_DIR/ledger.parquet)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_figures  # noqa: E402
import build_notebook  # noqa: E402
import build_slide  # noqa: E402
import build_workbook  # noqa: E402


def main() -> None:
    build_figures.main()      # reports/figures/*.png
    build_workbook.build()    # reports/retail-sales-report.xlsx
    build_slide.main()        # reports/summary-slide.png + .pdf
    build_notebook.main()     # notebooks/report.ipynb (executed, outputs stored)


if __name__ == "__main__":
    main()
