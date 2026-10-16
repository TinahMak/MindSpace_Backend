from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("signup/", views.signup_view, name="signup"),
    path("login/", views.EmailLoginView.as_view(), name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("dashboard/", views.dashboard_view, name="dashboard"),

    # ── Account settings / trust & privacy ──────────────────────
    path("settings/", views.account_settings_view, name="account_settings"),
    path("settings/export-data/", views.export_data_view, name="export_data"),
    path("settings/delete-account/", views.delete_account_view, name="delete_account"),

    # ── Email verification ──────────────────────────────────────
    path("verify-email/<uidb64>/<token>/", views.verify_email_view, name="verify_email"),
    path("verify-email/resend/", views.resend_verification_view, name="resend_verification"),

    # ── Password reset ────────────────────────────────────────
    path(
        "password-reset/",
        auth_views.PasswordResetView.as_view(
            template_name="accounts/password_reset.html",
            email_template_name="accounts/password_reset_email.html",
            subject_template_name="accounts/password_reset_subject.txt",
            success_url="/accounts/password-reset/done/",
        ),
        name="password_reset",
    ),
    path(
        "password-reset/done/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="accounts/password_reset_done.html"
        ),
        name="password_reset_done",
    ),
    path(
        "reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="accounts/password_reset_confirm.html",
            success_url="/accounts/reset/done/",
        ),
        name="password_reset_confirm",
    ),
    path(
        "reset/done/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="accounts/password_reset_complete.html"
        ),
        name="password_reset_complete",
    ),
]
