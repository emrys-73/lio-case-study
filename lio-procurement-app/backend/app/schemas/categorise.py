from typing import Literal

from pydantic import BaseModel, field_validator

from app.schemas.requests import CommodityOut


class CategoriseLineIn(BaseModel):
    id: str
    description: str = ""
    quantity: float | None = None
    unit_price: float | None = None

    @field_validator("quantity", "unit_price", mode="before")
    @classmethod
    def _lenient_number(cls, value):
        if isinstance(value, str):
            try:
                return float(value.strip().replace(",", "."))
            except ValueError:
                return None
        return value


class CategoriseIn(BaseModel):
    lines: list[CategoriseLineIn]


class LineCategoryOut(BaseModel):
    line_id: str
    group_id: int | None
    source: Literal["rule", "none"]
    rule_id: str | None
    matched_keyword: str | None


class CategoriseOut(BaseModel):
    lines: list[LineCategoryOut]
    commodity: CommodityOut
