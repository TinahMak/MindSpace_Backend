from django.urls import path

from adminpanel import api as admin_api
from professionals import api as pro_api
from professionals import consult_api
from selfcare import api as selfcare_api

from . import views

urlpatterns = [
    path("health/", views.health_view),
    path("meta/", views.meta_view),
    # auth
    path("auth/signup/", views.signup_view),
    path("auth/login/", views.login_view),
    path("auth/logout/", views.logout_view),
    path("auth/password-reset/", views.password_reset_view),
    path("auth/resend-verification/", views.resend_verification_view),
    # account
    path("me/", views.me_view),
    path("me/export/", views.export_view),
    path("me/delete/", views.delete_account_view),
    # mood
    path("dashboard/", views.dashboard_view),
    path("moods/", views.moods_view),
    path("moods/<int:pk>/", views.mood_detail_view),
    # insights
    path("insights/", views.insights_view),
    path("insights/report.pdf", views.report_pdf_view),
    path("insights/weekly/", views.weekly_insights_view),
    path("insights/weekly/generate/", views.weekly_generate_view),
    # chat
    path("chat/current/", views.current_conversation_view),
    path("chat/conversations/", views.conversations_view),
    path("chat/conversations/<int:pk>/", views.conversation_detail_view),
    path("chat/conversations/<int:pk>/messages/", views.send_message_view),
    path("chat/messages/<int:pk>/log-mood/", views.log_suggested_mood_view),
    # help
    path("help/", views.help_view),
    # app rating (any signed-in user)
    path("rating/", admin_api.my_rating_view),
    # admin (admins only)
    path("admin/stats/", admin_api.stats_view),
    path("admin/users/", admin_api.users_view),
    path("admin/users/<int:pk>/", admin_api.user_detail_view),
    path("admin/users/<int:pk>/<str:action>/", admin_api.user_action_view),
    path("admin/admins/", admin_api.admins_view),
    path("admin/ratings/", admin_api.ratings_view),
    path("admin/audit/", admin_api.audit_view),
    path("admin/backup/", admin_api.backup_view),
    path("admin/reports/<str:kind>/preview/", admin_api.report_preview_view),
    path("admin/reports/<str:kind>.<str:fmt>", admin_api.report_file_view),
    # professionals: their own area
    path("pro/meta/", pro_api.pro_meta_view),
    path("pro/signup/", pro_api.pro_signup_view),
    path("pro/me/", pro_api.pro_me_view),
    path("pro/me/resubmit/", pro_api.pro_resubmit_view),
    path("pro/documents/", pro_api.pro_upload_view),
    path("pro/documents/<int:pk>/", pro_api.pro_document_delete_view),
    path("documents/<int:pk>/file/", pro_api.document_file_view),
    # professionals: finding support (clients)
    path("support/match/", pro_api.match_view),
    path("support/<int:pk>/", pro_api.public_profile_view),
    # self-care tools
    path("selfcare/meta/", selfcare_api.selfcare_meta_view),
    path("journal/", selfcare_api.journal_view),
    path("journal/<int:pk>/", selfcare_api.journal_entry_view),
    path("safety-plan/", selfcare_api.safety_plan_view),
    # consultations (Phase 4)
    path("consultations/", consult_api.client_requests_view),
    path("consultations/<int:pk>/", consult_api.client_request_detail_view),
    path("consultations/<int:pk>/<str:action>/", consult_api.client_request_action_view),
    path("pro/consultations/", consult_api.pro_requests_view),
    path("pro/consultations/<int:pk>/", consult_api.pro_request_detail_view),
    path("pro/consultations/<int:pk>/<str:action>/", consult_api.pro_request_action_view),
    # professionals: admin review
    path("admin/professionals/", pro_api.admin_pros_view),
    path("admin/professionals/<int:pk>/", pro_api.admin_pro_detail_view),
    path("admin/professionals/<int:pk>/<str:action>/", pro_api.admin_pro_action_view),
]
