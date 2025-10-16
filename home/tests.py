from django.test import TestCase
from django.urls import reverse

class HomePageTest(TestCase):
    """Tests the basic functionality of the landing page."""

    def test_view_url_exists_at_proper_location(self):
        """Test that the homepage resolves to the root URL (/)."""
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)

    def test_view_uses_correct_template(self):
        """Test that the correct template (index.html) is used."""
        response = self.client.get(reverse('index'))
        self.assertTemplateUsed(response, 'index.html')