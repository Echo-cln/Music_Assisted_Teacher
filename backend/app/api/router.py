from fastapi import APIRouter

from app.api.routes import ai_engine, audio, auth, classes, feedback, generation_jobs, health, lessons, resources, songs

api_router = APIRouter(prefix="/api")
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(songs.router)
api_router.include_router(resources.router)
api_router.include_router(classes.router)
api_router.include_router(lessons.router)
api_router.include_router(generation_jobs.router)
api_router.include_router(audio.router)
api_router.include_router(feedback.router)
api_router.include_router(ai_engine.router)
