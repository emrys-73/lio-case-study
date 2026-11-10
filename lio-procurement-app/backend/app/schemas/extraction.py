from pydantic import BaseModel, ConfigDict, Field, field_validator


class PdfParseResponse(BaseModel):
    text: str


class ExtractionRequest(BaseModel):
    text: str


# camelCase on the wire — matches the AI's JSON output format and what the
# frontend's extraction flow already consumes.
class OrderLineData(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    position_description: str | None = Field(default=None, alias="positionDescription")
    unit_price: float | None = Field(default=None, alias="unitPrice")
    amount: float | None = None
    unit: str | None = None
    total_price: float | None = Field(default=None, alias="totalPrice")


class ExtractedVendorData(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    title: str | None = None
    vendor_name: str | None = Field(default=None, alias="vendorName")
    vat_id: str | None = Field(default=None, alias="vatId")
    department: str | None = None
    order_lines: list[OrderLineData] = Field(default_factory=list, alias="orderLines")
    total_cost: float | None = Field(default=None, alias="totalCost")

    @field_validator("order_lines", mode="before")
    @classmethod
    def _null_lines_are_empty(cls, value):
        return [] if value is None else value
    commodity_group_id: int | None = Field(default=None, alias="commodityGroupId")
    commodity_group_name: str | None = Field(default=None, alias="commodityGroupName")


class ExtractionResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    success: bool
    data: ExtractedVendorData | None = None
    error: str | None = None
    missing_fields: list[str] | None = Field(default=None, alias="missingFields")
