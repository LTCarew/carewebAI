"""
Template tags for registry app.
Provides organization-related context to templates.
"""
from django import template
from registry.services import get_user_organizations, get_active_organization

register = template.Library()


@register.simple_tag
def get_organizations_for_user(user):
    """
    Get all organizations for a user.
    Usage: {% get_organizations_for_user user as user_organizations %}
    """
    if not user.is_authenticated:
        return []
    
    return get_user_organizations(user)


@register.simple_tag
def get_current_organization(request):
    """
    Get the currently active organization from session.
    Usage: {% get_current_organization request as current_org %}
    """
    return get_active_organization(request)
