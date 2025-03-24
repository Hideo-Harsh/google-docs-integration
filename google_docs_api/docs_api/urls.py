from django.urls import path
from .oauth import google_auth, oauth_callback

urlpatterns = [
    path("google-auth/", google_auth, name="google-auth"),
    path("oauth2callback/", oauth_callback, name="oauth-callback"),
]