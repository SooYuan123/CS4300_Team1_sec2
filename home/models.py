from django.db import models

""" cache API data """
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