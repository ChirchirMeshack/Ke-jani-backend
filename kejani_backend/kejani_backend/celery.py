"""
Celery application configuration for KE-JANI.
"""
import os

from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'kejani_backend.settings')

app = Celery('kejani_backend')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()
