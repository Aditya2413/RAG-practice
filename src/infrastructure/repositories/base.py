from abc import ABC, abstractmethod
from typing import Generic, TypeVar
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

T = TypeVar("T")


class IRepository(ABC, Generic[T]):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @abstractmethod
    async def find_by_id(self, id: UUID) -> T | None: ...

    @abstractmethod
    async def create(self, data: dict) -> T: ...

    @abstractmethod
    async def update(self, id: UUID, data: dict) -> T: ...

    @abstractmethod
    async def delete(self, id: UUID) -> None: ...
