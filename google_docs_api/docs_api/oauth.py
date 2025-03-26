import os
import requests
import google.oauth2.credentials
import google.auth.transport.requests
import google_auth_oauthlib.flow
from googleapiclient.discovery import build
from django.conf import settings
from django.shortcuts import redirect
from django.http import JsonResponse
from django.utils.crypto import get_random_string

# Allow HTTP for development
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

# Google OAuth Scopes (for Docs API access)
SCOPES = ["https://www.googleapis.com/auth/documents"]

def google_auth(request):
    """Initiates OAuth flow to get user authorization"""
    flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
        settings.GOOGLE_CREDENTIALS_FILE, SCOPES
    )
    flow.redirect_uri = "http://localhost:8000/api/oauth2callback/"

    authorization_url, state = flow.authorization_url(access_type="offline", prompt="consent")

    # Store state in session for later verification
    request.session["oauth_state"] = state

    return redirect(authorization_url)


def oauth_callback(request):
    """Handles the OAuth callback and retrieves access token"""
    expected_state = request.session.get("oauth_state")
    received_state = request.GET.get("state")

    if expected_state != received_state:
        return JsonResponse({"error": "OAuth state mismatch. Possible CSRF attack."}, status=400)

    flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
        settings.GOOGLE_CREDENTIALS_FILE, SCOPES, state=expected_state
    )
    flow.redirect_uri = "http://localhost:8000/api/oauth2callback/"

    authorization_response = request.build_absolute_uri()
    flow.fetch_token(authorization_response=authorization_response)

    # Save credentials in session
    credentials = flow.credentials
    credentials_dict = credentials_to_dict(credentials)

    print(f"🔹 Storing credentials: {credentials_dict}")  # ✅ Debugging log

    request.session["google_credentials"] = credentials_dict
    request.session.modified = True
    request.session.save()  # 🚀 Manually save session

    session_id = request.session.session_key  # ✅ Get session key

    print(f"🔍 Session ID After Login: {session_id}")  # ✅ Debug log

    response = JsonResponse({
        "message": "Authentication successful!",
        "sessionid": session_id  # ✅ Return session ID in response
    })
    
    response.set_cookie("sessionid", session_id, httponly=True, samesite="Lax")  # ✅ Ensure session cookie is set

    return response


def credentials_to_dict(credentials):
    """Helper function to convert credentials object to dictionary"""
    return {
        "token": credentials.token,
        "refresh_token": credentials.refresh_token,
        "token_uri": credentials.token_uri,
        "client_id": credentials.client_id,
        "client_secret": credentials.client_secret,
        "scopes": credentials.scopes,
    }

def refresh_access_token(credentials_dict):
    """Refreshes the access token using the refresh token."""
    refresh_token = credentials_dict.get("refresh_token")
    if not refresh_token:
        print("❌ No refresh token found!")
        return None  # Can't refresh without a refresh token

    print(f"🔄 Attempting to refresh token: {refresh_token}")  # ✅ Debug log

    data = {
        "client_id": credentials_dict["client_id"],
        "client_secret": credentials_dict["client_secret"],
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }
    response = requests.post("https://oauth2.googleapis.com/token", data=data)

    print(f"🔍 Google Response: {response.json()}")  # ✅ Debug log

    if response.status_code == 200:
        new_token = response.json()
        credentials_dict["token"] = new_token["access_token"]
        return credentials_dict  # ✅ Return updated credentials
    else:
        print("❌ Failed to refresh token!")
        return None  # Token refresh failed

