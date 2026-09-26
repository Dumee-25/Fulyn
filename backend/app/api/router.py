from fastapi import APIRouter

from app.api.routes import caffeine, chat, expenses, health, journal, moods, sleep

api_router = APIRouter(prefix="/api")
for module in (health, chat, journal, expenses, moods, sleep, caffeine):
    api_router.include_router(module.router)
