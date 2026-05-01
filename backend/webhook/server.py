from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from webhook.api_routes import router as api_router
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)

@app.get("/health")
async def health():
    return {"status": "ok"}
