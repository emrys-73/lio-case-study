from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.core.deps import get_current_membership
from app.db.session import get_db
from app.models import Article, OrganizationMember
from app.schemas.articles import ArticleOut, ArticlePage, CatalogArticle, SearchOut, SuggestOut
from app.services import catalogue_search

router = APIRouter(prefix="/articles", tags=["articles"])


@router.get("", response_model=ArticlePage)
def list_articles(
    search: str | None = Query(
        default=None, description="Filter by description or article number (case-insensitive)"
    ),
    supplier_id: str | None = Query(default=None),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    membership: OrganizationMember = Depends(get_current_membership),
    db: Session = Depends(get_db),
) -> ArticlePage:
    filters = [Article.organization_id == membership.organization_id]
    if search:
        term = f"%{search}%"
        filters.append(
            or_(Article.description.ilike(term), Article.article_number.ilike(term))
        )
    if supplier_id:
        filters.append(Article.supplier_id == supplier_id)

    total = db.scalar(
        select(func.count()).select_from(Article).where(*filters)
    ) or 0

    stmt = (
        select(Article)
        .where(*filters)
        .options(joinedload(Article.supplier))
        .order_by(Article.article_number)
        .offset(offset)
        .limit(limit)
    )
    items = [
        ArticleOut(
            id=a.id,
            article_number=a.article_number,
            supplier_id=a.supplier_id,
            supplier_name=a.supplier.name if a.supplier else None,
            description=a.description,
            unit_price=a.unit_price,
            currency=a.currency,
            unit=a.unit,
            quantity=a.quantity,
            created_at=a.created_at,
        )
        for a in db.scalars(stmt)
    ]
    return ArticlePage(items=items, total=total, limit=limit, offset=offset)


@router.get("/count")
def count_articles(
    membership: OrganizationMember = Depends(get_current_membership),
    db: Session = Depends(get_db),
) -> dict[str, int]:
    total = (
        db.scalar(
            select(func.count())
            .select_from(Article)
            .where(Article.organization_id == membership.organization_id)
        )
        or 0
    )
    return {"count": total}


def _catalogue(db: Session, organization_id) -> catalogue_search.Catalogue:
    descriptions = db.scalars(
        select(Article.description).where(Article.organization_id == organization_id).distinct()
    ).all()
    return catalogue_search.catalogue_for(list(descriptions))


def _offers(db: Session, organization_id, descriptions: list[str]) -> dict[str, list[dict]]:
    stmt = (
        select(Article)
        .where(Article.organization_id == organization_id, Article.description.in_(descriptions))
        .options(joinedload(Article.supplier))
    )
    grouped: dict[str, list[dict]] = {}
    for a in db.scalars(stmt):
        grouped.setdefault(a.description, []).append(
            {
                "article_number": a.article_number,
                "description": a.description,
                "supplier_name": a.supplier.name if a.supplier else None,
                "unit": a.unit,
                "unit_price": float(a.unit_price),
                "currency": a.currency,
            }
        )
    return grouped


def _picked(offers: list[dict], vendor: str | None, unit: str | None) -> CatalogArticle | None:
    article = catalogue_search.pick_article(offers, vendor=vendor, unit=unit)
    return CatalogArticle(**article) if article else None


@router.get("/suggest", response_model=SuggestOut)
def suggest_article(
    q: str = Query(default="", max_length=500),
    vendor: str | None = Query(default=None, max_length=300),
    unit: str | None = Query(default=None, max_length=50),
    membership: OrganizationMember = Depends(get_current_membership),
    db: Session = Depends(get_db),
) -> SuggestOut:
    catalogue = _catalogue(db, membership.organization_id)
    method = catalogue_search.SHIPPED
    description = catalogue_search.sure(catalogue_search.rank(catalogue, q, method), method)
    if description is None:
        return SuggestOut(match=None)
    offers = _offers(db, membership.organization_id, [description]).get(description, [])
    return SuggestOut(match=_picked(offers, vendor, unit))


@router.get("/search", response_model=SearchOut)
def search_articles(
    q: str = Query(default="", max_length=500),
    limit: int = Query(default=5, ge=1, le=20),
    vendor: str | None = Query(default=None, max_length=300),
    unit: str | None = Query(default=None, max_length=50),
    membership: OrganizationMember = Depends(get_current_membership),
    db: Session = Depends(get_db),
) -> SearchOut:
    catalogue = _catalogue(db, membership.organization_id)
    descriptions = catalogue_search.search(catalogue, q, limit=limit)
    if not descriptions:
        return SearchOut(items=[])
    offers = _offers(db, membership.organization_id, descriptions)
    items = [_picked(offers.get(d, []), vendor, unit) for d in descriptions]
    return SearchOut(items=[item for item in items if item is not None])
