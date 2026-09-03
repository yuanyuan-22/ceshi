from django.urls import path
from .views import QAView, AgentView, ask_rag_view, qa_stream_view

urlpatterns = [
    path("", QAView.as_view(), name="qa"),
    path("agent/", AgentView.as_view(), name="qa_agent"),
    path("ask_rag/", ask_rag_view, name="ask_rag_legacy"),
    path("stream/", qa_stream_view, name="qa_stream"),
]
