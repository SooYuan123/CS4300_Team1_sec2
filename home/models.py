from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver


# cache API data
class AstronomicalEvent(models.Model):
    body_name = models.CharField(max_length=50)
    event_type = models.CharField(max_length=100)
    peak_date = models.DateTimeField()
    rise_time = models.DateTimeField(null=True, blank=True)
    set_time = models.DateTimeField(null=True, blank=True)
    altitude = models.FloatField(null=True, blank=True)
    obscuration = models.FloatField(null=True, blank=True)
    extra_info = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return f"{self.body_name} - {self.event_type} on {self.peak_date.strftime('%Y-%m-%d')}"


class Favorite(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    image_url = models.URLField()
    title = models.CharField(max_length=255, blank=True)
    desc = models.TextField(blank=True)

    class Meta:
        unique_together = ('user', 'image_url')

    def __str__(self):
        return f"{self.user.username} -> {self.title or self.image_url}"


class EventFavorite(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    event_id = models.CharField(max_length=255, default="", blank=True)
    body = models.CharField(max_length=100)
    type = models.CharField(max_length=100)
    peak = models.CharField(max_length=100, blank=True)
    rise = models.CharField(max_length=100, blank=True)
    transit = models.CharField(max_length=100, blank=True)
    set = models.CharField(max_length=100, blank=True)  # should rename later
    saved_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.event_id}"


class UserProfile(models.Model):
    """
    Extended user profile with additional information.
    Automatically created when a User is created.
    """
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='profile'
    )
    bio = models.TextField(
        max_length=500,
        blank=True,
        help_text="Tell us about yourself"
    )
    profile_picture = models.ImageField(
        upload_to='profile_pics/',
        blank=True,
        null=True,
        help_text="Upload a profile picture (minimum 200x200px)"
    )
    location = models.CharField(
        max_length=100,
        blank=True,
        help_text="Your location (optional)"
    )
    favorite_celestial_body = models.CharField(
        max_length=100,
        blank=True,
        help_text="Your favorite celestial object"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "User Profile"
        verbose_name_plural = "User Profiles"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username}'s Profile"

    def get_profile_picture_url(self):
        """Return profile picture URL if exists, otherwise default avatar placeholder"""
        if self.profile_picture:
            return self.profile_picture.url
        return f'https://ui-avatars.com/api/?name={self.user.username}&size=200&background=random'


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):  # pylint: disable=unused-argument
    """Create a UserProfile whenever a new User is created."""
    if created:
        UserProfile.objects.create(user=instance)


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):  # pylint: disable=unused-argument
    """Save the UserProfile whenever the User is saved."""
    if hasattr(instance, "profile"):
        instance.profile.save()
    else:
        UserProfile.objects.create(user=instance)
