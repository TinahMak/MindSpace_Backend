from django.urls import path

from . import views

urlpatterns = [
    path("", views.chat_view, name="chat"),
    path("<int:conversation_id>/", views.chat_view, name="chat"),
    path("new/", views.new_conversation_view, name="chat_new"),
    path("log-mood/<int:message_id>/", views.log_suggested_mood_view, name="chat_log_mood"),
]
