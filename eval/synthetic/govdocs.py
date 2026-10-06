"""Synthetic government-document PDFs for testing the govdoc ingester.

Every name, number, place and event here is fictional. Nothing is based on a real case.

Three documents, each with its source paragraphs kept as ground truth:
- affidavit:     numbered paragraphs, hanging indent, blank line between paragraphs,
                 one paragraph runs across a page break, running header and page footer.
- police_report: unnumbered narrative, first-line indents with no blank line between
                 paragraphs, one sentence broken across a page break.
- scanned:       an affidavit page set rendered to images with no text layer except a
                 Bates stamp in the margin, so the ingester must fall back to OCR.

Built with reportlab (BSD) and pypdfium2 (Apache-2.0/BSD-3).

Usage: python -m eval.synthetic.govdocs [out_dir]   (default eval/fixtures/govdoc)
"""

from __future__ import annotations

import io
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path

import pypdfium2 as pdfium
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

PAGE_W, PAGE_H = 612.0, 792.0  # US Letter
LEFT, TOP, BOTTOM = 72.0, 90.0, 720.0
FONT, SIZE, LEADING = "Helvetica", 10.0, 13.0
WRAP = 92  # characters per line at 10pt Helvetica inside the margins
PARA_GAP = 8.0

HEADER = "SYNTHETIC TEST DOCUMENT - Case No. 26-CR-0417-SYN - NOT A REAL CASE"


@dataclass(frozen=True)
class Para:
    text: str
    number: int | None = None  # printed paragraph number, if the document numbers them
    heading: bool = False


AFFIDAVIT_TITLE = "AFFIDAVIT IN SUPPORT OF AN APPLICATION FOR A SEARCH WARRANT"

AFFIDAVIT: tuple[Para, ...] = (
    Para(AFFIDAVIT_TITLE, heading=True),
    Para("UNITED STATES DISTRICT COURT FOR THE DISTRICT OF NORTH RIVERTON", heading=True),
    Para(
        "I, Dana Whitlock, a Special Agent with the Riverton Field Office, being duly sworn, "
        "state as follows:"
    ),
    Para(
        "I have been a Special Agent since 2017. I have received training in the examination "
        "of mobile devices and in the review of extraction reports produced by forensic tools.",
        1,
    ),
    Para(
        "This affidavit is submitted in support of an application to search a Samsung "
        "Galaxy phone recovered from MARK TELLER on March 4, 2026 (Device 1) and an Apple "
        "iPhone recovered from IRINA VOSS on the same date (Device 2).",
        2,
    ),
    Para(
        "A forensic extraction of Device 1 was performed on March 6, 2026. The extraction "
        "report lists a WhatsApp account with the handle @northstar. Based on my review, "
        "the account @northstar was used by MARK TELLER.",
        3,
    ),
    Para(
        "On March 5, 2026 at approximately 2:31 a.m., the user of @northstar sent a message "
        "to the user of Device 2 stating that the tickets were ready and that the meeting "
        "would take place at the parking structure on Delmar Avenue.",
        4,
    ),
    Para(
        "I believe the word tickets in this message is a code word for a quantity of "
        "controlled substances. In my training and experience, persons engaged in "
        "distribution commonly use event-related words such as tickets, seats or passes to "
        "refer to narcotics in order to avoid detection by law enforcement.",
        5,
    ),
    Para(
        "Device 1 and Device 2 exchanged 214 messages between February 1, 2026 and March 4, "
        "2026. No messages between the two devices were found after March 4, 2026.",
        6,
    ),
    Para(
        "On March 7, 2026, a second extraction was attempted on Device 2. The examiner "
        "reported that the attempt produced a logical extraction only, and that a file "
        "system extraction could not be completed because the device was locked. The "
        "examiner further reported that the WhatsApp database on Device 2 contained no "
        "entries for the period from February 20, 2026 through February 23, 2026, and I "
        "believe the absence of entries for that period indicates that the user of Device 2 "
        "removed messages during that period in an effort to conceal the conversation. "
        "The examiner did not report any error during the logical extraction, and the "
        "extraction report for Device 2 is consistent with the report for Device 1 in all "
        "other respects that I reviewed for the purposes of this affidavit.",
        7,
    ),
    Para(
        "MARK TELLER chose the parking structure on Delmar Avenue as the meeting place and "
        "directed IRINA VOSS to bring the tickets there.",
        8,
    ),
    Para(
        "A contact saved on Device 2 under the name Alex is associated with the telephone "
        "number (555) 010-4471. I believe this contact is MARK TELLER.",
        9,
    ),
    Para(
        "Based on the foregoing, I submit that there is probable cause to believe that the "
        "devices contain evidence of the offenses described above.",
        10,
    ),
    Para("Sworn to before me this 9th day of March, 2026."),
)

