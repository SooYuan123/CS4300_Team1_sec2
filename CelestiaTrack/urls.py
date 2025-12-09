"""
URL configuration for CelestiaTrack project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from home import views
from home.views import (
    index,
    events_list,
    events_api,
    api_celestial_bodies,
    register,
    gallery,
    toggle_favorite,
    toggle_event_favorite,
    favorites,
    weather_api,
    aurora_api,
)


urlpatterns = [
    path('login/', auth_views.LoginView.as_view(template_name='auth/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('register/', register, name='register'),
    path('', index, name='index'),
    path('events/', events_list, name="events_list"),

    path('api/events/', events_api, name='events_api'),
    path('api/weather/', weather_api, name='weather_api'),
    path("api/celestial/", api_celestial_bodies),
    path("api/celestial-bodies/", views.api_celestial_bodies, name="celestial_bodies"),
    path("api/search-city/", views.api_search_city, name="api_search_city"),

    path('gallery/', gallery, name='gallery'),
    path('toggle-favorite/', toggle_favorite, name='toggle_favorite'),
    path('toggle_event_favorite/', toggle_event_favorite, name='toggle_event_favorite'),
    path('favorites/', favorites, name='favorites'),
    path('api/chatbot/', views.chatbot_api, name='chatbot_api'),
    path('admin/', admin.site.urls),

    # Profile URLs
    path('profile/edit/', views.profile_edit, name='profile_edit'),
    path('profile/', views.profile_view, name='profile'),
    path('profile/<str:username>/', views.profile_view, name='profile'),
    path('api/upload-profile-picture/', views.upload_profile_picture, name='upload_profile_picture'),

    # Aurora API
    path('api/aurora/', aurora_api, name='aurora_api'),
]

# Serve media files in development
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

