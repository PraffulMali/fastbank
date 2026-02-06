from fastapi import FastAPI
from app.routers import auth

app = FastAPI(
    title="FastBank API",
    description="FastAPI Intern Project",
    version="1.0.0"
)

app.include_router(auth.router)

@app.get("/")
async def root():
    return {"message": "Welcome to FastBank API"}
