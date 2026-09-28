"""
Report generation and PDF export endpoints.
Generates "Inspection Passport" PDFs with photo gallery and inspection summary.
"""

from fastapi import APIRouter, Request, HTTPException, Depends, status
from pydantic import BaseModel, Field
from loguru import logger
from datetime import datetime
from typing import Optional, List
from sqlalchemy.orm import Session
from pathlib import Path
import os

from rentalshield.i18n import get_text
from rentalshield.i18n.middleware import get_language
from rentalshield.db.database import get_db
from rentalshield.db.models import CarProfile, RentalSession, InspectionPhoto, DisputeReport
from rentalshield.config import settings

router = APIRouter()


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class ReportDetail(BaseModel):
    """Report detail response."""
    id: str = Field(..., description="Report ID")
    car_id: str = Field(..., description="Car profile ID")
    report_title: str = Field(..., description="Report title")
    pdf_uri: Optional[str] = Field(None, description="PDF file path")
    pdf_generated_at: Optional[datetime] = Field(None, description="Generation timestamp")
    created_at: datetime = Field(..., description="Created timestamp")

    class Config:
        from_attributes = True


class ReportResponse(BaseModel):
    """Report response."""
    success: bool = Field(True, description="Success status")
    message: str = Field(..., description="Status message")
    data: dict = Field(..., description="Response data")
    language: str = Field(..., description="User language")

    class Config:
        example = {
            "success": True,
            "message": "Success",
            "data": {
                "id": "uuid",
                "car_id": "uuid",
                "report_title": "Ford Focus (ABC-1234) - Inspection Report",
                "pdf_uri": "file:///data/reports/uuid.pdf",
                "pdf_generated_at": "2026-09-28T10:00:00",
                "created_at": "2026-09-28T10:00:00"
            },
            "language": "en"
        }


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _generate_pdf_reportlab(car: CarProfile, sessions: List[RentalSession], photos: List[InspectionPhoto]) -> bytes:
    """
    Generate PDF using ReportLab.
    Creates professional "Inspection Passport" with:
    - Car details
    - Pickup & Dropoff inspection summary
    - Pre-existing damage list
    - Photo thumbnails (8 angles)
    - Digital signature ready
    """
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak, Image
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    from io import BytesIO
    
    # Create PDF in memory
    pdf_buffer = BytesIO()
    doc = SimpleDocTemplate(pdf_buffer, pagesize=letter,
                           rightMargin=0.5*inch, leftMargin=0.5*inch,
                           topMargin=0.5*inch, bottomMargin=0.5*inch)
    
    styles = getSampleStyleSheet()
    story = []
    
    # ════════════════════════════════════════════════════════════════════════
    # HEADER
    # ════════════════════════════════════════════════════════════════════════
    
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#1F2937'),
        spaceAfter=6,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )
    
    subtitle_style = ParagraphStyle(
        'CustomSubtitle',
        parent=styles['Normal'],
        fontSize=12,
        textColor=colors.HexColor('#6B7280'),
        spaceAfter=20,
        alignment=TA_CENTER,
    )
    
    story.append(Paragraph("🛡️ RENTALSHIELD INSPECTION PASSPORT", title_style))
    story.append(Paragraph(f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}", subtitle_style))
    
    # ════════════════════════════════════════════════════════════════════════
    # CAR DETAILS
    # ════════════════════════════════════════════════════════════════════════
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=colors.HexColor('#111827'),
        spaceAfter=10,
        spaceBefore=10,
        fontName='Helvetica-Bold'
    )
    
    story.append(Paragraph("RENTAL VEHICLE DETAILS", heading_style))
    
    car_details = [
        ["Attribute", "Value"],
        ["Rental Provider", car.rental_provider or "N/A"],
        ["Make / Model", f"{car.make or 'N/A'} / {car.model or 'N/A'}"],
        ["Year", str(car.year or "N/A")],
        ["License Plate", car.license_plate],
        ["VIN", car.vin or "N/A"],
        ["Color", car.color or "N/A"],
        ["Pickup Location", car.pickup_location or "N/A"],
        ["Dropoff Location", car.dropoff_location or "N/A"],
        ["Rental Period", f"{car.rental_start_date.strftime('%Y-%m-%d')} to {car.rental_end_date.strftime('%Y-%m-%d')}"],
    ]
    
    car_table = Table(car_details, colWidths=[2*inch, 4*inch])
    car_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#F3F4F6')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#1F2937')),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 11),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.HexColor('#374151')),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F9FAFB')]),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#E5E7EB')),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    
    story.append(car_table)
    story.append(Spacer(1, 0.3*inch))
    
    # ════════════════════════════════════════════════════════════════════════
    # INSPECTION SESSIONS
    # ════════════════════════════════════════════════════════════════════════
    
    for session in sessions:
        session_title = f"INSPECTION: {session.session_type.value.upper()}"
        story.append(Paragraph(session_title, heading_style))
        
        # Session details
        session_details = [
            ["Time", session.timestamp.strftime('%Y-%m-%d %H:%M UTC')],
            ["Location", session.gps_address or f"{session.gps_latitude}, {session.gps_longitude}"],
            ["GPS Accuracy", f"{session.gps_accuracy_meters or 'N/A'} meters"],
            ["Status", "✓ Complete" if session.is_complete else "⏳ In Progress"],
            ["Photos Captured", str(len(session.inspection_photos) or 0)],
        ]
        
        session_table = Table(session_details, colWidths=[2*inch, 4*inch])
        session_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F0F9FF')),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#1E40AF')),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#93C5FD')),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        
        story.append(session_table)
        
        # Pre-existing damages (if any)
        if session.pre_existing_damages:
            story.append(Spacer(1, 0.15*inch))
            story.append(Paragraph("Pre-Existing Damages", ParagraphStyle(
                'DamageHeading',
                parent=styles['Normal'],
                fontSize=11,
                textColor=colors.HexColor('#DC2626'),
                fontName='Helvetica-Bold',
                spaceAfter=8,
            )))
            
            damage_items = []
            for damage in session.pre_existing_damages:
                severity_emoji = {
                    "minor": "🟡",
                    "moderate": "🟠",
                    "severe": "🔴",
                }.get(damage.get("severity", "unknown"), "⚪")
                
                damage_text = f"{severity_emoji} <b>{damage.get('location', 'Unknown')}</b>: {damage.get('description', 'N/A')}"
                damage_items.append(Paragraph(damage_text, styles['Normal']))
                story.append(damage_items[-1])
                story.append(Spacer(1, 0.08*inch))
        
        story.append(Spacer(1, 0.2*inch))
    
    # ════════════════════════════════════════════════════════════════════════
    # PHOTOS
    # ════════════════════════════════════════════════════════════════════════
    
    if photos:
        story.append(PageBreak())
        story.append(Paragraph("INSPECTION PHOTOS", heading_style))
        
        # Photos grid (2x4 layout)
        photo_grid = []
        row = []
        
        for photo in photos:
            # Try to add photo image if it exists locally
            try:
                local_path = photo.local_uri.replace("file://", "")
                if os.path.exists(local_path):
                    img = Image(local_path, width=2.8*inch, height=2.1*inch)
                    row.append(img)
                else:
                    # Placeholder
                    row.append(Paragraph(f"📷 {photo.angle_code.value}", styles['Normal']))
            except Exception as e:
                logger.warning("Could not include photo: {}", e)
                row.append(Paragraph(f"📷 {photo.angle_code.value}", styles['Normal']))
            
            if len(row) == 2:
                photo_grid.append(row)
                row = []
        
        if row:  # Add remaining photos
            while len(row) < 2:
                row.append(Paragraph("", styles['Normal']))
            photo_grid.append(row)
        
        if photo_grid:
            photo_table = Table(photo_grid, colWidths=[3*inch, 3*inch])
            photo_table.setStyle(TableStyle([
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('LEFTPADDING', (0, 0), (-1, -1), 10),
                ('RIGHTPADDING', (0, 0), (-1, -1), 10),
                ('TOPPADDING', (0, 0), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
            ]))
            story.append(photo_table)
    
    # ════════════════════════════════════════════════════════════════════════
    # FOOTER
    # ════════════════════════════════════════════════════════════════════════
    
    story.append(Spacer(1, 0.3*inch))
    footer_style = ParagraphStyle(
        'Footer',
        parent=styles['Normal'],
        fontSize=9,
        textColor=colors.HexColor('#9CA3AF'),
        alignment=TA_CENTER,
    )
    story.append(Paragraph(
        f"🛡️ RentalShield Phase 1 | Report ID: {datetime.utcnow().strftime('%Y%m%d-%H%M%S')} | "
        f"<i>This report is generated by automated inspection system</i>",
        footer_style
    ))
    
    # Build PDF
    doc.build(story)
    pdf_buffer.seek(0)
    return pdf_buffer.getvalue()


def _to_detail(report: DisputeReport) -> dict:
    """Convert model to detail response."""
    return {
        "id": report.id,
        "car_id": report.car_profile_id,
        "report_title": report.report_title or "Inspection Report",
        "pdf_uri": report.pdf_uri,
        "pdf_generated_at": report.pdf_generated_at,
        "created_at": report.created_at,
    }


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.post("/{car_id}/generate", response_model=ReportResponse, status_code=201)
async def generate_report(
    car_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Generate PDF Inspection Passport report for a car.
    
    Includes:
    - Car details (make, model, license plate, etc.)
    - Pickup & Dropoff inspection summary
    - Pre-existing damage list
    - 8-angle photo gallery
    - Professional formatting for disputes
    """
    lang = get_language(request)
    
    try:
        logger.info("Generate report: car={}", car_id)
        
        # Get car profile
        car = db.query(CarProfile).filter(CarProfile.id == car_id).first()
        if not car:
            error_msg = get_text("error.carNotFound", language=lang)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_msg,
            )
        
        # Get all sessions for this car
        sessions = db.query(RentalSession).filter(
            RentalSession.car_profile_id == car_id
        ).order_by(RentalSession.timestamp.asc()).all()
        
        # Get all photos (from all sessions)
        photos = db.query(InspectionPhoto).join(
            RentalSession, InspectionPhoto.rental_session_id == RentalSession.id
        ).filter(
            RentalSession.car_profile_id == car_id
        ).order_by(InspectionPhoto.angle_code.asc()).all()
        
        logger.info("✓ Retrieved: {} sessions, {} photos", len(sessions), len(photos))
        
        # Generate PDF
        pdf_bytes = _generate_pdf_reportlab(car, sessions, photos)
        logger.info("✓ PDF generated: {} bytes", len(pdf_bytes))
        
        # Save PDF to disk
        settings.ensure_dirs()
        pdf_filename = f"{car_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.pdf"
        pdf_path = settings.reports_dir / pdf_filename
        
        with open(pdf_path, "wb") as f:
            f.write(pdf_bytes)
        
        logger.info("✓ PDF saved: {}", pdf_path)
        
        # Create report record
        report = DisputeReport(
            car_profile_id=car_id,
            report_title=f"{car.make} {car.model} ({car.license_plate}) - Inspection Report",
            pdf_uri=f"file://{pdf_path}",
            pdf_generated_at=datetime.utcnow(),
            pdf_size_bytes=len(pdf_bytes),
        )
        db.add(report)
        db.commit()
        db.refresh(report)
        
        logger.info("✓ Report record created: {}", report.id)
        
        success_msg = get_text("common.success", language=lang)
        return ReportResponse(
            success=True,
            message=success_msg,
            data=_to_detail(report),
            language=lang,
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Report generation error: {}", e, exc_info=True)
        error_msg = get_text("error.reportGenerationFailed", language=lang)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_msg,
        )


@router.get("/{car_id}/latest", response_model=ReportResponse)
async def get_latest_report(
    car_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """Get the latest generated report for a car."""
    lang = get_language(request)
    
    try:
        # Verify car exists
        car = db.query(CarProfile).filter(CarProfile.id == car_id).first()
        if not car:
            error_msg = get_text("error.carNotFound", language=lang)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_msg,
            )
        
        # Get latest report
        report = db.query(DisputeReport).filter(
            DisputeReport.car_profile_id == car_id
        ).order_by(DisputeReport.created_at.desc()).first()
        
        if not report:
            error_msg = get_text("error.reportNotFound", language=lang)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_msg,
            )
        
        success_msg = get_text("common.success", language=lang)
        return ReportResponse(
            success=True,
            message=success_msg,
            data=_to_detail(report),
            language=lang,
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Get report error: {}", e, exc_info=True)
        error_msg = get_text("error.fetchFailed", language=lang)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_msg,
        )


@router.get("/{car_id}", response_model=ReportResponse)
async def get_car_report(
    car_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """Get the latest report for a car (alias for /latest)."""
    return await get_latest_report(car_id, request, db)
