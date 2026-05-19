from django.contrib import admin
from django.contrib.auth.views import LogoutView
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path("",include("registry.urls")),
    path("",include("django.contrib.auth.urls")),
    path(
        "logout/",
        LogoutView.as_view(),
        name="logout"
    ),
]
