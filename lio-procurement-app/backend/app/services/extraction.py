import json
import logging

from openai import OpenAI
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import CommodityGroup
from app.schemas.extraction import ExtractedVendorData, ExtractionResponse

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a data extraction and classification specialist. Always respond with "
    "valid JSON only, no markdown or code blocks. Extract all information accurately "
    "from German business documents and classify into the appropriate commodity "
    "group based on the full context of the offer."
)


def _nullable(kind: str) -> dict:
    return {"type": [kind, "null"]}


def _strict_object(properties: dict) -> dict:
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


REPLY_SCHEMA = _strict_object({
    "title": _nullable("string"),
    "vendorName": _nullable("string"),
    "vatId": _nullable("string"),
    "department": _nullable("string"),
    "orderLines": {
        "type": "array",
        "items": _strict_object({
            "positionDescription": _nullable("string"),
            "unitPrice": _nullable("number"),
            "amount": _nullable("number"),
            "unit": _nullable("string"),
            "totalPrice": _nullable("number"),
            "kind": {"type": "string", "enum": ["item", "charge"]},
        }),
    },
    "alternatives": {
        "type": "array",
        "items": _strict_object({
            "positionDescription": _nullable("string"),
            "totalPrice": _nullable("number"),
        }),
    },
    "totalCost": _nullable("number"),
    "commodityGroupId": _nullable("integer"),
    "commodityGroupName": _nullable("string"),
})


def _build_prompt(pdf_text: str, commodity_groups_list: str) -> str:
    return f"""Extract the purchase from this supplier quote (Angebot) AND classify it into one commodity group. The quote is usually German.

Document Text:
{pdf_text}

Fields:
1. title: a short (2-5 words) description of what is being bought.
2. vendorName: the company that sent the quote (Lieferant/Anbieter/Firma).
3. vatId: the vendor's VAT ID (USt-IdNr./UID/VAT ID/Umsatzsteuer-ID). null if the quote has none. A tax number (Steuernummer) or a customer number is not a VAT ID.
4. department: the buyer's department if the quote names one (Abteilung). Otherwise null.
5. orderLines: everything the buyer pays for, one line each:
   - positionDescription: the item or charge as printed (Bezeichnung/Artikel)
   - unitPrice: price per unit before VAT (Einzelpreis/E.P.)
   - amount: the quantity (Menge/Anzahl). Can be a decimal: "1,28 qm" is 1.28
   - unit: in English ("Stück" -> "pieces", "Lizenzen" -> "licenses", "qm" -> "sqm", "lfm" -> "m", "Pauschale" -> "lump sum")
   - totalPrice: the line total before VAT, after any discount on that line (Gesamtpreis/G.P.)
   - kind: "item" for goods and services, "charge" for shipping, delivery, installation, packaging, levies and other fees
6. alternatives: positions offered as an alternative or option, with their total (or unit price if no total is printed).
7. totalCost: the net total before VAT. Items plus charges.
8. commodityGroupId and commodityGroupName: the SINGLE most appropriate commodity group from the list below.

Rules:
- Charges are order lines, also when the quote prints them under the table or in the totals block (Versandkosten, Fracht, Transport, Lieferung, Montage, Verpackung, Urheberrechtsabgabe). Without them the lines do not add up to the total.
- Alternatives and optional positions are not order lines. Look for "Alternative", "Alt.", "Option", "optional", "Eventualposition", or a sub-position like 1.1a / 1.1b offered instead of another one. Put them in alternatives only.
- Headings and group titles with no price of their own are not order lines.
- totalCost is the net total before VAT (Nettobetrag, Summe netto, Zwischensumme plus charges). Never the gross amount with VAT (Bruttobetrag, Gesamtbetrag inkl. MwSt., Endbetrag, Rechnungsbetrag).
- Copy numbers as printed, as plain numbers: dot for decimals, no thousands separator, no currency sign. "1.438,00 EUR" is 1438.00.
- When something is not in the document, use null. Never guess.

Available Commodity Groups (ID | Category | Name):
{commodity_groups_list}

For classification, consider the PRIMARY nature and purpose of the items:
  * Branded office decor/furniture → Office Equipment (15)
  * Traditional promotional items (brochures, giveaways, banners) → Promotional Materials (43)
  * Software/IT products → Software (31) or IT Services (30)
  * If genuinely uncertain, set commodityGroupId to null"""


