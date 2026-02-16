from celery import Celery
from app.config.settings import settings
from app.celery.schedules import beat_schedule

celery_app = Celery(
    "fastbank",
    broker=f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}",
    backend=f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}",
)

celery_app.conf.update(
    timezone="UTC",
    enable_utc=True,
    broker_connection_retry_on_startup=True,
    beat_schedule=beat_schedule,   
)

celery_app.autodiscover_tasks(["app.celery"])

import app.celery.tasks   
