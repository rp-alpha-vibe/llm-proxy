"""Export the finalized deck's 2x PNG renders to a PDF for viewing.

Usage: python submission/export_presentation_pdf.py BUILD_DIR OUTPUT.pdf
PPTX remains the editable source. PDF pages use the same rendering as the
visually reviewed deck. No slide content is reflowed during PDF export.
"""

import json
import sys
from pathlib import Path

from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


def main() -> None:
    build_dir = Path(sys.argv[1]).resolve()
    destination = Path(sys.argv[2]).resolve()
    slides = json.loads((build_dir / "slide-text.json").read_text(encoding="utf-8"))
    images = [build_dir / "rendered" / f"slide-{i + 1}.png" for i in range(len(slides))]
    if not slides or not all(image.is_file() for image in images):
        raise ValueError("Complete rendered slides are required")
    if destination.exists():
        raise FileExistsError("Use a new output path for each PDF revision")
    destination.parent.mkdir(parents=True, exist_ok=True)
    document = canvas.Canvas(str(destination), pagesize=(960, 540), pageCompression=1)
    document.setTitle(slides[0][2].replace("\n", " "))
    document.setAuthor("Команда Красный Kod")
    for number, (image, texts) in enumerate(zip(images, slides, strict=True), start=1):
        document.drawImage(ImageReader(str(image)), 0, 0, width=960, height=540)
        document.bookmarkPage(f"slide-{number}")
        document.addOutlineEntry(texts[2].replace("\n", " "), f"slide-{number}")
        if number == len(slides):
            document.linkURL(
                "https://llm-proxy-production-84c7.up.railway.app/docs",
                (48, 63.75, 408, 98.25),
                relative=0,
                thickness=0,
            )
            document.linkURL(
                "https://github.com/rp-alpha-vibe/llm-proxy",
                (528, 63.75, 912, 98.25),
                relative=0,
                thickness=0,
            )
        document.showPage()
    document.save()
    print(f"PDF pages: {len(slides)}; output: {destination}")


if __name__ == "__main__":
    main()
