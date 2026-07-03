from django.urls import path

from .auth_views import LoginView, LogoutView, MeView
from .views import (
    ActivityDetailView,
    ActivityListView,
    ImportLeadsCSVView,
    LeadDetailView,
    LeadListView,
)

urlpatterns = [
    path("auth/login/", LoginView.as_view(), name="auth-login"),
    path("auth/logout/", LogoutView.as_view(), name="auth-logout"),
    path("auth/me/", MeView.as_view(), name="auth-me"),
    path("leads/import-csv/", ImportLeadsCSVView.as_view(), name="leads-import-csv"),
    path("leads/", LeadListView.as_view(), name="lead-list"),
    path("leads/<uuid:pk>/", LeadDetailView.as_view(), name="lead-detail"),
    path("activities/", ActivityListView.as_view(), name="activity-list"),
    path("activities/<uuid:pk>/", ActivityDetailView.as_view(), name="activity-detail"),
]