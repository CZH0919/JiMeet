from django.urls import path

from apps.chat import views

urlpatterns = [
    path("users/<str:uid>", views.PeerProfileView.as_view(), name="chat-peer-profile"),
    path("chat/conversations", views.ConversationListView.as_view(), name="chat-conversations"),
    path("chat/conversations/unread-count", views.ChatUnreadCountView.as_view(), name="chat-unread-count"),
    path("chat/conversations/<int:conversation_id>/messages", views.MessageListView.as_view(), name="chat-messages"),
    path("chat/conversations/<int:conversation_id>/read", views.ReadMessagesView.as_view(), name="chat-read"),
]
