from django.urls import path
from . import views

app_name = 'banking'

urlpatterns = [
    path('mpesa/',                      views.MpesaAccountListCreateView.as_view(), name='mpesa_list'),
    path('mpesa/<int:pk>/',              views.MpesaAccountDetailView.as_view(),     name='mpesa_detail'),
    path('mpesa/<int:pk>/set-primary/',  views.SetPrimaryMpesaView.as_view(),        name='mpesa_set_primary'),
    path('bank/',                        views.BankAccountListCreateView.as_view(),  name='bank_list'),
    path('bank/<int:pk>/',               views.BankAccountDetailView.as_view(),      name='bank_detail'),
]
