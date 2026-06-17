import uuid
from pydantic import BaseModel


class GapCell(BaseModel):
    category: str
    client_visibility: float | None = None
    top_competitor_visibility: float | None = None
    top_competitor_name: str | None = None
    competitors_winning: bool = False


class GapMatrixRow(BaseModel):
    client_id: uuid.UUID
    client_name: str
    cells: list[GapCell] = []


class GapMatrixResponse(BaseModel):
    categories: list[str] = []
    rows: list[GapMatrixRow] = []
