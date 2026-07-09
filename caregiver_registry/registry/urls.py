from django.urls import path
from . import views
from accounts.views import organization_signup

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

    path(
        "signup/organization/",
        organization_signup,
        name="organization_signup"
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
        "registry/network/",
        views.registry_network,
        name="registry_network"
    ),

    path(
        "dashboard/org/",
        views.org_dashboard,
        name="org_dashboard"
    ),
    path(
        "dashboard/org/caregivers/<int:pk>/",
        views.caregiver_detail,
        name="caregiver_detail"
    ),

    path(
        "dashboard/org/clients/<int:pk>/",
        views.client_detail,
        name="client_detail"
    ),

    path(
        "dashboard/org/caregivers/<int:pk>/<str:status>/",
        views.update_caregiver_status,
        name="update_caregiver_status"
    ),

    path(
        "dashboard/org/clients/<int:pk>/<str:status>/",
        views.update_client_status,
        name="update_client_status"
    ),

    # Profile-based status update routes (create org relationship if needed)
    path(
        "dashboard/org/caregivers/profile/<int:profile_id>/<str:status>/",
        views.update_caregiver_status_by_profile,
        name="update_caregiver_profile_status"
    ),

    path(
        "dashboard/org/clients/profile/<int:profile_id>/<str:status>/",
        views.update_client_status_by_profile,
        name="update_client_profile_status"
    ),

    path(
        "switch-organization/<int:org_id>/",
        views.switch_organization,
        name="switch_organization"
    ),
    
    # Support Coordinator URLs
    path(
        "coordinator/dashboard/",
        views.coordinator_dashboard,
        name="coordinator_dashboard"
    ),
    
    path(
        "coordinator/signup/<uuid:token>/",
        views.coordinator_signup,
        name="coordinator_signup"
    ),
    
    path(
        "coordinator/invite/",
        views.coordinator_invite_send,
        name="coordinator_invite_send"
    ),
    
    path(
        "coordinator/permissions/<int:relationship_id>/",
        views.coordinator_permissions_update,
        name="coordinator_permissions_update"
    ),
    
    # Pool Browsing URLs
    path(
        "pool/caregivers/",
        views.caregiver_pool,
        name="caregiver_pool"
    ),
    
    path(
        "pool/clients/",
        views.client_pool,
        name="client_pool"
    ),
    
    path(
        "pool/caregivers/add/<int:profile_id>/",
        views.add_caregiver_to_org,
        name="add_caregiver_to_org"
    ),
    
    path(
        "pool/clients/add/<int:profile_id>/",
        views.add_client_to_org,
        name="add_client_to_org"
    ),

    # ── Scheduling URLs ───────────────────────────────────────────────────────
    path(
        "schedules/",
        views.schedule_list,
        name="schedule_list",
    ),
    path(
        "schedules/create/",
        views.schedule_create,
        name="schedule_create",
    ),
    path(
        "schedules/<int:pk>/",
        views.schedule_detail,
        name="schedule_detail",
    ),
    path(
        "schedules/<int:pk>/edit/",
        views.schedule_edit,
        name="schedule_edit",
    ),
    path(
        "schedules/<int:pk>/submit/",
        views.schedule_submit,
        name="schedule_submit",
    ),
    path(
        "schedules/<int:pk>/cancel/",
        views.schedule_cancel,
        name="schedule_cancel",
    ),
    path(
        "schedule-entries/<int:entry_pk>/caregiver/<str:action>/",
        views.schedule_entry_caregiver_respond,
        name="schedule_entry_caregiver_respond",
    ),
    path(
        "schedule-entries/<int:entry_pk>/support/<str:action>/",
        views.schedule_entry_support_respond,
        name="schedule_entry_support_respond",
    ),
]
