"""
PDF report generator – RentalShield v3
A4 · Professional car inspection format · Evidence-first design
"""
from __future__ import annotations

import functools
import tempfile
from datetime import datetime
from pathlib import Path

import PIL.Image
from PIL import Image, ImageDraw, ImageFont

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
    Image as RLImage,
    HRFlowable,
)
from reportlab.pdfgen import canvas as rl_canvas
from loguru import logger

from rentalshield.models import Damage, ComparisonItem, ComparisonStatus, RentalMetadata


# ─── Page geometry ────────────────────────────────────────────────────────────
PAGE_W, PAGE_H = A4           # 595.28 × 841.89 pts
MARGIN   = 42
BODY_W   = PAGE_W - 2 * MARGIN  # ≈ 511 pts
BOT_M    = 48

# ─── Palette ──────────────────────────────────────────────────────────────────
C_NAVY  = colors.HexColor("#162447")
C_RED   = colors.HexColor("#E63946")
C_WHITE = colors.white
C_BGLT  = colors.HexColor("#F5F7FA")
C_LINE  = colors.HexColor("#D8DCE6")
C_MID   = colors.HexColor("#6B7280")
C_DARK  = colors.HexColor("#111827")
C_GREEN = colors.HexColor("#15803D")

SEV_COL = {
    "SEVERE":   colors.HexColor("#DC2626"),
    "MODERATE": colors.HexColor("#EA580C"),
    "MINOR":    colors.HexColor("#D97706"),
    "UNKNOWN":  colors.HexColor("#6B7280"),
}
SEV_LIGHT = {
    "SEVERE":   colors.HexColor("#FEF2F2"),
    "MODERATE": colors.HexColor("#FFF7ED"),
    "MINOR":    colors.HexColor("#FFFBEB"),
    "UNKNOWN":  colors.HexColor("#F9FAFB"),
}

# ─── Company brand colours ────────────────────────────────────────────────────
# Background RGB for the generated logo badge. Covers the major rental brands.
_COMPANY_COLORS: dict[str, tuple[int, int, int]] = {
    "noleggiare":  (232,  17, 134),  # Noleggiare hot pink (brand colour)
    "hertz":       (200, 155,   0),  # Hertz gold/dark-yellow (readable on dark bg)
    "sixt":        (230,  90,   0),  # Sixt orange
    "europcar":    (  0, 132,  61),  # Europcar green
    "avis":        (190,   0,   0),  # Avis red
    "budget":      (  0,  71, 135),  # Budget blue
    "enterprise":  (  0, 104,  71),  # Enterprise green
    "national":    (200,  20,  50),  # National red
    "alamo":       (  0, 132,  61),  # Alamo green
    "dollar":      ( 80, 130,  60),  # Dollar green
    "thrifty":     (  0,  71, 135),  # Thrifty blue
    "goldcar":     (180, 140,   0),  # Goldcar gold
    "maggiore":    (  0,  47, 108),  # Maggiore dark blue
    "leasys":      ( 20,  80, 180),  # Leasys blue
    "ok mobility": ( 30,  30,  30),  # OK Mobility near-black
    "interrent":   ( 20, 100,  50),  # InterRent green
    "record":      (170,  20,  30),  # Record red
    "localiza":    (255, 180,   0),  # Localiza yellow → dark text
    "firefly":     (  0,  80, 160),  # Firefly blue
}

# ─── Company domain lookup ────────────────────────────────────────────────────
_COMPANY_DOMAINS: dict[str, str] = {
    "noleggiare":  "noleggiare.it",
    "hertz":       "hertz.com",
    "sixt":        "sixt.com",
    "europcar":    "europcar.com",
    "avis":        "avis.com",
    "budget":      "budget.com",
    "enterprise":  "enterprise.com",
    "national":    "nationalcar.com",
    "alamo":       "alamo.com",
    "dollar":      "dollar.com",
    "thrifty":     "thrifty.com",
    "goldcar":     "goldcar.es",
    "ok mobility": "okmobility.com",
    "localiza":    "localiza.com",
    "firefly":     "fireflycarrental.com",
    "interrent":   "interrent.com",
    "record":      "recordrentacar.com",
    "maggiore":    "maggiore.it",
    "leasys":      "leasysrent.com",
}


# ─── Utilities ────────────────────────────────────────────────────────────────

def _smart_title(s: str | None) -> str | None:
    if not s:
        return s
    return " ".join(w.capitalize() if w.islower() else w for w in s.strip().split())


def _fit(path: Path, max_w: float, max_h: float) -> tuple[float, float]:
    try:
        with PIL.Image.open(str(path)) as img:
            iw, ih = img.size
        scale = min(max_w / iw, max_h / ih, 1.0)
        return iw * scale, ih * scale
    except Exception:
        return max_w, max_h * 0.6


