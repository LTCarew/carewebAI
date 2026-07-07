from django.contrib import admin
from django.contrib.auth.views import LoginView, LogoutView
from django.urls import path, include

from accounts.forms import CareWebLoginForm

urlpatterns = [
    path('admin/', admin.site.urls),
    path("", include("registry.urls")),
    path("", include("matching.urls")),
    # Override the default login view to use our status-aware form
    path(
        "login/",
        LoginView.as_view(authentication_form=CareWebLoginForm),
        name="login",
    ),
    path("", include("django.contrib.auth.urls")),
    path(
        "logout/",
        LogoutView.as_view(),
        name="logout"
    ),
]
