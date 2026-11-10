from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models import OrganizationMember, User
from app.routers.pdf import MAX_PDF_BYTES
from app.schemas.extraction import ExtractionRequest, ExtractionResponse
from app.services.extraction import extract_quote, extract_vendor_data

router = APIRouter(prefix="/extraction", tags=["extraction"])


def buyer_name(db: Session, user: User) -> str | None:
    membership = db.scalar(select(OrganizationMember).where(OrganizationMember.user_id == user.id))
    return membership.organization.name if membership else None


@router.post("", response_model=ExtractionResponse, response_model_by_alias=True)
def extract(
    payload: ExtractionRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ExtractionResponse:
    """Extract structured vendor data from PDF text via OpenAI.

    Returns ``{success, data?, error?, missingFields?}`` — the same envelope the
    original server action produced (errors are part of the payload, not HTTP
    errors, so the UI can show partial-extraction warnings).
    """
    return extract_vendor_data(payload.text, db, buyer_name(db, user))


@router.post("/pdf", response_model=ExtractionResponse, response_model_by_alias=True)
async def extract_pdf(
    file: UploadFile,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ExtractionResponse:
    if file.content_type not in ("application/pdf", "application/x-pdf"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Please upload a PDF file")
    pdf_bytes = await file.read()
    if len(pdf_bytes) > MAX_PDF_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="PDF exceeds the 10MB limit"
        )
    try:
        return extract_quote(pdf_bytes, db, buyer_name(db, user))
    except Exception:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Failed to read the PDF")
