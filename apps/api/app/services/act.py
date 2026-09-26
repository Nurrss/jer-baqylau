"""Inspection act (акт осмотра) as PDF — reportlab with an embedded Cyrillic/Kazakh font."""

from __future__ import annotations

import asyncio
import hashlib
import io
import uuid
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.i18n import t
from app.core.logging import get_logger
from app.db.models import Act, Photo
from app.domain.enums import Lang, ParcelStatus, PhotoOwnerType
from app.providers.storage import StorageProvider
from app.schemas.parcels import ParcelDetail
from app.services import audit
from app.services import parcels as parcel_service

log = get_logger(__name__)

FONTS_DIR = Path(__file__).resolve().parents[1] / "assets" / "fonts"
TZ = ZoneInfo("Asia/Almaty")
MAX_PHOTOS = 4
PRIMARY = colors.HexColor("#0b6aa8")
MUTED = colors.HexColor("#5a6b80")


@lru_cache
def _register_fonts() -> None:
    pdfmetrics.registerFont(TTFont("DejaVu", str(FONTS_DIR / "DejaVuSans.ttf")))
    pdfmetrics.registerFont(TTFont("DejaVu-Bold", str(FONTS_DIR / "DejaVuSans-Bold.ttf")))
    pdfmetrics.registerFontFamily("DejaVu", normal="DejaVu", bold="DejaVu-Bold")


def _styles() -> dict[str, ParagraphStyle]:
    base = ParagraphStyle("base", fontName="DejaVu", fontSize=9.5, leading=13)
    return {
        "base": base,
        "org": ParagraphStyle("org", parent=base, fontSize=8.5, textColor=MUTED, alignment=TA_CENTER),
        "title": ParagraphStyle("title", parent=base, fontName="DejaVu-Bold", fontSize=15, leading=19,
                                alignment=TA_CENTER, spaceBefore=6),
        "number": ParagraphStyle("number", parent=base, alignment=TA_CENTER, textColor=MUTED, spaceAfter=10),
        "h": ParagraphStyle("h", parent=base, fontName="DejaVu-Bold", fontSize=11, leading=15, textColor=PRIMARY,
                            spaceBefore=10, spaceAfter=5),
        "cell": ParagraphStyle("cell", parent=base, fontSize=9, leading=12),
        "cellb": ParagraphStyle("cellb", parent=base, fontName="DejaVu-Bold", fontSize=9, leading=12),
        "small": ParagraphStyle("small", parent=base, fontSize=7.5, leading=10, textColor=MUTED),
    }  # fmt: skip


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


@dataclass(slots=True)
class ActPhoto:
    data: bytes
    caption: str


def _findings(detail: ParcelDetail, lang: Lang) -> list[str]:
    """Inspector comments of the current violation case, oldest first."""
    if detail.status in (ParcelStatus.OK, ParcelStatus.UNDER_CHECK) and not detail.violation_type:
        return []
    items = [
        h.comment
        for h in reversed(detail.history)
        if h.comment and h.actor.startswith("inspector") and h.to_status != ParcelStatus.UNDER_CHECK.value
    ]
    if not items and detail.violation_type:
        items = [t(lang, f"violation-{detail.violation_type.value}")]
    return items


@dataclass(frozen=True, slots=True)
class ActVerification:
    """Registry data printed on the act: number, QR link and fingerprints."""

    number: str
    url: str
    chain_head: str
    chain_length: int
    photo_count: int


def _qr(url: str, size_mm: float = 30) -> Drawing:
    widget = QrCodeWidget(url, barLevel="M")
    x0, y0, x1, y1 = widget.getBounds()
    size = size_mm * mm
    drawing = Drawing(size, size, transform=[size / (x1 - x0), 0, 0, size / (y1 - y0), 0, 0])
    drawing.add(widget)
    return drawing


