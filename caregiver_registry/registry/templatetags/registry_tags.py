"""
Template tags for registry app.
Provides organization-related context to templates.
"""
from django import template
from registry.services import get_user_memberships, get_active_organization

register = template.Library()


@register.simple_tag
def get_user_organizations(user):
    """
    Get all organization memberships for a user.
    Usage: {% get_user_organizations user as user_organizations %}
    """
    if not user.is_authenticated:
        return []
    
    return get_user_memberships(user)


@register.simple_tag
def get_current_organization(request):
    """
    Get the currently active organization from session.
    Usage: {% get_current_organization request as current_org %}
    """
    return get_active_organization(request)