def _exif_corrected(path: Path) -> Path:
    """
    Return a path to an EXIF-rotation-corrected copy of the image.
    Phone photos are often stored sideways — the EXIF orientation tag says
    'rotate 90°' but ReportLab ignores it. PIL's exif_transpose() fixes that.
    Returns the original path if correction fails or is not needed.
    """
    try:
        import PIL.ImageOps as _ImageOps
        img = PIL.Image.open(str(path))
        corrected = _ImageOps.exif_transpose(img)
        if corrected.size == img.size and list(corrected.getdata()) == list(img.getdata()):
            return path   # no change needed
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
        corrected.convert("RGB").save(tmp.name, "JPEG", quality=92)
        tmp.close()
        return Path(tmp.name)
    except Exception:
        return path


def _rl_img(path: Path | None, max_w: float, max_h: float,
            exif_correct: bool = False) -> RLImage | None:
    if not path or not Path(path).exists():
        return None
    p = _exif_corrected(Path(path)) if exif_correct else Path(path)
    w, h = _fit(p, max_w, max_h)
    return RLImage(str(p), width=w, height=h)


def _img_cell(img_path: Path | None, w=72, h=54):
    img = _rl_img(img_path, w, h)
    return img if img else Spacer(1, 0)


# ─── Badge / logo ─────────────────────────────────────────────────────────────

# Companies whose brand uses all-lowercase (affects badge initial)
_COMPANY_LOWERCASE = {"noleggiare", "ok mobility", "localiza", "firefly", "interrent"}


def _make_badge(company: str, size: int = 120) -> Path:
    key = company.lower().strip()
    # Use lowercase initial for brands with lowercase identity (e.g. "noleggiare")
    if key in _COMPANY_LOWERCASE:
        initials = company.strip()[0].lower()
    else:
        initials = "".join(
            w[0].upper() for w in company.strip().split()
            if w and w[0].isalpha()
        )[:2] or company[:1].upper()

    # Brand colour: use known map, fall back to navy for unknown companies
    bg_rgb = _COMPANY_COLORS.get(key, (22, 36, 71))
    # Choose white or dark text based on perceived luminance (WCAG formula)
    lum = 0.299 * bg_rgb[0] + 0.587 * bg_rgb[1] + 0.114 * bg_rgb[2]
    text_color = "white" if lum < 160 else "#111827"

    img  = Image.new("RGB", (size, size), color=bg_rgb)
    draw = ImageDraw.Draw(img)
    # Slightly larger font for single-character initials
    font_size = int(size * (0.52 if len(initials) == 1 else 0.38))
    font = None
    for fp in [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Italic.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]:
        if Path(fp).exists():
            try:
                font = ImageFont.truetype(fp, font_size); break
            except Exception:
                pass
    if font is None:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), initials, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((size-tw)//2 - bbox[0], (size-th)//2 - bbox[1]),
              initials, fill=text_color, font=font)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size-1, size-1],
                                           radius=size//5, fill=255)
    result = Image.new("RGB", (size, size), (255, 255, 255))
    result.paste(img, mask=mask)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
    result.save(tmp.name, "PNG"); tmp.close()
    return Path(tmp.name)


def _get_logo(company: str | None) -> Path | None:
    """Server has no internet; always use generated badge."""
    if not company:
        return None
    return _make_badge(company)


# ─── Page-number canvas ───────────────────────────────────────────────────────

class _NC(rl_canvas.Canvas):
    def __init__(self, *args, session_id="", report_date="", **kwargs):
        super().__init__(*args, **kwargs)
        self._pages: list[dict] = []
        self._sid  = session_id
        self._date = report_date

    def showPage(self):
        self._pages.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._pages)
        for i, state in enumerate(self._pages, 1):
            self.__dict__.update(state)
            self._footer(i, total)
            rl_canvas.Canvas.showPage(self)
        rl_canvas.Canvas.save(self)

    def _footer(self, n: int, total: int):
        if n == 1:
            # Cover page: just a thin bottom line + report ID
            self.saveState()
            self.setStrokeColor(C_LINE)
            self.setLineWidth(0.5)
            self.line(MARGIN, BOT_M - 4, PAGE_W - MARGIN, BOT_M - 4)
            self.setFont("Helvetica", 7)
            self.setFillColor(C_MID)
            self.drawString(MARGIN, BOT_M - 18,
                            f"Report ID: {self._sid}   ·   {self._date}")
            self.drawRightString(PAGE_W - MARGIN, BOT_M - 18, "RentalShield")
            self.restoreState()
            return
        self.saveState()
        self.setStrokeColor(C_LINE)
        self.setLineWidth(0.5)
        self.line(MARGIN, BOT_M - 4, PAGE_W - MARGIN, BOT_M - 4)
        self.setFont("Helvetica", 7)
        self.setFillColor(C_MID)
        self.drawString(MARGIN, BOT_M - 18,
                        f"RentalShield  ·  Vehicle Damage Audit  ·  {self._sid}")
        self.drawRightString(PAGE_W - MARGIN, BOT_M - 18, f"Page {n} / {total}")
        self.restoreState()


