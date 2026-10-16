from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User


class UserAdmin(BaseUserAdmin):
    model = User
    list_display = ("email", "first_name", "last_name", "is_staff", "date_joined")
    ordering = ("-date_joined",)
    fieldsets = BaseUserAdmin.fieldsets + (
        ("MindSpace profile", {
            "fields": ("date_of_birth", "phone", "focus", "marketing_opt_in", "terms_accepted_at"),
        }),
    )


admin.site.register(User, UserAdmin)
