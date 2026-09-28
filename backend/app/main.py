import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError

from app.api.routes import auth, inventory, items, system, users, traceability, documents
from app.context import request_id_var
from app.core.config import get_settings
from app.core.errors import DomainError
from app.core.logging import configure_logging, log
from app.db import current_schema_revision, new_session
from app.version import EXPECTED_SCHEMA_REVISION


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
    st = get_settings()
    configure_logging(st.log_level)
    if not st.skip_schema_check:
        with new_session() as db:
            rev = current_schema_revision(db)
        if rev != EXPECTED_SCHEMA_REVISION:
            log.error("schema_mismatch", found=rev, expected=EXPECTED_SCHEMA_REVISION)
            raise RuntimeError(f"Database schema {rev!r} does not match expected {EXPECTED_SCHEMA_REVISION!r}. "
                               "Run migrations with the release that matches this database.")
    log.info("startup", version=st.app_version, commit=st.git_commit, schema=EXPECTED_SCHEMA_REVISION)
    yield


def create_app() -> FastAPI:
    st = get_settings()
    app = FastAPI(title="PLM API", version=st.app_version, lifespan=lifespan,
                  docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None)

    @app.middleware("http")
    async def request_context(request: Request, call_next):  # type: ignore[no-untyped-def]
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        request_id_var.set(rid[:64])
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid[:64]
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault("Cache-Control", "no-store")
        return response

    @app.exception_handler(DomainError)
    async def domain_error(_: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse({"detail": exc.message, "code": exc.code}, status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        msgs = []
        for e in exc.errors():
            loc = ".".join(str(x) for x in e.get("loc", []) if x != "body")
            msgs.append(f"{loc}: {e.get('msg')}" if loc else str(e.get("msg")))
        return JSONResponse({"detail": "; ".join(msgs), "code": "validation", "errors": exc.errors()},
                            status_code=422)

    @app.exception_handler(DBAPIError)
    async def db_error(_: Request, exc: DBAPIError) -> JSONResponse:
        # Database-level integrity controls (triggers/constraints) are the last line of defence.
        msg = str(getattr(exc.orig, "diag", None) and exc.orig.diag.message_primary or "")  # type: ignore[union-attr]
        log.warning("db_rejected", error=msg or str(exc.orig)[:300])
        if msg.startswith("PLM:"):
            return JSONResponse({"detail": msg, "code": "integrity_control"}, status_code=409)
        return JSONResponse({"detail": "The database rejected the operation (integrity constraint).",
                             "code": "integrity_constraint"}, status_code=409)

    for r in (auth.router, users.router, items.router, inventory.router, traceability.router, documents.router, system.router):
        app.include_router(r)
    return app


app = create_app()