# ─── Paragraph styles ─────────────────────────────────────────────────────────

def _S():
    base = getSampleStyleSheet()

    def mk(name, **kw):
        return ParagraphStyle(name, parent=base["Normal"], **kw)

    return {
        "b":     base,
        # Cover
        "brand": mk("brand",  fontSize=10, fontName="Helvetica-Bold",
                    textColor=colors.HexColor("#A8BCDC")),
        "h1":    mk("h1",     fontSize=15, fontName="Helvetica-Bold",
                    textColor=C_WHITE, alignment=2),
        "cv_lbl":mk("cv_lbl", fontSize=7,  textColor=C_MID, spaceAfter=2),
        "cv_val":mk("cv_val", fontSize=11, fontName="Helvetica-Bold",
                    textColor=C_DARK),
        "disc":  mk("disc",   fontSize=7,  textColor=C_MID, leading=10,
                    alignment=1),
        # Tables
        "th":    mk("th",     fontSize=8,  fontName="Helvetica-Bold",
                    textColor=C_WHITE, alignment=1),
        "tc":    mk("tc",     fontSize=8,  leading=11, textColor=C_DARK),
        # Evidence pages
        "ev_num":mk("ev_num", fontSize=22, fontName="Helvetica-Bold",
                    textColor=C_WHITE),
        "ev_typ":mk("ev_typ", fontSize=12, fontName="Helvetica-Bold",
                    textColor=C_WHITE, alignment=2),
        "ev_loc":mk("ev_loc", fontSize=9,  fontName="Helvetica-Bold",
                    textColor=C_NAVY),
        "ev_desc":mk("ev_desc",fontSize=9, textColor=C_DARK, leading=14),
        "ev_cap":mk("ev_cap", fontSize=7,  textColor=C_MID, alignment=1),
        "ev_meta":mk("ev_meta",fontSize=8, textColor=C_MID),
        "sect":  mk("sect",   fontSize=12, fontName="Helvetica-Bold",
                    textColor=C_NAVY, spaceBefore=8, spaceAfter=6),
        "ok":    mk("ok",     fontSize=11, fontName="Helvetica-Bold",
                    textColor=C_GREEN),
    }


# ─── Cover page ───────────────────────────────────────────────────────────────