POLICE_TITLE = "RIVERTON POLICE DEPARTMENT - INCIDENT REPORT"

POLICE_REPORT: tuple[Para, ...] = (
    Para(POLICE_TITLE, heading=True),
    Para("Report No. RPD-26-00877-SYN. Reporting officer: Officer Sam Okafor, Badge 4410."),
    Para("NARRATIVE", heading=True),
    Para(
        "On March 4, 2026 at about 21:40 hours I responded to the parking structure on Delmar "
        "Avenue after a call about two people sitting in a parked vehicle with the engine "
        "running. On arrival I observed a grey sedan on level three with two occupants."
    ),
    Para(
        "I identified the driver as MARK TELLER by his state identification card. The "
        "passenger identified herself as IRINA VOSS. Both occupants were cooperative and "
        "stated that they were waiting for a friend."
    ),
    Para(
        "I observed a black Samsung phone in the center console and an Apple iPhone on the "
        "passenger seat. Both phones were collected and placed into evidence under item "
        "numbers 1 and 2. Neither phone was examined at the scene."
    ),
    Para(
        "Officer Lena Park arrived at 21:52 hours to assist. Officer Park searched the "
        "vehicle with the consent of the driver. No contraband was located in the vehicle. "
        "Officer Park noted an envelope in the glove box containing two printed concert "
        "tickets for an event at the Riverton Arena on March 6, 2026."
    ),
    Para(
        "TELLER stated that the tickets were a gift for VOSS and that he had arranged to meet "
        "her at the structure because it was close to her apartment. VOSS stated that she "
        "had suggested the structure as the meeting place."
    ),
    Para(
        "Both occupants were released at the scene at 22:30 hours. The phones were "
        "transported to the station and logged into property by me at 23:05 hours."
    ),
    Para("No further action was taken at the scene."),
)

SCANNED_TITLE = "AFFIDAVIT OF SPECIAL AGENT DANA WHITLOCK"

SCANNED: tuple[Para, ...] = (
    Para(SCANNED_TITLE, heading=True),
    Para("I, Dana Whitlock, being duly sworn, state as follows:"),
    Para(
        "I reviewed the extraction report for Device 1. The report lists 214 messages "
        "exchanged with Device 2 between February 1, 2026 and March 4, 2026.",
        1,
    ),
    Para(
        "On March 5, 2026 the account @northstar sent a message stating that the tickets "
        "were ready.",
        2,
    ),
    Para("The account @northstar was registered to the telephone number (555) 010-4471.", 3),
    Para("No messages between the devices were found after March 4, 2026.", 4),
    Para("I believe the user of Device 2 removed messages from the WhatsApp database.", 5),
)


def _lines(p: Para) -> list[tuple[float, str]]:
    """(x, text) for each printed line of a paragraph."""
    if p.number is not None:
        label = f"{p.number}."
        wrapped = textwrap.wrap(p.text, WRAP - 6)
        return [(LEFT, f"{label}  {wrapped[0]}")] + [(LEFT + 24, w) for w in wrapped[1:]]
    return [(LEFT, w) for w in textwrap.wrap(p.text, WRAP)]


def _indented_lines(p: Para) -> list[tuple[float, str]]:
    """First-line indent, no number (police narrative style)."""
    if p.heading:
        return [(LEFT, p.text)]
    wrapped = textwrap.wrap(p.text, WRAP, initial_indent="      ")
    return [(LEFT + 24, wrapped[0].lstrip())] + [(LEFT, w) for w in wrapped[1:]]


