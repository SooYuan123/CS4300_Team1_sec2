from django.db import models

""" cache API data """
class AstronomicalEvent(models.Model):
    # Source API choices
    SOURCE_CHOICES = [
        ('astronomy_api', 'Astronomy API'),
        ('open_meteo', 'Open-Meteo'),
        ('ams_meteors', 'AMS Meteors'),
    ]
    
    # Event category choices
    CATEGORY_CHOICES = [
        ('celestial_body', 'Celestial Body'),
        ('twilight', 'Astronomical Twilight'),
        ('meteor_shower', 'Meteor Shower'),
        ('fireball', 'Fireball'),
    ]
    
    body_name = models.CharField(max_length=50)
    event_type = models.CharField(max_length=100)
    peak_date = models.DateTimeField()
    rise_time = models.DateTimeField(null=True, blank=True)
    set_time = models.DateTimeField(null=True, blank=True)
    altitude = models.FloatField(null=True, blank=True)
    obscuration = models.FloatField(null=True, blank=True)
    
    # New fields for API integration
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default='astronomy_api')
    event_category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='celestial_body')
    extra_info = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return f"{self.body_name} - {self.event_type} on {self.peak_date.strftime('%Y-%m-%d')}"