def _cover(
    story, S, damages, meta, session_id,
    video_name, gen_at, logo_path, car_img_path,
    company, car_model,
):
    m = meta or RentalMetadata()
    n = len(damages)

    # ── 1. Header band ──────────────────────────────────────────────────────
    hdr = Table(
        [[Paragraph("🛡 RentalShield", S["brand"]),
          Paragraph("Vehicle Damage Audit Report", S["h1"])]],
        colWidths=[BODY_W * 0.38, BODY_W * 0.62],
    )
    hdr.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), C_NAVY),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 18),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 18),
        ("LEFTPADDING",   (0, 0), (0, 0),   14),
        ("RIGHTPADDING",  (-1, 0),(-1, -1), 14),
    ]))
    story.append(hdr)
    story.append(Spacer(1, 16))

    # ── 2. Vehicle identification grid ──────────────────────────────────────
    def info_cell(label, value):
        return [Paragraph(label.upper(), S["cv_lbl"]),
                Paragraph(value or "—", S["cv_val"])]

    gps      = (f"{m.gps_lat:.5f}, {m.gps_lon:.5f}" if m.gps_lat is not None else None)
    plate_lbl = ("Plate (auto-read)"
                 if getattr(m, "car_plate_source", None) == "auto" else "Licence Plate")
    contract  = " / ".join(filter(None, [m.contract_number, session_id]))

    id_tbl = Table(
        [[info_cell("Rental Company",    company),
          info_cell(plate_lbl,           m.car_plate),
          info_cell("Vehicle",           car_model)],
         [info_cell("Pickup Location",   m.location),
          info_cell("Inspection Date",   gen_at.strftime("%d %B %Y,  %H:%M")),
          info_cell("Contract / Session",contract or session_id or "—")]],
        colWidths=[BODY_W * 0.36, BODY_W * 0.32, BODY_W * 0.32],
    )
    id_tbl.setStyle(TableStyle([
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING",    (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING",   (0, 0), (-1, -1), 10),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
        ("LINEBELOW",     (0, 0), (-1, 0),  0.4, C_LINE),
        ("BOX",           (0, 0), (-1, -1), 0.5, C_LINE),
        ("INNERGRID",     (0, 0), (-1, -1), 0.3, C_LINE),
        ("BACKGROUND",    (0, 0), (-1, 0),  C_BGLT),
        ("BACKGROUND",    (0, 1), (-1, 1),  colors.white),
    ]))
    story.append(id_tbl)
    story.append(Spacer(1, 18))

    # ── 3. Car reference image (big, full width) ─────────────────────────────
    if car_img_path and Path(car_img_path).exists():
        # Apply EXIF rotation — phone photos are often stored sideways
        _car_img_corrected = _exif_corrected(Path(car_img_path))
        cw, ch = _fit(_car_img_corrected, BODY_W, 280)
        car_tbl = Table(
            [[RLImage(str(_car_img_corrected), width=cw, height=ch)]],
            colWidths=[BODY_W],
        )
        car_tbl.setStyle(TableStyle([
            ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
            ("BACKGROUND",    (0, 0), (-1, -1), C_BGLT),
            ("BOX",           (0, 0), (-1, -1), 0.5, C_LINE),
            ("TOPPADDING",    (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ]))
        story.append(car_tbl)
        story.append(Spacer(1, 18))

    # ── 4. Damage count  +  company logo ────────────────────────────────────
    dmg_bg  = C_RED if n > 0 else C_GREEN
    count_s = ParagraphStyle("cnt", parent=S["b"]["Normal"],
                              fontSize=68, fontName="Helvetica-Bold",
                              textColor=C_WHITE, alignment=1, leading=72)
    dlbl_s  = ParagraphStyle("dlbl", parent=S["b"]["Normal"],
                              fontSize=11, fontName="Helvetica-Bold",
                              textColor=C_WHITE, alignment=1)

    count_tbl = Table(
        [[Paragraph(str(n), count_s)],
         [Paragraph("DAMAGE" + ("S" if n != 1 else ""), dlbl_s)],
         [Paragraph("DETECTED", dlbl_s)]],
        colWidths=[150],
    )
    count_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), dmg_bg),
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING",    (0, 0), (-1, -1), 20),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 20),
    ]))

    # Logo / company name block (right side)
    logo_block: list = []
    if logo_path and Path(logo_path).exists():
        lw, lh = _fit(Path(logo_path), 100, 80)
        logo_block.append(RLImage(str(logo_path), width=lw, height=lh))
    if company:
        co_s   = ParagraphStyle("co",  parent=S["b"]["Normal"],
                                fontSize=13, fontName="Helvetica-Bold",
                                textColor=C_NAVY, alignment=2)
        co_l_s = ParagraphStyle("col", parent=S["b"]["Normal"],
                                fontSize=8, textColor=C_MID, alignment=2)
        logo_block += [Paragraph(company,        co_s),
                       Paragraph("Rental company", co_l_s)]
    if not logo_block:
        logo_block = [Spacer(1, 0)]

    row4 = Table(
        [[count_tbl, logo_block]],
        colWidths=[160, BODY_W - 160],
    )
    row4.setStyle(TableStyle([
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN",         (1, 0), (1, -1),  "RIGHT"),
        ("LEFTPADDING",   (0, 0), (-1, -1), 0),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
        ("TOPPADDING",    (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(row4)

    # ── 5. Disclaimer ────────────────────────────────────────────────────────
    story.append(Spacer(1, 20))
    story.append(HRFlowable(width=BODY_W, thickness=0.5, color=C_LINE))
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        "This report was produced automatically by the RentalShield AI vision system "
        "using dual-pass analysis and zone-level inspection. Each finding is backed by "
        "photographic evidence shown on subsequent pages. "
        "Intended as legal documentation for rental damage disputes.",
        S["disc"],
    ))
    story.append(PageBreak())


# ─── Summary table ────────────────────────────────────────────────────────────

def _summary(story, S, damages):
    story.append(Paragraph("Damage Summary", S["sect"]))
    story.append(HRFlowable(width=BODY_W, thickness=1.5, color=C_NAVY,
                             spaceAfter=10))

    if not damages:
        story.append(Paragraph("✅  No physical damage detected.", S["ok"]))
        return

    hdr  = [Paragraph(h, S["th"]) for h in
            ["#", "Source", "Location", "Type", "Severity", "Description", "Photo"]]
    rows = [hdr]
    cw   = [22, 48, 110, 54, 58, 143, 76]  # sum = 511 = BODY_W

    for i, d in enumerate(damages, 1):
        src = (f"Photo {d.frame}" if d.time_sec is None and d.frame
               else f"{d.time_sec:.1f}s" if d.time_sec is not None else "—")
        bg, fg = SEV_COL.get(d.severity.value, C_MID), colors.white
        sev_s  = ParagraphStyle("sv", parent=S["b"]["Normal"],
                                fontSize=7, fontName="Helvetica-Bold",
                                textColor=fg, alignment=1)
        sev_tbl = Table([[Paragraph(d.severity.value, sev_s)]], colWidths=[50])
        sev_tbl.setStyle(TableStyle([
            ("BACKGROUND",    (0,0),(-1,-1), bg),
            ("TOPPADDING",    (0,0),(-1,-1), 3),
            ("BOTTOMPADDING", (0,0),(-1,-1), 3),
            ("LEFTPADDING",   (0,0),(-1,-1), 3),
            ("RIGHTPADDING",  (0,0),(-1,-1), 3),
        ]))
        typ_s = ParagraphStyle("tp", parent=S["b"]["Normal"],
                               fontSize=8, fontName="Helvetica-Bold",
                               textColor=C_NAVY, alignment=1)
        num_s = ParagraphStyle("ns", parent=S["b"]["Normal"],
                               fontSize=9, fontName="Helvetica-Bold",
                               textColor=C_NAVY, alignment=1)
        rows.append([
            Paragraph(str(i), num_s),
            Paragraph(src,            S["tc"]),
            Paragraph(d.location,     S["tc"]),
            Paragraph(d.type.value,   typ_s),
            sev_tbl,
            Paragraph(d.description,  S["tc"]),
            _img_cell(d.img_path, w=72, h=54),
        ])

    t = Table(rows, colWidths=cw, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND",     (0,0),(-1, 0), C_NAVY),
        ("FONTSIZE",       (0,0),(-1,-1), 8),
        ("ALIGN",          (0,0),(-1,-1), "CENTER"),
        ("VALIGN",         (0,0),(-1,-1), "MIDDLE"),
        ("GRID",           (0,0),(-1,-1), 0.3, C_LINE),
        ("ROWBACKGROUNDS", (0,1),(-1,-1), [colors.white, C_BGLT]),
        ("TOPPADDING",     (0,0),(-1,-1), 5),
        ("BOTTOMPADDING",  (0,0),(-1,-1), 5),
        ("LEFTPADDING",    (0,0),(-1,-1), 4),
        ("RIGHTPADDING",   (0,0),(-1,-1), 4),
    ]))
    story.append(t)
    story.append(Spacer(1, 10))
    note = ParagraphStyle("n", parent=S["b"]["Normal"],
                          fontSize=7.5, textColor=C_MID, leading=11)
    story.append(Paragraph(
        "Full photographic evidence — full-frame context and close-up — follows on subsequent pages.",
        note,
    ))
    story.append(PageBreak())


# ─── Evidence page ────────────────────────────────────────────────────────────

def _evidence(story, S, i: int, d: Damage):
    sev     = d.severity.value
    sev_bg  = SEV_COL.get(sev, C_MID)
    sev_lt  = SEV_LIGHT.get(sev, C_BGLT)

    # ── Header ───────────────────────────────────────────────────────────────
    sev_pill_s = ParagraphStyle("sp", parent=S["b"]["Normal"],
                                fontSize=9, fontName="Helvetica-Bold",
                                textColor=sev_bg, alignment=2)
    sev_pill = Table([[Paragraph(sev, sev_pill_s)]],
                     colWidths=[70])
    sev_pill.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), colors.white),
        ("BOX",           (0,0),(-1,-1), 1.5, sev_bg),
        ("TOPPADDING",    (0,0),(-1,-1), 4),
        ("BOTTOMPADDING", (0,0),(-1,-1), 4),
        ("LEFTPADDING",   (0,0),(-1,-1), 6),
        ("RIGHTPADDING",  (0,0),(-1,-1), 6),
    ]))

    right_hdr = Table(
        [[Paragraph(d.type.value, S["ev_typ"])],
         [sev_pill]],
        colWidths=[80],
    )
    right_hdr.setStyle(TableStyle([
        ("ALIGN",         (0,0),(-1,-1), "RIGHT"),
        ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
        ("TOPPADDING",    (0,0),(-1,-1), 2),
        ("BOTTOMPADDING", (0,0),(-1,-1), 2),
    ]))

    hdr = Table(
        [[Paragraph(f"FINDING #{i}", S["ev_num"]), right_hdr]],
        colWidths=[BODY_W - 100, 100],
    )
    hdr.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), C_NAVY),
        ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
        ("TOPPADDING",    (0,0),(-1,-1), 12),
        ("BOTTOMPADDING", (0,0),(-1,-1), 12),
        ("LEFTPADDING",   (0,0),(0, 0),  14),
        ("RIGHTPADDING",  (-1,0),(-1,-1),12),
    ]))
    story.append(hdr)

    # ── Location bar ─────────────────────────────────────────────────────────
    loc_tbl = Table(
        [[Paragraph(f"📍  {d.location}", S["ev_loc"])]],
        colWidths=[BODY_W],
    )
    loc_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), sev_lt),
        ("TOPPADDING",    (0,0),(-1,-1), 7),
        ("BOTTOMPADDING", (0,0),(-1,-1), 7),
        ("LEFTPADDING",   (0,0),(-1,-1), 14),
        ("RIGHTPADDING",  (0,0),(-1,-1), 14),
        ("LINEBELOW",     (0,0),(-1,-1), 1, sev_bg),
    ]))
    story.append(loc_tbl)
    story.append(Spacer(1, 12))

    # ── Images ───────────────────────────────────────────────────────────────
    full_p = Path(d.full_img_path) if d.full_img_path and Path(d.full_img_path).exists() else None
    crop_p = Path(d.img_path)      if d.img_path      and Path(d.img_path).exists()      else None

    if full_p and crop_p:
        # Top: full annotated frame (full width, big — gives context)
        fw, fh = _fit(full_p, BODY_W, 300)
        story.append(RLImage(str(full_p), width=fw, height=fh))
        story.append(Paragraph("Full frame  —  annotated with damage location",
                               S["ev_cap"]))
        story.append(Spacer(1, 10))

        # Bottom: crop closeup (left) + description (right)
        cw_img, ch_img = _fit(crop_p, BODY_W * 0.44, 190)
        crop_img = RLImage(str(crop_p), width=cw_img, height=ch_img)

        src = (f"Photo {d.frame}" if d.time_sec is None and d.frame
               else f"Frame {d.frame} at {d.time_sec:.1f}s" if d.time_sec is not None
               else None)

        desc_s = ParagraphStyle("ds", parent=S["b"]["Normal"],
                                fontSize=9, textColor=C_DARK, leading=14)
        meta_parts = list(filter(None, [src, d.location]))
        meta_s = ParagraphStyle("ms", parent=S["b"]["Normal"],
                                fontSize=8, textColor=C_MID, spaceAfter=0)
        right_content = [
            Paragraph("Close-up", S["cv_lbl"]),
            Spacer(1, 4),
            Paragraph(d.description, desc_s),
            Spacer(1, 8),
            Paragraph(" · ".join(meta_parts), meta_s) if meta_parts else Spacer(1, 0),
        ]

        bot_tbl = Table(
            [[crop_img, right_content]],
            colWidths=[BODY_W * 0.44 + 10, BODY_W * 0.56 - 10],
        )
        bot_tbl.setStyle(TableStyle([
            ("VALIGN",        (0,0),(-1,-1), "TOP"),
            ("LEFTPADDING",   (0,0),(-1,-1), 0),
            ("RIGHTPADDING",  (0,0),(-1,-1), 0),
            ("TOPPADDING",    (0,0),(-1,-1), 0),
            ("BOTTOMPADDING", (0,0),(-1,-1), 0),
            ("LEFTPADDING",   (1,0),(1,-1), 14),
        ]))
        story.append(bot_tbl)

    elif full_p:
        fw, fh = _fit(full_p, BODY_W, 380)
        story.append(RLImage(str(full_p), width=fw, height=fh))
        story.append(Spacer(1, 8))
        story.append(Paragraph(d.description, S["ev_desc"]))

    elif crop_p:
        # Just the crop — show it big and centered
        cw_img, ch_img = _fit(crop_p, BODY_W * 0.7, 300)
        crop_center = Table([[RLImage(str(crop_p), width=cw_img, height=ch_img)]],
                            colWidths=[BODY_W])
        crop_center.setStyle(TableStyle([("ALIGN",(0,0),(-1,-1),"CENTER")]))
        story.append(crop_center)
        story.append(Spacer(1, 8))
        story.append(Paragraph(d.description, S["ev_desc"]))

    story.append(PageBreak())


