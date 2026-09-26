from fastapi import APIRouter

from app.api.routes import (
    caffeine,
    chat,
    expenses,
    health,
    journal,
    memories,
    moods,
    people,
    planning,
    sleep,
)

api_router = APIRouter(prefix="/api")
for router in (
    health.router,
    chat.router,
    journal.router,
    expenses.router,
    moods.router,
    sleep.router,
    caffeine.router,
    memories.router,
    people.people_router,
    people.interactions_router,
    people.music_router,
    planning.subscriptions_router,
    planning.reminders_router,
    planning.decisions_router,
    planning.waiting_router,
):
    api_router.include_router(router)