def render_act(
    detail: ParcelDetail,
    lang: Lang,
    inspector: str,
    photos: list[ActPhoto],
    now: datetime | None = None,
    verification: ActVerification | None = None,
) -> bytes:
    _register_fonts()
    s = _styles()
    now = (now or datetime.now(TZ)).astimezone(TZ)
    fmt_date = lambda d: d.astimezone(TZ).strftime("%d.%m.%Y") if d else "—"  # noqa: E731
    number = (
        verification.number
        if verification
        else f"{detail.cadastral_number.replace(':', '')[-6:]}-{now:%y%m%d}"
    )

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=18 * mm,
        title=f"{t(lang, 'act-title')} {detail.cadastral_number}",
        author="ЖерБақылау",
    )
    story: list = [
        Paragraph(_escape(t(lang, "act-org")), s["org"]),
        Paragraph(_escape(t(lang, "act-title")), s["title"]),
        Paragraph(_escape(t(lang, "act-number", number=number, date=now.strftime("%d.%m.%Y"))), s["number"]),
        Paragraph(_escape(t(lang, "act-intro", inspector=inspector)), s["base"]),
        Paragraph(_escape(t(lang, "act-section-parcel")), s["h"]),
    ]

    address = detail.address_kk if lang is Lang.KK else detail.address_ru
    rows = [
        (t(lang, "act-field-cadastral"), detail.cadastral_number),
        (t(lang, "act-field-address"), address),
        (t(lang, "act-field-purpose"), t(lang, f"purpose-{detail.purpose.value}")),
        (
            t(lang, "act-field-area"),
            t(lang, "act-area-value", value=f"{detail.area_ha:.4f}".rstrip("0").rstrip(".")),
        ),
        (t(lang, "act-field-owner"), t(lang, f"owner-{detail.owner_type.value}")),
    ]
    if detail.lease_until:
        rows.append((t(lang, "act-field-lease"), detail.lease_until.strftime("%d.%m.%Y")))
    rows.append((t(lang, "act-field-status"), t(lang, f"pstatus-{detail.status.value}")))
    if detail.violation_type:
        rows.append((t(lang, "act-field-violation"), t(lang, f"violation-{detail.violation_type.value}")))
    if detail.deadline_at and detail.status in (ParcelStatus.VIOLATION, ParcelStatus.IN_REMEDIATION):
        rows.append((t(lang, "act-field-deadline"), fmt_date(detail.deadline_at)))
    rows.append((t(lang, "act-field-coords"), f"{detail.centroid.lat:.6f}, {detail.centroid.lon:.6f}"))

    table = Table(
        [[Paragraph(_escape(k), s["cellb"]), Paragraph(_escape(v), s["cell"])] for k, v in rows],
        colWidths=[52 * mm, None],
    )
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cfd7e1")),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eef2f6")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(table)

    story.append(Paragraph(_escape(t(lang, "act-section-findings")), s["h"]))
    findings = _findings(detail, lang)
    if findings:
        story.extend(Paragraph(f"• {_escape(item)}", s["base"]) for item in findings)
    else:
        story.append(Paragraph(_escape(t(lang, "act-no-findings")), s["base"]))

    story.append(Paragraph(_escape(t(lang, "act-section-signals")), s["h"]))
    if detail.signals:
        for signal in detail.signals:
            line = t(
                lang,
                "act-signal-line",
                code=signal.tracking_code,
                date=fmt_date(signal.created_at),
                category=t(lang, f"category-{signal.category.value}"),
                status=t(lang, f"sstatus-{signal.status.value}"),
            )
            story.append(Paragraph(f"• {_escape(line)}", s["base"]))
    else:
        story.append(Paragraph(_escape(t(lang, "act-no-signals")), s["base"]))

    photo_block: list = [Paragraph(_escape(t(lang, "act-section-photos")), s["h"])]
    if photos:
        cells = []
        for photo in photos[:MAX_PHOTOS]:
            image = Image(io.BytesIO(photo.data))
            ratio = image.imageHeight / image.imageWidth
            image.drawWidth = 80 * mm
            image.drawHeight = 80 * mm * ratio
            cells.append([image, Paragraph(_escape(photo.caption), s["small"])])
        grid = [cells[i : i + 2] for i in range(0, len(cells), 2)]
        grid_rows = [[Table([[c[0]], [c[1]]]) for c in row] + [""] * (2 - len(row)) for row in grid]
        photo_table = Table(grid_rows, colWidths=[87 * mm, 87 * mm])
        photo_table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
        photo_block.append(photo_table)
    else:
        photo_block.append(Paragraph(_escape(t(lang, "act-no-photos")), s["base"]))
    story.append(KeepTogether(photo_block))

    if verification:
        info = [
            t(lang, "act-verify-number", number=verification.number),
            t(lang, "act-verify-url", url=verification.url),
            t(lang, "act-verify-chain", head=verification.chain_head[:16], count=verification.chain_length),
            t(lang, "act-verify-photos", count=verification.photo_count),
            t(lang, "act-verify-note"),
        ]
        verify_table = Table(
            [[_qr(verification.url), [Paragraph(_escape(line), s["small"]) for line in info]]],
            colWidths=[36 * mm, None],
        )
        verify_table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
        story.append(KeepTogether([Paragraph(_escape(t(lang, "act-section-verify")), s["h"]), verify_table]))

    signatures = Table(
        [
            [Paragraph(_escape(t(lang, "act-sign-inspector")), s["cellb"]), "", Paragraph(_escape(t(lang, "act-sign-owner")), s["cellb"])],
            ["_" * 34, "", "_" * 34],
            [Paragraph(_escape(t(lang, "act-sign-hint")), s["small"]), "", Paragraph(_escape(t(lang, "act-sign-hint")), s["small"])],
        ],
        colWidths=[78 * mm, 18 * mm, 78 * mm],
    )  # fmt: skip
    story.extend([Spacer(1, 14 * mm), KeepTogether([signatures])])

    footer_text = lambda page: t(lang, "act-footer", datetime=now.strftime("%d.%m.%Y %H:%M"), page=page)  # noqa: E731

    def _footer(canvas, document) -> None:  # type: ignore[no-untyped-def]
        canvas.saveState()
        canvas.setFont("DejaVu", 7)
        canvas.setFillColor(MUTED)
        canvas.drawString(18 * mm, 10 * mm, footer_text(document.page))
        canvas.setStrokeColor(PRIMARY)
        canvas.setLineWidth(1.2)
        canvas.line(18 * mm, A4[1] - 11 * mm, A4[0] - 18 * mm, A4[1] - 11 * mm)
        canvas.restoreState()

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buffer.getvalue()


