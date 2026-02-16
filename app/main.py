from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    await get_redis()
    yield
    await close_redis()


app = FastAPI(
    title="FastBank API",
    description="FastAPI Banking Project with WebSocket Support",
    version="1.0.0",
    lifespan=lifespan,
)

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


@app.get("/")
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


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "FastBank API"}
