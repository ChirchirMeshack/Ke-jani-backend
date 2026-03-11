from django.urls import path
from .views import MySubscriptionView, AvailablePlansView

app_name = 'subscriptions'

urlpatterns = [
    path('my-subscription/', MySubscriptionView.as_view(), name='my-subscription'),
    path('plans/', AvailablePlansView.as_view(), name='available-plans'),
]
