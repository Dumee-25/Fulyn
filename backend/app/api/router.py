from fastapi import APIRouter

from app.api.routes import (
    analytics,
    caffeine,
    chat,
    expenses,
    health,
    journal,
    memories,
    moods,
    people,
    planning,
    reports,
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
    reports.events_router,
    reports.timeline_router,
    reports.reports_router,
    analytics.router,
):
    api_router.include_router(router)
