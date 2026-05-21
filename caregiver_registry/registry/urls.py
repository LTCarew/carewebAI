from django.urls import path
from . import views

urlpatterns = [

    path(
        "",
        views.home,
        name="home"
    ),

    path(
        "apply/caregiver/",
        views.caregiver_apply,
        name="caregiver_apply"
    ),

    path(
        "apply/client/",
        views.client_apply,
        name="client_apply"
    ),

    path(
        "apply/success/",
        views.application_success,
        name="application_success"
    ),

    path("dashboard/", 
        views.dashboard_redirect, 
        name="dashboard_redirect"
    ),

    path(
        "dashboard/caregiver/",
        views.caregiver_dashboard,
        name="caregiver_dashboard"
    ),

    path(
        "dashboard/client/",
        views.client_dashboard,
        name="client_dashboard"
    ),

    path(
        "dashboard/admin/",
        views.admin_dashboard,
        name="admin_dashboard"
    ),
    path(
        "dashboard/admin/caregivers/<int:pk>/",
        views.caregiver_detail,
        name="caregiver_detail"
    ),

    path(
        "dashboard/admin/clients/<int:pk>/",
        views.client_detail,
        name="client_detail"
    ),

    path(
        "dashboard/admin/caregivers/<int:pk>/<str:status>/",
        views.update_caregiver_status,
        name="update_caregiver_status"
    ),

    path(
        "dashboard/admin/clients/<int:pk>/<str:status>/",
        views.update_client_status,
        name="update_client_status"
    ),
]