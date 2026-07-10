from django.urls import path
from . import views
from accounts.views import organization_signup, staff_invite_send, staff_signup

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
        "schedules/<int:pk>/delete/",
        views.schedule_delete,
        name="schedule_delete",
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
    path(
        "schedule-entries/<int:entry_pk>/rate/",
        views.schedule_entry_rate,
        name="schedule_entry_rate",
    ),
    path(
        "dashboard/org/caregivers/<int:pk>/ratings/",
        views.caregiver_ratings_detail,
        name="caregiver_ratings_detail",
    ),
    path(
        "dashboard/org/clients/<int:pk>/ratings/",
        views.client_ratings_detail,
        name="client_ratings_detail",
    ),

    # ── Self-Service Profile Pages ────────────────────────────────────────────
    path("profile/caregiver/",                        views.caregiver_profile_view,             name="caregiver_profile"),
    path("profile/caregiver/edit/identity/",          views.caregiver_profile_edit_identity,    name="caregiver_profile_edit_identity"),
    path("profile/caregiver/edit/location/",          views.caregiver_profile_edit_location,    name="caregiver_profile_edit_location"),
    path("profile/caregiver/edit/availability/",      views.caregiver_profile_edit_availability,name="caregiver_profile_edit_availability"),
    path("profile/caregiver/edit/experience/",        views.caregiver_profile_edit_experience,  name="caregiver_profile_edit_experience"),
    path("profile/caregiver/edit/notes/",             views.caregiver_profile_edit_notes,       name="caregiver_profile_edit_notes"),

    path("profile/client/",                           views.client_profile_view,                name="client_profile"),
    path("profile/client/edit/identity/",             views.client_profile_edit_identity,       name="client_profile_edit_identity"),
    path("profile/client/edit/programs/",             views.client_profile_edit_programs,       name="client_profile_edit_programs"),
    path("profile/client/edit/availability/",         views.client_profile_edit_availability,   name="client_profile_edit_availability"),
    path("profile/client/edit/care-needs/",           views.client_profile_edit_care_needs,     name="client_profile_edit_care_needs"),

    path("profile/coordinator/",                      views.coordinator_profile_view,           name="coordinator_profile"),
    path("profile/coordinator/edit/identity/",        views.coordinator_profile_edit_identity,  name="coordinator_profile_edit_identity"),
    path("profile/coordinator/edit/info/",            views.coordinator_profile_edit_info,      name="coordinator_profile_edit_info"),

    # ── Staff Invite URLs ─────────────────────────────────────────────────────
    path(
        "dashboard/org/staff/invite/",
        staff_invite_send,
        name="staff_invite_send",
    ),
    path(
        "staff/signup/<uuid:token>/",
        staff_signup,
        name="staff_signup",
    ),
]
