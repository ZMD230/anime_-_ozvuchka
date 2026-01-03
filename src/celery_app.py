import os
from celery import Celery

broker = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0")
backend = os.getenv("CELERY_RESULT_BACKEND", broker)

celery_app = Celery("anime", broker=broker, backend=backend)
celery_app.conf.update(task_track_started=True)
