from django.shortcuts import render
from .utils import fetch_astronomical_events

def index(request):
    return render(request, 'index.html')

def events_list(request):
    events = fetch_astronomical_events()
    return render(request, 'events_list.html', {"events": events})
