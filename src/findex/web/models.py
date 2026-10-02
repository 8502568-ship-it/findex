from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SearchParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    q: str = Field(min_length=1, max_length=200)
    k: int = Field(default=10, ge=1, le=100)
    scorer: Literal["bm25", "tfidf"] = "bm25"
    page: int = Field(default=1, ge=1, le=10000)


class SearchItem(BaseModel):
    doc_id: int
    title: str
    score: float
    snippet: str


class SearchResponse(BaseModel):
    query: str
    scorer: Literal["bm25", "tfidf"]
    page: int
    page_size: int
    total: int
    pages: int
    results: list[SearchItem]


class DocumentResponse(BaseModel):
    doc_id: int
    title: str
    text: str


class StatsResponse(BaseModel):
    documents: int
    terms: int
    average_document_length: float


class HealthResponse(BaseModel):
    status: Literal["ok"]
