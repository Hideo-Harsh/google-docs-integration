from django.http import JsonResponse
from rest_framework.decorators import api_view
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from bs4 import BeautifulSoup
from google.auth.exceptions import RefreshError
from .oauth import refresh_access_token

@api_view(["POST"])
def create_google_doc(request):
    """API endpoint to create a new Google Doc and insert formatted content"""

    print(" dai ")

    # Get OAuth credentials from session
    creds_dict = request.session.get("google_credentials")
    if not creds_dict:
        return JsonResponse({"error": "User not authenticated"}, status=401)

    content = request.data.get("content")
    if not content:
        return JsonResponse({"error": "Content cannot be empty"}, status=400)

    # ✅ Validate HTML before processing
    cleaned_content, error_message = validate_html(content)
    print("clearedcontent == ",cleaned_content)
    print("error message = ", error_message)
    if error_message:
        return JsonResponse({"error": error_message}, status=400)

    creds = Credentials(**creds_dict)

    # 🔍 Check token expiration BEFORE making a request
    if creds.expired and creds.refresh_token:
        print("🔴 Token expired! Attempting to refresh...")
        new_creds_dict = refresh_access_token(creds_dict)
        if not new_creds_dict:
            return JsonResponse({
                "error": "Session expired. Please reauthenticate at /api/google-auth/"
            }, status=401)
        request.session["google_credentials"] = new_creds_dict
        request.session.modified = True
        creds = Credentials(**new_creds_dict)

    try:
        # ✅ Create Google Docs API service
        service = build("docs", "v1", credentials=creds)

        # ✅ Create an empty Google Doc
        title = request.data.get("title", "Untitled Document")
        doc = service.documents().create(body={"title": title}).execute()
        doc_id = doc["documentId"]

        # ✅ Get last valid index in the document
        index = get_document_end_index(service, doc_id)
        if index < 1:
            index = 1  # ✅ Ensure valid index

        # ✅ Convert HTML to Google Docs API requests
        requests = parse_html_to_google_docs(cleaned_content, index)

        print("Generated Requests:", requests)
        # ✅ Insert content using batchUpdate
        if requests:
            service.documents().batchUpdate(documentId=doc_id, body={"requests": requests}).execute()

        doc_url = f"https://docs.google.com/document/d/{doc_id}/edit"
        return JsonResponse({"message": "Document created successfully!", "doc_url": doc_url})

    except RefreshError:
        return JsonResponse({
            "error": "Session expired. Please reauthenticate at /api/google-auth/"
        }, status=401)
    except Exception as e:
        return JsonResponse({"error": f"Failed to create document: {str(e)}"}, status=500)

def parse_html_to_google_docs(html_content, start_index):
    """Parses HTML content and converts it into Google Docs API requests."""
    soup = BeautifulSoup(html_content, "html.parser")
    print("soup == ", soup)  

    requests = []
    index = start_index  

    for tag in soup.find_all(recursive=False):
        print(f"Processing tag: {tag.name} at index {index}")

        if tag.name == "h1":
            text_length = len(tag.text)
            requests.append(insert_text_request(index, tag.text, new_line=True))
            requests.append(update_text_style_request(index, index + text_length, bold=True, font_size=20))
            index += text_length + 1  

        elif tag.name == "p":
            text_length = len(tag.text)
            requests.append(insert_text_request(index, tag.text, new_line=True))
            requests.append(update_text_style_request(index, index + text_length, bold="b" in [c.name for c in tag.contents]))
            index += text_length + 1  

        elif tag.name == "hr":
            requests.append(insert_page_break_request(index))
            index += 1

        elif tag.name in ["ul", "ol"]:
            requests.extend(process_list(index, tag))
            index += sum(len(li.text) + 1 for li in tag.find_all("li", recursive=False))  

    print(f"✅ Final index used: {index}")
    return requests

def get_document_end_index(service, doc_id):
    """Fetches the last valid index in the Google Doc to prevent insertion errors."""
    try:
        doc = service.documents().get(documentId=doc_id).execute()
        content = doc.get("body", {}).get("content", [])

        if not content:
            return 1  # ✅ Start at 1 if document is empty

        last_element = content[-1]
        end_index = last_element.get("endIndex", 1)

        return max(1, end_index - 1)  # ✅ Prevents out-of-bound index issues

    except Exception as e:
        print(f"❌ Failed to fetch document index: {e}")
        return 1  # ✅ Safe fallback index

