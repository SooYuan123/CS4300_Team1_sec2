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
from home.views import index, events_list, events_api, register, gallery, toggle_favorite, favorites

urlpatterns = [
    path('login/', auth_views.LoginView.as_view(template_name='auth/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('register/', register, name='register'),
    path('', index, name='index'),
    path('events/', events_list, name="events_list"),
    path('api/events/', events_api, name='events_api'),
    path('gallery/', gallery, name='gallery'),
    path('toggle-favorite/', toggle_favorite, name='toggle_favorite'),
    path('favorites/', favorites, name='favorites'),
]
