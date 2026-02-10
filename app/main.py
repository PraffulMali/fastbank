from fastapi import FastAPI
from app.routers import auth, tenant, user, account, transaction

app = FastAPI(
    title="FastBank API",
    description="FastAPI Project",
    version="1.0.0"
)

app.include_router(auth.router)
app.include_router(tenant.router)
app.include_router(user.router)
app.include_router(account.router)
app.include_router(transaction.router)

@app.get("/")
async def root():
    return {"message": "Welcome to FastBank API"}
