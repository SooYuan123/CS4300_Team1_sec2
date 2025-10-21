"""
Gunicorn configuration file for Render deployment.
This tells Gunicorn to look inside the CelestiaTrack project folder
and use the wsgi.py file to start the Django application.
"""
bind = '0.0.0.0:8000'
workers = 4 # Good starting number of worker processes
module = 'CelestiaTrack.wsgi:application'