async def build_act(
    session: AsyncSession, storage: StorageProvider, parcel_id: uuid.UUID, lang: Lang, inspector: str
) -> tuple[str, bytes]:
    detail = await parcel_service.get_detail(session, storage, parcel_id)
    # Inspector photos first, then the citizens' ones (from linked signals).
    signal_ids = [uuid.UUID(sig.id) for sig in detail.signals]
    rows = list(
        await session.scalars(
            select(Photo)
            .where(
                ((Photo.owner_type == PhotoOwnerType.PARCEL) & (Photo.owner_id == parcel_id))
                | ((Photo.owner_type == PhotoOwnerType.SIGNAL) & (Photo.owner_id.in_(signal_ids)))
            )
            .order_by(Photo.owner_type, Photo.created_at.desc())
            .limit(MAX_PHOTOS)
        )
    )
    photos: list[ActPhoto] = []
    for photo in rows:
        try:
            data = await storage.download(photo.thumb_path)
        except Exception:
            log.warning("act_photo_unavailable", photo_id=str(photo.id))
            continue
        taken = (photo.taken_at or photo.created_at).astimezone(TZ).strftime("%d.%m.%Y")
        photos.append(
            ActPhoto(
                data=data,
                caption=t(
                    lang,
                    "act-photo-caption",
                    source=t(lang, f"photo-source-{photo.source.value}"),
                    date=taken,
                ),
            )
        )
    # Register the act: its number, the audit-chain state and the evidence fingerprints are fixed now.
    act_id = uuid.uuid4()
    seq = int(await session.scalar(select(func.nextval("act_number_seq"))) or 0)
    number = f"A-{datetime.now(TZ):%Y}-{seq:05d}"
    head, length = await audit.chain_state(session)
    photo_hashes = [p.sha256 for p in rows if p.sha256]
    url = f"{get_settings().public_web_url.rstrip('/')}/verify/{act_id}"
    verification = ActVerification(number, url, head, length, len(photo_hashes))
    pdf = await asyncio.to_thread(render_act, detail, lang, inspector, photos, None, verification)
    session.add(
        Act(
            id=act_id,
            number=number,
            parcel_id=parcel_id,
            cadastral_number=detail.cadastral_number,
            parcel_status=detail.status.value,
            lang=lang,
            pdf_sha256=hashlib.sha256(pdf).hexdigest(),
            chain_head=head,
            chain_length=length,
            photo_hashes=photo_hashes,
            issued_by=inspector,
        )
    )
    await session.flush()
    filename = f"act_{number}_{detail.cadastral_number.replace(':', '-')}_{lang.value}.pdf"
    return filename, pdf
