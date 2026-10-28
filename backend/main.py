from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.api.routes import router
from backend.db import mongodb
from config.settings import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    mongodb.connect()
    yield
    mongodb.close()


app = FastAPI(title="Personalized Study Guide Generator", lifespan=lifespan)
app.include_router(router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host=settings.API_HOST, port=settings.API_PORT, reload=True)
