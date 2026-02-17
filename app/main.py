from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi_limiter import FastAPILimiter
from fastapi_limiter.depends import RateLimiter
from app.constants import APP_NAME, RATE_LIMIT_TIMES, RATE_LIMIT_WINDOW_SECONDS
from app.routers import (
    auth,
    tenant,
    user,
    account,
    transaction,
    loan,
    account_type,
    loan_type,
    interest_rule,
)
from app.routers import websocket as ws_router
from app.routers import notification
from app.celery.app import celery_app
from app.database.redis import get_redis, close_redis
from contextlib import asynccontextmanager
from app.utils.logger import setup_logging
from app.middleware.logging import log_requests


@asynccontextmanager
async def lifespan(app: FastAPI):
    redis_client = await get_redis()
    await FastAPILimiter.init(redis_client)
    yield
    await close_redis()


setup_logging()

app = FastAPI(
    title=f"{APP_NAME} API",
    description="FastAPI Banking Project with WebSocket Support",
    version="1.0.0",
    lifespan=lifespan,
)

app.middleware("http")(log_requests)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(tenant.router)
app.include_router(user.router)
app.include_router(account.router)
app.include_router(transaction.router)
app.include_router(loan.router)
app.include_router(notification.router)
app.include_router(account_type.router)
app.include_router(loan_type.router)
app.include_router(interest_rule.router)

app.include_router(ws_router.router)


@app.get(
    "/",
    dependencies=[
        Depends(RateLimiter(times=RATE_LIMIT_TIMES, seconds=RATE_LIMIT_WINDOW_SECONDS))
    ],
)
async def root():
    return {
        "message": "Welcome to FastBank API",
        "version": "1.0.0",
        "features": [
            "REST API",
            "WebSocket Support",
            "Real-time Notifications",
            "Background Task Processing",
        ],
    }


@app.get(
    "/health",
    dependencies=[
        Depends(RateLimiter(times=RATE_LIMIT_TIMES, seconds=RATE_LIMIT_WINDOW_SECONDS))
    ],
)
async def health_check():
    return {"status": "healthy", "service": "FastBank API"}
