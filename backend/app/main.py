import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from app.db import connect, init_schema
from app.investigations import router


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    with connect() as connection:
        init_schema(connection)
    yield


def create_app() -> FastAPI:
    application = FastAPI(title="Forge", lifespan=lifespan)
    application.include_router(router)
    return application


app = create_app()


def run() -> None:
    host = os.environ.get("FORGE_HOST", "").strip()
    port_text = os.environ.get("FORGE_PORT", "").strip()
    if not host or not port_text:
        raise SystemExit("Defina FORGE_HOST e FORGE_PORT no ambiente.")
    uvicorn.run("app.main:app", host=host, port=int(port_text))
