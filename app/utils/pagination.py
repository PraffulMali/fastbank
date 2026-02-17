from typing import Generic, TypeVar, List, Any
from math import ceil

from fastapi import Query
from pydantic import BaseModel, ConfigDict

from sqlalchemy import select, func
from sqlalchemy.sql import Select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import DEFAULT_PAGE, DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    total: int
    page: int
    page_size: int
    total_pages: int
    has_next: bool
    has_previous: bool
    items: List[T]

    model_config = ConfigDict(from_attributes=True)


class Paginator(Generic[T]):

    def __init__(
        self,
        page: int = Query(
            DEFAULT_PAGE,
            ge=1,
            description="Page number (starts from 1)",
        ),
        page_size: int = Query(
            DEFAULT_PAGE_SIZE,
            ge=1,
            le=MAX_PAGE_SIZE,
            description="Number of items per page",
        ),
    ):
        self.page = page
        self.page_size = page_size

    def get_offset(self) -> int:
        return (self.page - 1) * self.page_size

    def get_limit(self) -> int:
        return self.page_size

    async def paginate(
        self,
        session: AsyncSession,
        query: Select,
    ) -> Page[T]:

        count_stmt = select(func.count()).select_from(query.alias())
        total_result = await session.execute(count_stmt)
        total = total_result.scalar_one()

        paginated_query = query.offset(self.get_offset()).limit(self.get_limit())
        result = await session.execute(paginated_query)
        items = list(result.scalars().all())

        total_pages = ceil(total / self.page_size) if total > 0 else 1

        return Page(
            items=items,
            total=total,
            page=self.page,
            page_size=self.page_size,
            total_pages=total_pages,
            has_next=self.page < total_pages,
            has_previous=self.page > 1,
        )
