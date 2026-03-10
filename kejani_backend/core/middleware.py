import json

from django.http import JsonResponse
from rest_framework_simplejwt.authentication import JWTAuthentication


class DemoAccountGuard:
    """
    Middleware that intercepts non-safe HTTP methods from demo users
    (is_demo=True) and blocks everything except logout and token refresh.
    """

    ALLOWED_PATHS = (
        '/api/auth/logout/',
        '/api/auth/token/refresh/',
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method in ('POST', 'PUT', 'PATCH', 'DELETE') and request.path not in self.ALLOWED_PATHS:
            user = None
            
            # Check if Django Auth Middleware populated request.user (e.g. session auth)
            if hasattr(request, 'user') and request.user.is_authenticated:
                user = request.user
            else:
                # DRF JWT Authentication — manually decode the token
                try:
                    auth_result = JWTAuthentication().authenticate(request)
                    if auth_result:
                        user, _ = auth_result
                except Exception:
                    pass
            
            if user and getattr(user, 'is_demo', False):
                return JsonResponse(
                    {
                        'error': 'demo_restricted',
                        'message': (
                            'This action is not available in demo mode. '
                            'Create a free account to use all features.'
                        ),
                        'cta': 'Create a free account',
                        'cta_url': '/register',
                    },
                    status=403,
                )

        return self.get_response(request)
