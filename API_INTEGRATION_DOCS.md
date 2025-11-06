# API Integration Skeleton Documentation

## Overview
This document describes the API integration skeleton implemented for the CelestiaTrack astronomical events system. The skeleton integrates three APIs to provide comprehensive astronomical event data.

## Integrated APIs

### 1. Astronomy API (Existing)
- **Purpose**: Celestial body events (sun, moon, planets)
- **Authentication**: Basic Auth with APP_ID and APP_SECRET
- **Status**: ✅ Already implemented and working
- **Data**: Rise/set times, eclipses, planetary events, etc.

### 2. Open-Meteo API (New)
- **Purpose**: Astronomical twilight events
- **Authentication**: None required (free API)
- **Status**: ✅ Implemented and tested
- **Data**: Astronomical twilight start/end times
- **Endpoint**: `https://api.open-meteo.com/v1/forecast`
- **Parameters**: 
  - `latitude`, `longitude`: Location coordinates
  - `daily`: `sunrise,sunset,astronomical_twilight_start,astronomical_twilight_end`
  - `start_date`, `end_date`: Date range
  - `timezone`: `auto` (automatically detects timezone)

### 3. AMS Meteors API (New)
- **Purpose**: Meteor showers and fireball sightings
- **Authentication**: API key required (paid membership)
- **Status**: ✅ Implemented with graceful degradation
- **Data**: Meteor shower events, fireball sightings
- **Endpoints**:
  - `https://www.amsmeteors.org/members/api/open_api/get_events` (meteor showers)
  - `https://www.amsmeteors.org/members/api/open_api/get_close_reports` (fireballs)

## Implementation Details

### Database Model Extensions
The `AstronomicalEvent` model has been extended with:
- `source`: Tracks which API provided the data (`astronomy_api`, `open_meteo`, `ams_meteors`)
- `event_category`: Categorizes event types (`celestial_body`, `twilight`, `meteor_shower`, `fireball`)

### API Integration Functions

#### `fetch_twilight_events(latitude, longitude, from_date=None, to_date=None)`
- Fetches astronomical twilight data from Open-Meteo
- Returns standardized event format
- Handles API errors gracefully

#### `fetch_meteor_shower_events(from_date=None, to_date=None, api_key=None)`
- Fetches meteor shower data from AMS Meteors API
- Skips if API key is not provided
- Returns standardized event format

#### `fetch_fireball_events(from_date=None, to_date=None, api_key=None, latitude=None, longitude=None)`
- Fetches fireball sighting data from AMS Meteors API
- Skips if API key is not provided
- Returns standardized event format

### Event Aggregation
The `fetch_all_events()` function now:
1. Fetches celestial body events from Astronomy API
2. Fetches twilight events from Open-Meteo API
3. Fetches meteor shower events from AMS Meteors API (if key available)
4. Fetches fireball events from AMS Meteors API (if key available)
5. Merges all events into a single chronological list

### Frontend Updates
The events list template now:
- Displays source badges for each event
- Shows category-specific information (twilight, meteor showers, fireballs)
- Handles different data schemas gracefully
- Maintains existing infinite scroll functionality

## Configuration

### Environment Variables
Add to `CS4300_Team1_sec2/CelestiaTrack/Astronomy.env`:
```
# AMS Meteors API Configuration
# Note: AMS Meteors API requires a paid membership or invitation
# Leave empty to skip meteor shower and fireball data
AMS_METEORS_API_KEY=

# Open-Meteo API Configuration
# Note: Open-Meteo requires no API key for basic usage
```

### Settings Configuration
The `AMS_METEORS_API_KEY` is loaded in `settings.py`:
```python
AMS_METEORS_API_KEY = config('AMS_METEORS_API_KEY', default='')
```

## Error Handling
- Each API call is wrapped in try-except blocks
- API failures don't break the entire page
- Graceful degradation when APIs are unavailable
- Console logging for debugging

## Testing
A test script `test_api_integration.py` is provided to verify:
- Open-Meteo API integration
- AMS Meteors API graceful degradation
- Error handling

## Usage Instructions

### For Open-Meteo API
No additional setup required. The API is free and will work immediately.

### For AMS Meteors API
1. Visit https://www.amsmeteors.org/members/imo_api
2. Obtain an API key (requires paid membership)
3. Add the key to `CS4300_Team1_sec2/CelestiaTrack/Astronomy.env`
4. Restart the Django server

## Future Enhancements
The skeleton is designed to be easily extensible:
- Additional APIs can be added by following the same pattern
- Event categories can be expanded
- Data processing can be enhanced
- Caching can be implemented for better performance

## File Structure
```
CS4300_Team1_sec2/
├── CelestiaTrack/
│   ├── Astronomy.env          # API configuration
│   └── settings.py            # Django settings
├── home/
│   ├── models.py              # Extended database model
│   ├── utils.py               # API integration functions
│   ├── views.py               # Updated event aggregation
│   └── templates/
│       └── events_list.html   # Updated frontend
└── test_api_integration.py    # Test script
```

## API Response Formats

### Open-Meteo Response
```json
{
  "daily": {
    "time": ["2024-01-01", "2024-01-02"],
    "astronomical_twilight_start": ["05:30", "05:31"],
    "astronomical_twilight_end": ["18:45", "18:46"]
  }
}
```

### AMS Meteors Response
```json
{
  "status": 200,
  "result": [
    {
      "name": "Perseids",
      "peak_date": "2024-08-12",
      "description": "Annual meteor shower",
      "meteor_count": "60 per hour"
    }
  ]
}
```

## Notes
- All APIs use the hardcoded location: (38.775867, -84.39733)
- Date range: Past 365 days to next 1095 days (~3 years)
- Events are sorted chronologically regardless of source
- The system gracefully handles missing API keys
- Error logging helps with debugging and monitoring
