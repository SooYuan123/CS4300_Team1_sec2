import pytest
from django.urls import reverse
from django.contrib.auth.models import User
from home.models import Favorite


@pytest.mark.django_db
def test_toggle_favorite_requires_auth(client):
    """Unauthenticated users should get redirected data and 401."""
    url = reverse("toggle_favorite")  # Make sure you named the URL correctly
    response = client.post(url, {"image_url": "http://x.com/img.jpg"})
    assert response.status_code == 401
    json = response.json()
    assert json["redirect"] == "/login/"


@pytest.mark.django_db
def test_toggle_favorite_creates_favorite(client):
    """First toggle should create a Favorite entry."""
    user = User.objects.create_user(username="t1", password="pass")
    client.login(username="t1", password="pass")

    url = reverse("toggle_favorite")
    data = {
        "image_url": "http://x.com/img1.jpg",
        "title": "Nebula",
        "desc": "Space!"
    }
    response = client.post(url, data)

    assert response.status_code == 200
    assert response.json()["favorited"] is True

    fav = Favorite.objects.get(user=user, image_url=data["image_url"])
    assert fav.title == "Nebula"
    assert fav.desc == "Space!"


@pytest.mark.django_db
def test_toggle_favorite_unfavorites_when_existing(client):
    """Second toggle should delete the existing entry."""
    user = User.objects.create_user(username="t2", password="pass")
    client.login(username="t2", password="pass")

    # Pre-create favorite
    fav = Favorite.objects.create(
        user=user,
        image_url="http://x.com/img2.jpg",
        title="Galaxy"
    )

    url = reverse("toggle_favorite")
    response = client.post(url, {"image_url": fav.image_url})

    assert response.status_code == 200
    assert response.json()["favorited"] is False
    assert Favorite.objects.filter(user=user, image_url=fav.image_url).count() == 0


@pytest.mark.django_db
def test_toggle_favorite_respects_unique_constraint(client):
    """
    If two toggles hit the same URL, 'get_or_create' must not duplicate.
    """
    user = User.objects.create_user(username="t3", password="pass")
    client.login(username="t3", password="pass")

    url = reverse("toggle_favorite")
    img = "http://x.com/unique.jpg"

    # First toggle → create
    client.post(url, {"image_url": img})

    # Second toggle → delete
    client.post(url, {"image_url": img})

    assert Favorite.objects.filter(user=user, image_url=img).count() == 0


@pytest.mark.django_db
def test_favorites_view_lists_user_favorites(client):
    """Ensure the favorites page returns the user's favorites."""
    user = User.objects.create_user(username="t4", password="pass")
    client.login(username="t4", password="pass")

    Favorite.objects.create(user=user, image_url="http://x.com/a.jpg", title="A")
    Favorite.objects.create(user=user, image_url="http://x.com/b.jpg", title="B")

    url = reverse("favorites")
    response = client.get(url)

    assert response.status_code == 200
    # Check context
    favs = response.context["favorites"]
    assert len(favs) == 2
    assert {f.title for f in favs} == {"A", "B"}


@pytest.mark.django_db
def test_favorites_view_requires_login(client):
    """favorites view should redirect (302) if user not logged in."""
    url = reverse("favorites")
    response = client.get(url)
    assert response.status_code == 302
    assert "/login" in response.url
