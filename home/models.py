from django.db import models

""" cache API data """
class AstronomicalEvent(models.Model):
    name = models.CharField(max_length=100)
    event_type = models.CharField(max_length=100)
    utc_time = models.CharField(max_length=100)
    description = models.TextField()
    visibility = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.name} - {self.event_type}"