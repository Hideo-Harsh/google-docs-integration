import os
import google.oauth2.credentials
import google_auth_oauthlib.flow
from googleapiclient.discovery import build
from django.conf import settings
from django.shortcuts import redirect
from django.http import JsonResponse

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
    expected_state = request.session.get("oauth_state")  # ✅ Get stored state
    received_state = request.GET.get("state")  # ✅ Get state from Google response
    
    print(f"Expected State: {expected_state}")
    print(f"Received State: {received_state}")


    if expected_state != received_state:
        return JsonResponse({"error": "OAuth state mismatch. Possible CSRF attack."}, status=400)

    flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
        settings.GOOGLE_CREDENTIALS_FILE, SCOPES, state=expected_state
    )
    flow.redirect_uri = "http://localhost:8000/api/oauth2callback/"

    authorization_response = request.build_absolute_uri()
    flow.fetch_token(authorization_response=authorization_response)

    # Save credentials in session (or DB in real apps)
    credentials = flow.credentials
    credentials_dict = credentials_to_dict(credentials)
    print(f"🔹 Storing credentials: {credentials_dict}")  # Debugging print
    # ✅ Store in session
    request.session["google_credentials"] = credentials_dict
    request.session.modified = True  # Ensure session is saved
    request.session.save()  # 🚀 Manually force saving session

    return JsonResponse({"message": "Authentication successful!"})

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
