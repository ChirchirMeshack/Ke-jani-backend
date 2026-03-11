from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.http import JsonResponse
from django.db import connection
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)


def health_check(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return JsonResponse({"status": "ok", "database": "ok"}, status=200)
    except Exception as e:
        return JsonResponse({"status": "error", "database": str(e)}, status=500)


urlpatterns = [
    # Admin
    path('admin/', admin.site.urls),

    # API Schema & Docs
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),

    # Auth
    path('api/auth/', include('apps.users.urls')),

    # Banking
    path('api/banking/', include('apps.banking.urls')),

    # Landlords
    path('api/landlords/', include('apps.landlords.urls')),

    # Properties
    path('api/properties/', include('apps.properties.urls', namespace='properties')),

    # Leases
    path('api/leases/', include('apps.leases.urls', namespace='leases')),

    # Tenants
    path('api/tenants/', include('apps.tenants.urls', namespace='tenants')),

    # Health
    path('api/health/', health_check),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