# ─── Public: Audit report ─────────────────────────────────────────────────────

def generate_audit_report(
    damages:      list[Damage],
    output_pdf:   Path,
    video_name:   str = "",
    session_id:   str = "",
    metadata:     "RentalMetadata | None" = None,
    recorded_at:  "datetime | None" = None,
    logo_path:    "Path | None" = None,
    car_img_path: "Path | None" = None,
) -> Path:
    output_pdf.parent.mkdir(parents=True, exist_ok=True)

    gen_at       = recorded_at or datetime.now()
    company      = _smart_title(metadata.rental_company if metadata else None)
    car_model    = _smart_title(metadata.car_model      if metadata else None)

    _cleanup_logo = False
    if logo_path and Path(logo_path).exists():
        logo_path = Path(logo_path)
    else:
        logo_path     = _get_logo(company)
        _cleanup_logo = True

    doc = SimpleDocTemplate(
        str(output_pdf), pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=40, bottomMargin=BOT_M,
    )
    S     = _S()
    story = []

    _cover(story, S, damages, metadata, session_id, video_name,
           gen_at, logo_path, car_img_path, company, car_model)

    _summary(story, S, damages)

    for i, d in enumerate(damages, 1):
        _evidence(story, S, i, d)

    cm = functools.partial(
        _NC, session_id=session_id,
        report_date=gen_at.strftime("%Y-%m-%d %H:%M"),
    )
    doc.build(story, canvasmaker=cm)

    if _cleanup_logo and logo_path and logo_path.exists():
        try: logo_path.unlink()
        except OSError: pass

    logger.info("Audit report → {}", output_pdf)
    return output_pdf