def _strip_markdown_fences(content: str) -> str:
    cleaned = content.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned.removeprefix("```json").strip()
    elif cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```").strip()
    if cleaned.endswith("```"):
        cleaned = cleaned.removesuffix("```").strip()
    return cleaned


def request_params(pdf_text: str, commodity_groups_list: str) -> dict:
    return {
        "model": settings.openai_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _build_prompt(pdf_text, commodity_groups_list)},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "quote_extraction", "strict": True, "schema": REPLY_SCHEMA},
        },
        "max_completion_tokens": 4000,
        "temperature": 0,
    }


def parse_reply(content: str) -> ExtractedVendorData:
    return ExtractedVendorData.model_validate(json.loads(_strip_markdown_fences(content)))


def _blank(value: str | None) -> bool:
    return value is None or not value.strip()


def find_missing_fields(extracted: ExtractedVendorData) -> list[str]:
    missing: list[str] = []
    if _blank(extracted.title):
        missing.append("Title/Short Description")
    if _blank(extracted.vendor_name):
        missing.append("Vendor Name")
    if _blank(extracted.vat_id):
        missing.append("VAT ID")
    if _blank(extracted.department):
        missing.append("Department")
    if not extracted.order_lines:
        missing.append("Order Lines")
    if not extracted.total_cost:
        missing.append("Total Cost")
    if not extracted.commodity_group_id or not extracted.commodity_group_name:
        missing.append("Commodity Group")
    return missing


def extract_vendor_data(pdf_text: str, db: Session) -> ExtractionResponse:
    """Extract vendor data and classify commodity group in one AI call.

    Port of ``src/actions/extraction.ts`` — same prompt, model and validation.
    """
    if not pdf_text or not pdf_text.strip():
        return ExtractionResponse(success=False, error="No text provided for extraction")

    if not settings.openai_api_key:
        return ExtractionResponse(
            success=False,
            error="OPENAI_API_KEY is not configured on the server",
        )

    commodity_groups = list(
        db.scalars(select(CommodityGroup).order_by(CommodityGroup.id))
    )
    if not commodity_groups:
        return ExtractionResponse(
            success=False,
            error="Failed to load commodity groups for classification",
        )

    # Give the model the full commodity catalog so it has complete context to
    # pick the most accurate match in a single pass.
    commodity_groups_list = "\n".join(
        f"{g.id} | {g.category} | {g.name}" for g in commodity_groups
    )

    try:
        client = OpenAI(api_key=settings.openai_api_key)
        response = client.chat.completions.create(
            **request_params(pdf_text, commodity_groups_list)
        )

        content = response.choices[0].message.content
        if not content:
            return ExtractionResponse(success=False, error="Empty response from AI")

        extracted = parse_reply(content)
    except Exception as exc:  # noqa: BLE001 — mirror the original catch-all
        logger.exception("Error extracting vendor data")
        return ExtractionResponse(success=False, error=str(exc))

    missing_fields = find_missing_fields(extracted)

    # Validate that the returned commodity group id actually exists.
    if extracted.commodity_group_id is not None:
        valid_ids = {g.id for g in commodity_groups}
        if extracted.commodity_group_id not in valid_ids:
            logger.warning(
                "Invalid commodity group ID returned: %s", extracted.commodity_group_id
            )
            extracted.commodity_group_id = None
            extracted.commodity_group_name = None
            if "Commodity Group" not in missing_fields:
                missing_fields.append("Commodity Group")

    return ExtractionResponse(
        success=True,
        data=extracted,
        missing_fields=missing_fields or None,
    )
