from django.contrib import admin

from .models import AdminAction, AppRating


@admin.register(AppRating)
class AppRatingAdmin(admin.ModelAdmin):
    list_display = ("user", "stars", "platform", "updated_at")
    list_filter = ("stars", "platform")


@admin.register(AdminAction)
class AdminActionAdmin(admin.ModelAdmin):
    list_display = ("created_at", "actor_email", "action", "target_email")
    list_filter = ("action",)
    readonly_fields = [f.name for f in AdminAction._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