def _furniture(c: canvas.Canvas, n: int, total: int) -> None:
    c.setFont(FONT, 8)
    c.drawString(LEFT, PAGE_H - 48, HEADER)
    c.drawString(PAGE_W / 2 - 24, PAGE_H - 760, f"Page {n} of {total}")


def _canvas(target, title: str, producer: str) -> canvas.Canvas:
    c = canvas.Canvas(target, pagesize=(PAGE_W, PAGE_H), invariant=1, pageCompression=1)
    c.setTitle(title)
    c.setProducer(producer)
    c.setCreator(producer)
    return c


def _draw_lines(c: canvas.Canvas, lines: list[tuple[float, float, str]]) -> None:
    c.setFont(FONT, SIZE)
    for x, y, text in lines:
        c.drawString(x, PAGE_H - y, text)


def _layout(
    paras: tuple[Para, ...],
    *,
    indent_style: bool,
    page_break_before: int | None = None,
    split_para: int | None = None,
    split_after_lines: int = 3,
) -> list[list[tuple[float, float, str]]]:
    """Place lines on pages. Returns, per page, (x, baseline_y, text).

    page_break_before: index of a paragraph forced to start a new page.
    split_para: index of a paragraph forced to run across a page break after
    split_after_lines of its lines.
    """
    pages: list[list[tuple[float, float, str]]] = [[]]
    y = TOP
    for i, p in enumerate(paras):
        lines = _indented_lines(p) if indent_style else _lines(p)
        if i == page_break_before and pages[-1]:
            pages.append([])
            y = TOP
        for j, (x, text) in enumerate(lines):
            if y > BOTTOM or (i == split_para and j == split_after_lines):
                pages.append([])
                y = TOP
            pages[-1].append((x, y, text))
            y += LEADING
        if not indent_style or p.heading:
            y += PARA_GAP
    return pages


def _write(pages: list[list[tuple[float, float, str]]], path: Path, title: str) -> None:
    c = _canvas(str(path), title, "baker synthetic")
    for n, lines in enumerate(pages, start=1):
        _furniture(c, n, len(pages))
        _draw_lines(c, lines)
        c.showPage()
    c.save()


def make_affidavit(path: Path) -> Path:
    # Paragraph 7 (index 9) runs across the break between page 1 and page 2.
    pages = _layout(AFFIDAVIT, indent_style=False, split_para=9, split_after_lines=4)
    _write(pages, path, AFFIDAVIT_TITLE)
    return path


def make_police_report(path: Path) -> Path:
    # The paragraph at index 6 breaks mid-sentence across pages 1 and 2.
    pages = _layout(POLICE_REPORT, indent_style=True, split_para=6, split_after_lines=2)
    _write(pages, path, "")  # no metadata title: the ingester must read it from the page
    return path


def make_scanned(path: Path, dpi: int = 200) -> Path:
    """Render a two-page affidavit to images, then build a PDF that has only those images
    plus a per-page Bates stamp as its text layer, like a scanned production."""
    pages = _layout(SCANNED, indent_style=False, page_break_before=5)
    buf = io.BytesIO()
    src = _canvas(buf, "", "baker synthetic")
    for lines in pages:
        _draw_lines(src, lines)
        src.showPage()
    src.save()

    out = _canvas(str(path), "", "baker synthetic scan")
    pdf = pdfium.PdfDocument(buf.getvalue())
    for n in range(1, len(pdf) + 1):
        image = pdf[n - 1].render(scale=dpi / 72, grayscale=True).to_pil()
        out.drawImage(ImageReader(image), 0, 0, PAGE_W, PAGE_H)
        out.setFont(FONT, 8)
        out.drawString(PAGE_W - 160, PAGE_H - 772, f"BKR-SYN-{n:06d}")
        out.showPage()
    pdf.close()
    out.save()
    return path


FIXTURES = {
    "affidavit.pdf": make_affidavit,
    "police_report.pdf": make_police_report,
    "scanned_affidavit.pdf": make_scanned,
}


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    out = Path(args[0]) if args else Path("eval/fixtures/govdoc")
    out.mkdir(parents=True, exist_ok=True)
    for name, make in FIXTURES.items():
        print(make(out / name))
    return 0


if __name__ == "__main__":
    sys.exit(main())
