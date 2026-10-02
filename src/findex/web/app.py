from __future__ import annotations

import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from .config import Settings, get_settings
from .models import (
    DocumentResponse,
    HealthResponse,
    SearchParams,
    SearchResponse,
    StatsResponse,
)
from .service import WebSearch

log = logging.getLogger("findex.web")
templates = Jinja2Templates(directory=str(Path(__file__).with_name("templates")))


def get_service(request: Request) -> WebSearch:
    loaded = getattr(request.app.state, "web_search", None)
    if loaded is None:
        raise HTTPException(status_code=503, detail="Index is not loaded")
    return loaded


def get_optional_service(request: Request) -> WebSearch | None:
    return getattr(request.app.state, "web_search", None)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = app.state.settings
    app.state.web_search = None
    try:
        app.state.web_search = await asyncio.to_thread(
            WebSearch.load, settings.index_path, settings.docs_path
        )
        log.info("index loaded from %s", settings.index_path)
    except Exception as exc:
        app.state.index_error = str(exc)
        log.error("index load failed: %s", exc)
    yield


def create_app(settings: Settings | None = None) -> FastAPI:
    cfg = settings or get_settings()
    app = FastAPI(title="findex", version="0.7.0", lifespan=lifespan)
    app.state.settings = cfg
    app.state.web_search = None
    app.state.index_error = None

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        request.state.request_id = request_id
        try:
            response = await call_next(request)
        except Exception:
            log.exception("request_id=%s unhandled exception", request_id)
            response = JSONResponse(
                status_code=500,
                content={
                    "detail": "Internal server error",
                    "request_id": request_id,
                },
            )
        response.headers["X-Request-ID"] = request_id
        return response

    async def search_impl(
        params: SearchParams, svc: WebSearch
    ) -> SearchResponse:
        results, total, pages = await asyncio.to_thread(
            svc.search, params.q, params.k, params.scorer, params.page
        )
        return SearchResponse(
            query=params.q,
            scorer=params.scorer,
            page=params.page,
            page_size=params.k,
            total=total,
            pages=pages,
            results=results,
        )

    @app.get("/", response_class=HTMLResponse)
    async def index_page(request: Request):
        q = request.query_params.get("q", "")
        try:
            k = int(request.query_params.get("k", "10"))
            page = int(request.query_params.get("page", "1"))
        except ValueError:
            k, page = 10, 1
        scorer = request.query_params.get("scorer", "bm25")
        data: dict[str, Any] = {
            "q": q,
            "k": k,
            "page": page,
            "scorer": scorer,
            "response": None,
            "error": None,
        }
        if q:
            try:
                validated = SearchParams(q=q, k=k, page=page, scorer=scorer)
                data["response"] = await search_impl(
                    validated, get_service(request)
                )
            except Exception as exc:
                data["error"] = str(exc)
        return templates.TemplateResponse(request, "index.html", data)

    @app.get("/search", response_model=SearchResponse)
    async def search_endpoint(
        params: SearchParams = Depends(),
        svc: WebSearch = Depends(get_service),
    ) -> SearchResponse:
        return await search_impl(params, svc)

    @app.get("/docs/{doc_id}", response_model=DocumentResponse)
    async def document_endpoint(
        doc_id: int, svc: WebSearch = Depends(get_service)
    ) -> DocumentResponse:
        doc = await asyncio.to_thread(svc.document, doc_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="Document not found")
        return DocumentResponse(doc_id=doc.doc_id, title=doc.title, text=doc.text)

    @app.get("/stats", response_model=StatsResponse)
    async def stats_endpoint(svc: WebSearch = Depends(get_service)) -> StatsResponse:
        return StatsResponse(**await asyncio.to_thread(svc.stats))

    @app.get("/health", response_model=HealthResponse)
    async def health_endpoint(
        svc: WebSearch | None = Depends(get_optional_service),
    ) -> HealthResponse:
        if svc is None:
            raise HTTPException(status_code=503, detail="Index is not loaded")
        return HealthResponse(status="ok")

    return app


app = create_app()
