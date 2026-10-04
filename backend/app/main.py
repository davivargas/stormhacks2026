"""FastAPI app factory. Run with: uvicorn app.main:app --reload (from backend/)."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from app import config, db
from app.routes import ApiError, router
from app.sim import snapshot
from app.schemas import ErrorResponse


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_pool()  # returns False and carries on when Tiger is unreachable
    snapshot.warm_up()  # open the Copernicus dataset in the background
    yield
    db.close_pool()


def create_app() -> FastAPI:
    app = FastAPI(title="PlasticPaths simulation API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        body = ErrorResponse(code=exc.code, message=exc.message, placement_id=exc.placement_id)
        return JSONResponse(status_code=exc.status, content=body.model_dump(by_alias=True, exclude_none=True))

    @app.exception_handler(RequestValidationError)
    async def _invalid(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = exc.errors()
        first = errors[0] if errors else {}
        where = ".".join(str(p) for p in first.get("loc", ()) if p != "body")
        message = f"{where}: {first.get('msg', 'invalid request')}" if where else first.get("msg", "invalid request")
        return JSONResponse(
            status_code=422,
            content={"code": "invalid_request", "message": message, "details": jsonable_errors(errors)},
        )

    app.include_router(router)
    return app


def jsonable_errors(errors: list[dict]) -> list[dict]:
    return [{"loc": list(e.get("loc", ())), "msg": e.get("msg", "")} for e in errors]


app = create_app()
