from django.urls import path
from .views import create_google_doc

urlpatterns = [
    path('create-doc/', create_google_doc, name='create-doc'),
]