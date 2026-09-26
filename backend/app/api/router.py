from fastapi import APIRouter

from app.api.routes import caffeine, chat, expenses, health, journal, memories, moods, sleep

api_router = APIRouter(prefix="/api")
for module in (health, chat, journal, expenses, moods, sleep, caffeine, memories):
    api_router.include_router(module.router)
