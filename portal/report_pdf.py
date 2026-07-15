"""
BigMint-branded PDF report base — "CodeG" formatting, shared by every report/PDF
the portal generates.

A4 portrait. A solid-blue **cover** (white logo + title), **inner pages** (white,
blue page title, red full-width footer bar with the site + page number), and an
optional **back cover** (Contact Us). Multi-commodity reports call `start_section()`
once per commodity so each starts on its own page inside a single PDF.

Brand fonts (Archivo) and logos are loaded from the bundled ``assets/`` folder; if
they're missing the base **degrades gracefully** to the core Helvetica font and
skips the logos, so report generation never crashes on a stripped deployment.
"""
import os
from fpdf import FPDF

# --- Brand palette (CodeG) ----------------------------------------------------
BLUE      = (2, 76, 161)     # #024CA1  (portal/pptx blue)
BLUE_DARK = (2, 58, 122)     # #023A7A
RED       = (255, 64, 54)    # #FF4036  accent
BODY      = (26, 26, 26)     # #1A1A1A
GRAY      = (232, 232, 232)  # #E8E8E8
GRAY_SOFT = (244, 246, 250)
MUTED     = (100, 116, 139)
WHITE     = (255, 255, 255)

_ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
_FONTS  = os.path.join(_ASSETS, "fonts")
LOGO_LIGHT = os.path.join(_ASSETS, "bm_logo_light_bg.png")   # blue logo -> white pages
LOGO_DARK  = os.path.join(_ASSETS, "bm_logo_dark_bg.png")    # white logo -> blue pages

SITE = "www.bigmint.co"
CONTACT = [("Email", "info@bigmint.co"), ("Phone", "+91 97700 56666"), ("Web", "www.bigmint.co")]


def pdf_bytes(pdf):
    """PDF bytes regardless of fpdf (str) or fpdf2 (bytearray)."""
    raw = pdf.output(dest="S")
    return raw.encode("latin-1") if isinstance(raw, str) else bytes(raw)


