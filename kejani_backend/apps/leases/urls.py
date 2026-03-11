from django.urls import path
from . import views

app_name = 'leases'

urlpatterns = [
    path('',              views.LandlordLeaseListView.as_view(), name='lease_list'),
    path('expiring/',     views.ExpiringLeasesView.as_view(),    name='expiring'),
    path('<int:pk>/',     views.LeaseDetailView.as_view(),       name='lease_detail'),
    path('<int:pk>/renew/', views.LeaseRenewView.as_view(),      name='lease_renew'),
]
