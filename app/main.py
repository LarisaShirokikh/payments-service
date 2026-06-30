import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import router
from app.broker import broker, declare_topology
from app.outbox import outbox_relay_loop

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await broker.connect()
    await declare_topology()
    relay_task = asyncio.create_task(outbox_relay_loop())
    try:
        yield
    finally:
        relay_task.cancel()
        await broker.close()


app = FastAPI(title="Payments Processing Service", version="1.0.0", lifespan=lifespan)
app.include_router(router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
