from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import auth as auth_routes
from app.api.routes import search as search_routes
from app.api.routes import sessions as sessions_routes
from app.config import settings

app = FastAPI(title="Test Chatbot API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.CORS_ORIGINS.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_routes.router)
app.include_router(sessions_routes.router)
app.include_router(search_routes.router)


@app.get("/health")
def health():
    return {"ok": True}
