from django.conf import settings
from django.conf.urls.static import static

from django.contrib import admin
from django.urls import include, path
from django.http import JsonResponse
from django.db import connection
from drf_spectacular.views import (SpectacularAPIView, SpectacularRedocView,
                                   SpectacularSwaggerView)

def health_check(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return JsonResponse({"status": "ok", "database": "ok"}, status=200)
    except Exception as e:
        return JsonResponse({"status": "error", "database": str(e)}, status=500)


urlpatterns = [
    # Schema
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    # Swagger UI
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    # Redoc (optional)
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
    # path("admin/", custom_admin_site.urls),
    # path("api/payment/", include("payment.urls")),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
    
    # path('api/waitlist', include('waitlist.urls')),
    # path('api/', include('user.urls')),

    # path('api/common/', include('common.urls')),
    # path('api/', include('fundraiser.urls')),
    # path('dashboard/', include('dashboard.urls')),
    # path('', include('django_prometheus.urls')),
    path('api/health/', health_check),
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL,document_root=settings.MEDIA_URL)
    