# ─── Public: Comparison / protection report ───────────────────────────────────

def generate_comparison_report(
    comparison:       list[ComparisonItem],
    company_damages:  list[dict],
    my_damage_count:  int,
    output_pdf:       Path,
    audit_pdf_name:   str = "",
    company_pdf_name: str = "",
    session_id:       str = "",
    metadata:         "RentalMetadata | None" = None,
) -> Path:
    output_pdf.parent.mkdir(parents=True, exist_ok=True)

    new_items       = [c for c in comparison if c.status == ComparisonStatus.NEW]
    matched_items   = [c for c in comparison if c.status == ComparisonStatus.MATCHED]
    uncertain_items = [c for c in comparison if c.status == ComparisonStatus.UNCERTAIN]

    doc = SimpleDocTemplate(
        str(output_pdf), pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=40, bottomMargin=BOT_M,
    )
    S     = _S()
    story = []
    base  = S["b"]

    # ── Header ────────────────────────────────────────────────────────────────
    hdr_s = ParagraphStyle("ph", parent=base["Normal"],
                           fontSize=14, fontName="Helvetica-Bold", textColor=C_WHITE)
    hdr = Table([[Paragraph("🛡  RentalShield — Damage Protection Report", hdr_s)]],
                colWidths=[BODY_W])
    hdr.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), C_NAVY),
        ("TOPPADDING",    (0,0),(-1,-1), 16),
        ("BOTTOMPADDING", (0,0),(-1,-1), 16),
        ("LEFTPADDING",   (0,0),(-1,-1), 14),
    ]))
    story.append(hdr)
    story.append(Spacer(1, 16))

    # ── Summary banner ────────────────────────────────────────────────────────
    bw = BODY_W / 4
    bn_hdr = ParagraphStyle("bnh", parent=base["Normal"],
                             fontSize=8, fontName="Helvetica-Bold",
                             textColor=C_WHITE, alignment=1)
    bn_val = ParagraphStyle("bnv", parent=base["Normal"],
                             fontSize=20, fontName="Helvetica-Bold",
                             textColor=C_DARK, alignment=1)
    bn_new = ParagraphStyle("bnn", parent=base["Normal"],
                             fontSize=20, fontName="Helvetica-Bold",
                             textColor=C_RED if new_items else C_GREEN,
                             alignment=1)
    banner = Table(
        [[Paragraph("YOUR AUDIT", bn_hdr), Paragraph("COMPANY DOCS", bn_hdr),
          Paragraph("⚠ NEW", bn_hdr),      Paragraph("UNCERTAIN", bn_hdr)],
         [Paragraph(str(my_damage_count),     bn_val),
          Paragraph(str(len(company_damages)), bn_val),
          Paragraph(str(len(new_items)),       bn_new),
          Paragraph(str(len(uncertain_items)), bn_val)]],
        colWidths=[bw, bw, bw, bw],
    )
    banner.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1, 0), C_NAVY),
        ("BACKGROUND",    (0,1),(-1,-1), C_BGLT),
        ("BACKGROUND",    (2,1),(2,-1),
         colors.HexColor("#FFF5F5") if new_items else colors.HexColor("#F0FFF4")),
        ("BOX",           (0,0),(-1,-1), 0.5, C_LINE),
        ("INNERGRID",     (0,0),(-1,-1), 0.5, C_LINE),
        ("ALIGN",         (0,0),(-1,-1), "CENTER"),
        ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
        ("TOPPADDING",    (0,0),(-1,-1), 10),
        ("BOTTOMPADDING", (0,0),(-1,-1), 10),
    ]))
    story.append(banner)
    story.append(Spacer(1, 20))

    tc = S["tc"]
    th = S["th"]

    def sec_hdr(txt):
        t = Table([[Paragraph(txt, ParagraphStyle("sh", parent=base["Normal"],
                              fontSize=10, fontName="Helvetica-Bold", textColor=C_WHITE))]],
                  colWidths=[BODY_W])
        t.setStyle(TableStyle([
            ("BACKGROUND",    (0,0),(-1,-1), C_NAVY),
            ("TOPPADDING",    (0,0),(-1,-1), 8),
            ("BOTTOMPADDING", (0,0),(-1,-1), 8),
            ("LEFTPADDING",   (0,0),(-1,-1), 12),
        ]))
        return t

    # NEW damages
    story.append(sec_hdr("⚠  NEW DAMAGES — Not in the Company's Report"))
    story.append(Spacer(1, 6))
    if new_items:
        nd_rows = [[Paragraph(h, th) for h in
                    ["Location", "Type", "Description", "Why NEW", "Photo"]]]
        for item in new_items:
            nd_rows.append([
                Paragraph(item.my_location, tc),
                Paragraph(item.my_type.value, tc),
                Paragraph(item.my_description, tc),
                Paragraph(item.reason, tc),
                _img_cell(item.img_path),
            ])
        nt = Table(nd_rows, colWidths=[108, 56, 140, 130, 77])
        nt.setStyle(TableStyle([
            ("BACKGROUND",  (0,0),(-1, 0), C_NAVY),
            ("BACKGROUND",  (0,1),(-1,-1), colors.HexColor("#FFF5F5")),
            ("FONTSIZE",    (0,0),(-1,-1), 8),
            ("ALIGN",       (0,0),(-1,-1), "CENTER"),
            ("VALIGN",      (0,0),(-1,-1), "MIDDLE"),
            ("GRID",        (0,0),(-1,-1), 0.3, C_LINE),
        ]))
        story.append(nt)
    else:
        story.append(Paragraph(
            "✅  All detected damages were already documented. You are covered.", S["ok"]
        ))

    story.append(Spacer(1, 16))
    story.append(sec_hdr("✅  Matched — Already in the Company's Report"))
    story.append(Spacer(1, 6))
    if matched_items:
        m_rows = [[Paragraph(h, th) for h in ["Location", "Type", "Match Reason"]]]
        for item in matched_items:
            m_rows.append([Paragraph(item.my_location, tc),
                           Paragraph(item.my_type.value, tc),
                           Paragraph(item.reason, tc)])
        mt = Table(m_rows, colWidths=[150, 80, 281])
        mt.setStyle(TableStyle([
            ("BACKGROUND",     (0,0),(-1, 0), C_NAVY),
            ("FONTSIZE",       (0,0),(-1,-1), 8),
            ("ALIGN",          (0,0),(-1,-1), "CENTER"),
            ("VALIGN",         (0,0),(-1,-1), "MIDDLE"),
            ("GRID",           (0,0),(-1,-1), 0.3, C_LINE),
            ("ROWBACKGROUNDS", (0,1),(-1,-1),
             [colors.white, colors.HexColor("#F0F8F4")]),
        ]))
        story.append(mt)
    else:
        story.append(Paragraph("No matched damages.", tc))

    if uncertain_items:
        story.append(Spacer(1, 16))
        story.append(sec_hdr("❓  Uncertain — Manual Review Recommended"))
        story.append(Spacer(1, 6))
        u_rows = [[Paragraph(h, th) for h in ["Location", "Type", "Reason"]]]
        for item in uncertain_items:
            u_rows.append([Paragraph(item.my_location, tc),
                           Paragraph(item.my_type.value, tc),
                           Paragraph(item.reason, tc)])
        ut = Table(u_rows, colWidths=[150, 80, 281])
        ut.setStyle(TableStyle([
            ("BACKGROUND",  (0,0),(-1, 0), colors.HexColor("#555555")),
            ("TEXTCOLOR",   (0,0),(-1, 0), C_WHITE),
            ("FONTSIZE",    (0,0),(-1,-1), 8),
            ("ALIGN",       (0,0),(-1,-1), "CENTER"),
            ("VALIGN",      (0,0),(-1,-1), "MIDDLE"),
            ("GRID",        (0,0),(-1,-1), 0.3, C_LINE),
        ]))
        story.append(ut)

    cm = functools.partial(_NC, session_id=session_id,
                           report_date=datetime.now().strftime("%Y-%m-%d %H:%M"))
    doc.build(story, canvasmaker=cm)
    logger.info("Protection report → {}", output_pdf)
    return output_pdf
