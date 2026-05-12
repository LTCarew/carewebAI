from django.contrib import admin
from .models import Organization, OrganizationStaff, OrganizationStaffInvite


admin.site.register(Organization)
admin.site.register(OrganizationStaff)
admin.site.register(OrganizationStaffInvite)