class BrandedPDF(FPDF):
    def __init__(self, title="Report", subtitle="", meta=""):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.report_title = title
        self.report_subtitle = subtitle
        self.report_meta = meta          # small line under the header rule (e.g. product / date)
        self.page_title = title
        self._on_cover = False
        self._cover_pages = set()        # page numbers of cover/back-cover (plain number, no red bar)
        self.set_auto_page_break(True, margin=20)
        self.set_margins(14, 32, 14)
        self.brand_font = "Helvetica"
        self._load_fonts()

    # --- fonts (Archivo if bundled, else Helvetica) ---------------------------
    def _load_fonts(self):
        reg = os.path.join(_FONTS, "Archivo-Regular.ttf")
        bold = os.path.join(_FONTS, "Archivo-Bold.ttf")
        try:
            if os.path.exists(reg) and os.path.exists(bold):
                self.add_font("Archivo", "", reg)
                self.add_font("Archivo", "B", bold)
                self.brand_font = "Archivo"
        except Exception:
            self.brand_font = "Helvetica"

    def _f(self, style="", size=11, color=BODY):
        try:
            self.set_font(self.brand_font, style, size)
        except Exception:
            self.set_font("Helvetica", style, size)
        self.set_text_color(*color)

    def _clean(self, s):
        """Core Helvetica is latin-1 only — sanitise when Archivo isn't loaded."""
        s = str(s)
        if self.brand_font == "Helvetica":
            return s.encode("latin-1", "replace").decode("latin-1")
        return s

    # --- auto header / footer on every inner page -----------------------------
    def header(self):
        if self._on_cover:
            return
        if os.path.exists(LOGO_LIGHT):
            try:
                self.image(LOGO_LIGHT, self.w - 14 - 34, 11, 34)
            except Exception:
                pass
        self._f("B", 20, BLUE)
        self.set_xy(14, 13)
        self.cell(self.w - 60, 10, self._clean(self.page_title), 0, 1)
        if self.report_meta:
            self._f("", 9, MUTED)
            self.set_x(14)
            self.cell(0, 5, self._clean(self.report_meta), 0, 1)
        self.set_draw_color(*GRAY)
        self.set_line_width(0.4)
        self.line(14, 27, self.w - 14, 27)
        self.set_y(32)

    def footer(self):
        # Every page is numbered, cover = 1 (fpdf's page_no is 1-based).
        n = self.page_no()
        if n in self._cover_pages:
            # cover / back cover: plain white number in the blue band above the red strip
            self._f("B", 9, WHITE)
            self.set_xy(self.w - 28, self.h - 15)
            self.cell(14, 6, str(n), 0, 0, "R")
            return
        # inner page: red footer bar with the site (left) + page number (right)
        self.set_fill_color(*RED)
        self.rect(0, self.h - 12, self.w, 12, "F")
        self._f("B", 9, WHITE)
        self.set_xy(14, self.h - 10)
        self.cell(0, 7, SITE, 0, 0, "L")
        self.set_xy(self.w - 44, self.h - 10)
        self.cell(30, 7, f"pg. {n}", 0, 0, "R")

    # --- cover / back cover ---------------------------------------------------
    def cover(self):
        self._on_cover = True
        self.add_page()
        self._cover_pages.add(self.page_no())
        self.set_fill_color(*BLUE)
        self.rect(0, 0, self.w, self.h, "F")
        if os.path.exists(LOGO_DARK):
            try:
                self.image(LOGO_DARK, 18, 18, 52)
            except Exception:
                pass
        self._f("B", 34, WHITE)
        self.set_xy(18, self.h * 0.40)
        self.multi_cell(self.w - 36, 13, self._clean(self.report_title))
        if self.report_subtitle:
            self._f("", 14, GRAY)
            self.set_x(18)
            self.multi_cell(self.w - 36, 7, self._clean(self.report_subtitle))
        if self.report_meta:
            self._f("", 11, GRAY)
            self.set_x(18)
            self.multi_cell(self.w - 36, 6, self._clean(self.report_meta))
        # gray site band + red bottom strip
        self.set_fill_color(*GRAY)
        self.set_xy(0, self.h - 34)
        self._f("B", 11, BLUE)
        self.cell(self.w, 11, "   " + SITE, 0, 0, "L", True)
        self.set_fill_color(*RED)
        self.rect(0, self.h - 6, self.w, 6, "F")
        self._on_cover = False

    def back_cover(self):
        self._on_cover = True
        self.add_page()
        self._cover_pages.add(self.page_no())
        self.set_fill_color(*BLUE)
        self.rect(0, 0, self.w, self.h, "F")
        if os.path.exists(LOGO_DARK):
            try:
                self.image(LOGO_DARK, 18, 18, 52)
            except Exception:
                pass
        self._f("B", 28, WHITE)
        self.set_xy(18, self.h * 0.34)
        self.cell(0, 12, "Contact Us", 0, 1)
        self._f("", 13, GRAY)
        for _label, val in CONTACT:
            self.set_x(18)
            self.cell(0, 9, self._clean(val), 0, 1)
        self.set_fill_color(*RED)
        self.rect(0, self.h - 6, self.w, 6, "F")
        self._on_cover = False

    # --- content helpers ------------------------------------------------------
    def start_section(self, title, meta=None):
        """Begin a commodity/section on a fresh page. `title` shows in the header."""
        self.page_title = title
        if meta is not None:
            self.report_meta = meta
        self.add_page()

    def subheader(self, text):
        self._f("B", 12.5, RED)
        self.ln(2)
        self.cell(0, 7, self._clean(text), 0, 1)
        self.ln(1)

    def body(self, text):
        self._f("", 10.5, BODY)
        self.multi_cell(0, 5.6, self._clean(text))
        self.ln(1)

    def keyvals(self, pairs):
        """Compact 'Label: value   Label: value' info line."""
        self._f("", 10, BODY)
        line = "     ".join(f"{k}: {v}" for k, v in pairs)
        self.multi_cell(0, 6, self._clean(line))
        self.ln(1)

    def table(self, headers, rows, widths=None, aligns=None, bold_rows=None):
        """Branded table: blue header, zebra body, thin gray rules; `bold_rows` =
        indices (into rows) rendered bold with a light-blue fill (totals etc.)."""
        epw = self.w - self.l_margin - self.r_margin
        n = len(headers)
        widths = widths or [epw / n] * n
        aligns = aligns or (["L"] + ["R"] * (n - 1))
        bold_rows = set(bold_rows or [])
        # header
        self._f("B", 9, WHITE)
        self.set_fill_color(*BLUE)
        for w, h in zip(widths, headers):
            self.cell(w, 9, self._clean(h), 0, 0, "C", True)
        self.ln()
        # body
        self.set_draw_color(*GRAY)
        self.set_line_width(0.2)
        for ri, row in enumerate(rows):
            if ri in bold_rows:
                self._f("B", 8.8, BLUE_DARK)
                self.set_fill_color(224, 233, 246)
                fill = True
            else:
                self._f("", 8.6, BODY)
                self.set_fill_color(*(GRAY_SOFT if ri % 2 else WHITE))
                fill = True
            for w, val, a in zip(widths, row, aligns):
                self.cell(w, 7, self._clean(val), "B", 0, a, fill)
            self.ln()
        self.ln(2)
