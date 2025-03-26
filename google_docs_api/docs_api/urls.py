from django.urls import path
from .oauth import google_auth, oauth_callback
from .views import create_google_doc

urlpatterns = [
    path("google-auth/", google_auth, name="google-auth"),
    path("oauth2callback/", oauth_callback, name="oauth-callback"),
    path("create-doc/", create_google_doc, name="create-doc"),
]