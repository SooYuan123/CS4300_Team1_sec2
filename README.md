# CelestiaTrack

A Django-based web app that fetches, processes, and displays upcoming astronomical events using the AstronomyAPI.
Each event is displayed in a clean, responsive Bootstrap layout with details such as rise/set times, peak date, and additional highlights.

## Setup
1. Clone this repository or copy the project files.
2. Create a virtual environment:
   ```bash
    python -m venv venv
    source venv/bin/activate 
3. Install dependencies
   ```bash
   pip install -r requirements.txt
4. Create a .env file in the project root (with manage.py):  
ASTRONOMY_API_APP_ID=your_app_id_here  
ASTRONOMY_API_APP_SECRET=your_app_secret_here  
You can obtain your credentials by registering at [astronomyapi.com](astronomyapi.com)

5. Run migrations
   ```bash
   python manage.py migrate
6. Start server
   ```bash
   python manage.py runserver 0.0.0.0:3000
- Open browser at http://127.0.0.1:3000/