def process_paragraph(index, tag):
    """Processes <p> tags and applies inline formatting (bold, italic)"""
    requests = []
    cursor_position = index  # Track where to insert text within paragraph

    for content in tag.contents:  
        if isinstance(content, str):  
            requests.extend(insert_text_request(cursor_position, content, new_line=False))
        elif content.name == "b":
            requests.extend(insert_text_request(cursor_position, content.text, bold=True, new_line=False))
        elif content.name == "i":
            requests.extend(insert_text_request(cursor_position, content.text, italic=True, new_line=False))
        
        cursor_position += len(content.text)  # ✅ Move cursor forward

    # ✅ Add a new line **only** after the full paragraph is processed
    requests.append(insert_text_request(cursor_position, "\n", new_line=False))

    return requests

def process_list(index, tag):
    """Processes <ul> and <ol> lists and converts them into Google Docs list format."""
    requests = []
    list_type = "BULLET_DISC_CIRCLE_SQUARE" if tag.name == "ul" else "NUMBERED_DECIMAL_ALPHA_ROMAN"

    for li in tag.find_all("li", recursive=False):
        cursor_position = index  # Start tracking index

        # ✅ Insert the text for the list item
        requests.append({
            "insertText": {
                "location": {"index": cursor_position},
                "text": li.text + "\n"
            }
        })

        # ✅ Apply bulleting AFTER inserting text
        requests.append({
            "createParagraphBullets": {
                "range": {"startIndex": cursor_position, "endIndex": cursor_position + len(li.text)},
                "bulletPreset": list_type
            }
        })

        index += len(li.text) + 1  # Move index forward for next list item

    return requests


def insert_list_marker_request(index, list_type):
    """Returns a Google Docs API request to apply bullet points or numbering."""

    bullet_presets = {
        "ul": "BULLET_DISC_CIRCLE_SQUARE",
        "ol": "NUMBERED_DECIMAL_ALPHA_ROMAN"
    }
    
    bullet_preset = bullet_presets.get(list_type, "BULLET_DISC_CIRCLE_SQUARE")

    return {
        "createParagraphBullets": {
            "range": {"startIndex": index, "endIndex": index + 1},
            "bulletPreset": bullet_preset
        }
    }

def insert_page_break_request(index):
    """Inserts a page break at the given index."""
    return {
        "insertPageBreak": {
            "location": {"index": index}
        }
    }


def insert_text_request(index, text, new_line=False):
    """Inserts text at the correct index (no bold/font_size)."""
    if not text.strip():
        return []  # ✅ Skip empty text

    return {
        "insertText": {
            "location": {"index": max(1, index)},  
            "text": text + ("\n" if new_line else "")
        }
    }

def update_text_style_request(start_index, end_index, bold=False, font_size=12):
    """Applies formatting (bold, font size) AFTER text insertion."""
    return {
        "updateTextStyle": {
            "range": {"startIndex": start_index, "endIndex": end_index},
            "textStyle": {
                "bold": bold,
                "fontSize": {"magnitude": font_size, "unit": "PT"}
            },
            "fields": "bold,fontSize"
        }
    }


def insert_page_break_request(index):
    """Returns a request to insert a page break."""
    return {
        "insertPageBreak": {
            "location": {"index": index}
        }
    }

def validate_html(content):
    """Validates HTML input and ensures only allowed tags are present"""
    allowed_tags = {"h1", "p", "b", "i", "ul", "ol", "li", "br", "hr"}
    soup = BeautifulSoup(content, "html.parser")
    disallowed_tags = []

    # Check for disallowed tags
    for tag in soup.find_all():
        if tag.name not in allowed_tags:
            disallowed_tags.append(tag.name)

    if disallowed_tags:
        return None, f"❌ Invalid tags detected: {', '.join(set(disallowed_tags))}. Allowed tags: {', '.join(allowed_tags)}."

    # Ensure lists (`ul`, `ol`) contain only `li` elements
    for tag in soup.find_all(["ul", "ol"]):
        if not all(child.name == "li" for child in tag.find_all(recursive=False)):
            return None, f"❌ Invalid list structure in <{tag.name}>. Lists must only contain <li> items."

    return str(soup), None  # ✅ Return cleaned HTML and no error