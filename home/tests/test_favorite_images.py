import pytest
from django.urls import reverse
from django.contrib.auth.models import User
from home.models import Favorite

@pytest.mark.django_db
def test_favorite_image_requires_login(client):
    url = reverse("toggle_favorite")
    response = client.post(url, {"image_url": "abc.jpg"})
    assert response.status_code == 401

@pytest.mark.django_db
def test_favorite_image_add_and_remove(client):
    user = User.objects.create_user("x", password="pass")
    client.login(username="x", password="pass")

    url = reverse("toggle_favorite")

    # Add
    response = client.post(url, {
        "image_url": "abc.jpg",
        "title": "test",
        "desc": "desc",
    })
    assert response.status_code == 200
    assert Favorite.objects.count() == 1

    # Remove
    response = client.post(url, {
        "image_url": "abc.jpg",
    })
    assert response.status_code == 200
    assert Favorite.objects.count() == 0
