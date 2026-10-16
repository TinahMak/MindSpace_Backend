from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from wellness.models import MoodEntry

from .forms import ChatMessageForm
from .models import Conversation, Message
from .services import SOUTH_AFRICA_CRISIS_LINE, detect_crisis, get_ai_reply, get_mood_suggestion


def _get_or_create_active_conversation(user):
    conversation = Conversation.objects.filter(user=user).order_by("-updated_at").first()
    if conversation is None:
        conversation = Conversation.objects.create(user=user)
    return conversation


@login_required
def chat_view(request, conversation_id=None):
    if conversation_id:
        conversation = get_object_or_404(Conversation, pk=conversation_id, user=request.user)
    else:
        conversation = _get_or_create_active_conversation(request.user)

    error = None
    ai_error = None

    if request.method == "POST":
        form = ChatMessageForm(request.POST, request.FILES)
        if form.is_valid():
            content = form.cleaned_data["content"].strip()
            image = form.cleaned_data.get("image")
            is_crisis = detect_crisis(content)

            user_message = Message.objects.create(
                conversation=conversation,
                role="user",
                content=content,
                image=image,
                is_crisis=is_crisis,
            )
            conversation.save(update_fields=["updated_at"])

            try:
                reply_text = get_ai_reply(conversation)
                assistant_message = Message.objects.create(
                    conversation=conversation, role="assistant", content=reply_text
                )
                if user_message.image:
                    suggestion = get_mood_suggestion(user_message)
                    if suggestion:
                        assistant_message.suggested_mood = suggestion["mood"]
                        assistant_message.suggested_emotions = suggestion["emotions"]
                        assistant_message.save(update_fields=["suggested_mood", "suggested_emotions"])
            except Exception:
                ai_error = (
                    "Sorry — I couldn't reach the AI companion just now. "
                    "Your message was saved; please try again in a moment."
                )

            if ai_error:
                request.session["chat_ai_error"] = ai_error
            return redirect("chat", conversation_id=conversation.pk)
        else:
            error = form.errors.get("__all__")
    else:
        form = ChatMessageForm()

    ai_error = request.session.pop("chat_ai_error", None)

    context = {
        "conversation": conversation,
        "messages": conversation.messages.order_by("created_at"),
        "form": form,
        "error": error,
        "ai_error": ai_error,
        "show_crisis_banner": conversation.has_crisis_flag,
        "crisis_line": SOUTH_AFRICA_CRISIS_LINE,
        "conversations": Conversation.objects.filter(user=request.user).order_by("-updated_at")[:10],
        "mood_emoji": MoodEntry.MOOD_EMOJI,
        "mood_labels": dict(MoodEntry.MOOD_CHOICES),
    }
    return render(request, "aichat/chat.html", context)


@login_required
def new_conversation_view(request):
    if request.method == "POST":
        conversation = Conversation.objects.create(user=request.user)
        return redirect("chat", conversation_id=conversation.pk)
    return redirect("chat")


@login_required
def log_suggested_mood_view(request, message_id):
    message = get_object_or_404(
        Message, pk=message_id, conversation__user=request.user, role="assistant"
    )
    if request.method == "POST" and message.suggested_mood and not message.mood_logged:
        MoodEntry.objects.create(
            user=request.user,
            date=timezone.localdate(),
            mood=message.suggested_mood,
            emotions=message.suggested_emotions,
            note="Logged from a photo shared in AI chat.",
        )
        message.mood_logged = True
        message.save(update_fields=["mood_logged"])
    return redirect("chat", conversation_id=message.conversation_id)
