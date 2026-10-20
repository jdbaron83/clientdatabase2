from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("clients/", views.client_list, name="client_list"),
    path("clients/new/", views.client_create, name="client_create"),
    path("clients/<int:pk>/", views.client_detail, name="client_detail"),
    path("clients/<int:pk>/edit/", views.client_update, name="client_update"),
    path("clients/<int:client_pk>/admit/", views.episode_create, name="episode_create"),
    path("episodes/<int:pk>/", views.episode_detail, name="episode_detail"),
    path("episodes/<int:pk>/edit/", views.episode_update, name="episode_update"),
    path("episodes/<int:pk>/discharge/", views.episode_discharge, name="episode_discharge"),
    path("episodes/<int:episode_pk>/authorizations/new/", views.authorization_create, name="authorization_create"),
    path("episodes/<int:episode_pk>/medications/new/", views.medication_create, name="medication_create"),
    path("authorizations/", views.authorization_list, name="authorization_list"),
    path("authorizations/<int:pk>/edit/", views.authorization_update, name="authorization_update"),
    path("census/", views.census, name="census"),
    path("waitlist/", views.waitlist, name="waitlist"),
    path("waitlist/new/", views.waitlist_create, name="waitlist_create"),
    path("waitlist/<int:pk>/edit/", views.waitlist_update, name="waitlist_update"),
    path("waitlist/<int:pk>/admit/", views.waitlist_admit, name="waitlist_admit"),
    path("waitlist/<int:pk>/close/", views.waitlist_close, name="waitlist_close"),
    path("audit/", views.audit_log, name="audit_log"),
]
