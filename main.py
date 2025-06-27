import requests
import json
import rich
from rich.table import Table
from rich.console import Console
from bs4 import BeautifulSoup
from datetime import datetime
import functools
import os
import time
import pytz
from jinja2 import Template

# Set Vancouver timezone
vancouver_tz = pytz.timezone('America/Vancouver')

def get_timezone_offset():
    """Get current timezone offset in hours."""
    now = datetime.now(vancouver_tz)
    return int(now.utcoffset().total_seconds() / 3600)

def ms_to_knots(speed_mps):
    """Convert speed from meters per second to knots."""
    return speed_mps * 1.94384

def mph_to_knots(speed_mph):
    """Convert speed from miles per hour to knots."""
    return speed_mph * 0.868976

def get_windy_forecast(model_name):
    assert model_name in ['gfs27_long', 'ecmwf', 'iconglobal', ]
    tz_offset = get_timezone_offset()
    api_url = f'https://windy.app/widget/data.php?id=wfwindyapp&model={model_name}&spotID=5099589&tz={tz_offset}'
    response = requests.get(api_url)
    if response.status_code == 200:
        # Remove the "window.wfwindyapp=" prefix and parse JSON
        json_str = response.text.replace('window.wfwindyapp=', '')
        loaded_data = json.loads(json_str)
        return normalize_windy(json.loads(loaded_data['data']))
    else:
        return {"error": "Failed to retrieve data"}

def normalize_windy(data):
    normalized_data = []
    for item in data:
        normalized_item = {
            'time': item['timestamp'],
            'speed_knots': ms_to_knots(item['windSpeed']),
            'gust_knots': ms_to_knots(item['windGust']),
            'direction': item['windDirection'],
            'temperature': item['airTemp'],
        }
        normalized_data.append(normalized_item)
    return normalized_data

def get_windfinder_forecast():
    tz_offset = get_timezone_offset()
    url = f'https://www.windfinder.com/forecast/jericho_beach_park?tz={tz_offset}'
    response = requests.get(url)
    if response.status_code != 200:
        return {"error": "Failed to retrieve data"}

    soup = BeautifulSoup(response.text, 'html.parser')
    forecast_data = []
        
    soup = BeautifulSoup(response.text, 'html.parser')
    forecast_data = []
    
    # Find all forecast days
    days = soup.select('div.weathertable.forecast-day')
    
    for day in days:
        # Extract date from header
        date = day.select_one('h3.weathertable__headline').text.strip()
        
        # Find all forecast rows for this day
        rows = day.select('div.weathertable__row')
        
        for row in rows:
            # Extract time
            time_elem = row.select_one('div.data-time span.value')
            time = time_elem.text if time_elem else None
            
            # Extract wind speed
            speed_elem = row.select_one('div.data-bar span.units-ws')
            speed_mph = float(speed_elem.text) if speed_elem else None
            
            # Extract wind gusts
            gust_elem = row.select_one('div.data-gusts span.units-ws')
            gust_mph = float(gust_elem.text) if gust_elem else None

            # Extract wind direction
            direction_elem = row.select_one('div.directionarrow')
            direction = float(direction_elem['title'].replace('°', '')) if direction_elem else None
            if direction:
                direction = (direction + 180) % 360  # Windfinder gives direction from south
            
            # Extract temperature
            temp_elem = row.select_one('div.data-temp span.units-at')
            temp = float(temp_elem.text) if temp_elem else None

            if all([time, speed_mph, gust_mph, direction, temp]):
                date_str = date + " " + time.replace('h', ':00')  # Convert "02h" to "02:00"
                dt = datetime.strptime(date_str, "%A, %b %d %H:%M")
                # Set current year and timezone
                dt = dt.replace(year=datetime.now(vancouver_tz).year)
                dt = vancouver_tz.localize(dt)
                timestamp = int(dt.timestamp())
                
                forecast_data.append({
                    'time': timestamp,
                    'speed_knots': mph_to_knots(speed_mph),
                    'gust_knots': mph_to_knots(gust_mph),
                    'direction': direction,
                    'temperature': temp
                })
            
    return forecast_data

def get_last_jericho_weather_timestamp(filename):
    if not os.path.exists(filename):
        return -1
    with open(filename, 'r') as f:
        last_line = f.readlines()[-1]
    return json.loads(last_line)['time']

def _parse_jericho_weather_history(line):
    """Parse a single line of Jericho weather history data."""
    try:
        # Skip header or empty lines
        if not line or 'Date' in line or '-' in line:
            return None
            
        # Split line into columns using whitespace
        parts = line.strip().split()
        if len(parts) < 8:  # Ensure minimum required columns
            return None
            
        # Parse date and time
        date_str = parts[0]  # Format: "6/22/25"
        time_str = parts[1]  # Format: "12:30a"
        
        # Parse numeric values
        temp = float(parts[2])
        wind_speed = float(parts[7])
        wind_dir = parts[8]
        wind_gust_knots = float(parts[10])
        rain = float(parts[16])
        
        # Convert 12-hour time to 24-hour
        time_val = time_str[:-1]  # Remove 'a' or 'p'
        hour, minute = map(int, time_val.split(':'))
        if time_str.endswith('p') and hour != 12:
            hour += 12
        elif time_str.endswith('a') and hour == 12:
            hour = 0
            
        # Create datetime object (assume 20xx for year)
        month, day, year = map(int, date_str.split('/'))
        year += 2000
        dt = datetime(year, month, day, hour, int(minute))
        dt = vancouver_tz.localize(dt)
        
        # Convert wind speed from mph to knots
        wind_speed_knots = wind_speed
        
        # Convert cardinal directions to degrees
        dir_to_deg = {'N': 0, 'NNE': 22.5, 'NE': 45, 'ENE': 67.5, 
                     'E': 90, 'ESE': 112.5, 'SE': 135, 'SSE': 157.5,
                     'S': 180, 'SSW': 202.5, 'SW': 225, 'WSW': 247.5,
                     'W': 270, 'WNW': 292.5, 'NW': 315, 'NNW': 337.5}
        
        direction = dir_to_deg.get(wind_dir, -1)
        
        return {
            'time': int(dt.timestamp()),
            'speed_knots': wind_speed_knots,
            'gust_knots': wind_gust_knots,
            'direction': direction,
            'temperature': temp,
            'rain': rain
        }
    except (ValueError, IndexError):
        return None

def update_jericho_weather_history(filename='jsca_weather.jsonl'):
    txt_url = 'https://jsca.bc.ca/main/downld02.txt'
    response = requests.get(txt_url)
    if response.status_code != 200:
        print("Failed to retrieve weather data")
        return
    
    lines = response.text.splitlines()
    last_timestamp = get_last_jericho_weather_timestamp(filename)
    
    new_data = []
    for line in lines:
        parsed = _parse_jericho_weather_history(line)
        if parsed and parsed['time'] > last_timestamp:
            new_data.append(parsed)
    
    if new_data:
        with open(filename, 'a') as f:
            for item in new_data:
                f.write(json.dumps(item) + '\n')
        print(f"Added {len(new_data)} new records to {filename}")

def get_pirateweather_forecast():
    """Get weather forecast from Pirateweather API including precipitation and conditions."""
    # Jericho Beach coordinates
    lat, lon = 49.28269, -123.20581  # 49°16'57.7"N 123°12'20.9"W converted to decimal
    
    # You'll need to get a free API key from pirateweather.net
    api_key = os.environ['PIRATE_WEATHER_API_KEY']
    
    # Use SI units to get wind in m/s (easier to convert to knots)
    url = f'https://api.pirateweather.net/forecast/{api_key}/{lat},{lon}?units=si&exclude=minutely,daily,alerts&extend=hourly'
    
    try:
        response = requests.get(url)
        if response.status_code != 200:
            print(f"Pirateweather API error: {response.status_code}")
            return []
        
        data = response.json()
        return normalize_pirateweather(data)
    except Exception as e:
        print(f"Error fetching Pirateweather data: {e}")
        return []

def normalize_pirateweather(data):
    """Normalize Pirateweather data to match our format."""
    normalized_data = []
    
    if 'hourly' not in data or 'data' not in data['hourly']:
        return normalized_data
    
    for item in data['hourly']['data']:
        # Map weather conditions to simple categories
        icon = item['icon']
        condition = map_weather_condition(icon)
        wind_direction = item['windBearing']
        wind_direction = (wind_direction + 180) % 360  # Convert to meteorological convention
        normalized_item = {
            'time': item['time'],
            'speed_knots': ms_to_knots(item.get('windSpeed', 0)),
            'gust_knots': ms_to_knots(item.get('windGust', 0)),
            'direction': wind_direction,
            'temperature': item.get('temperature', 0),
            'condition': condition,
            'icon': icon,
            'precipitation_probability': (item.get('precipProbability', 0) * 100),
            'precipitation_intensity': item.get('precipIntensity', 0),
            'cloud_cover': (item.get('cloudCover', 0) * 100)
        }
        normalized_data.append(normalized_item)
    
    return normalized_data

def map_weather_condition(icon):
    """Map Pirateweather icons to simple weather conditions."""
    condition_map = {
        'clear-day': 'sunny',
        'clear-night': 'clear',
        'rain': 'rainy',
        'snow': 'snowy',
        'sleet': 'rainy',
        'wind': 'windy',
        'fog': 'cloudy',
        'cloudy': 'cloudy',
        'partly-cloudy-day': 'partly-cloudy',
        'partly-cloudy-night': 'partly-cloudy',
        'thunderstorm': 'rainy',
        'hail': 'rainy'
    }
    return condition_map.get(icon, 'unknown')

FORECASTS = {
    'windy_gfs27_long': functools.partial(get_windy_forecast, 'gfs27_long'),
    'windy_ecmwf': functools.partial(get_windy_forecast, 'ecmwf'),
    'windy_iconglobal': functools.partial(get_windy_forecast, 'iconglobal'),
    'windfinder': get_windfinder_forecast,
    'pirateweather': get_pirateweather_forecast,
}

def save_forecast(forecast_name, data):
    """Save forecast data to a jsonl file in timestamped directory."""
    now = datetime.now(vancouver_tz)
    # Create directory path with timestamp components
    dir_path = f"./{now.year}/{now.month:02d}/{now.day:02d}/{now.hour:02d}/{now.minute:02d}"
    os.makedirs(dir_path, exist_ok=True)
    
    # Save data to jsonl file
    file_path = f"{dir_path}/{forecast_name}.jsonl"
    with open(file_path, 'w') as f:
        for item in data:
            f.write(json.dumps(item) + '\n')
    print(f"Saved {forecast_name} to {file_path}")

def run_periodic_save():
    """Run forecasts and save data every 10 minutes."""
    while True:
        now = datetime.now(vancouver_tz)
        # Only save on minutes divisible by 10 (00, 10, 20, 30, 40, 50)
        if now.minute % 10 == 0:
            for name, forecast_func in FORECASTS.items():
                try:
                    data = forecast_func()
                    save_forecast(name, data)
                except Exception as e:
                    print(f"Error getting forecast for {name}: {e}")
            try:
                update_jericho_weather_history()
            except Exception as e:
                print(f"Error updating Jericho weather history: {e}")
            time.sleep(60)  # Wait a minute to avoid multiple saves in the same minute
        time.sleep(1)

def generate_website():
    """Generate the website HTML file."""
    from make_forecast import get_website_data
    
    # Get data for the website
    data = get_website_data()
    
    # Load the Jinja template
    with open('website.jinja', 'r') as f:
        template = Template(f.read())
    
    # Render the template with data
    html_content = template.render(**data)
    
    # Save to HTML file
    with open('index.html', 'w') as f:
        f.write(html_content)
    
    print("Website generated: index.html")

if __name__ == "__main__":
    console = Console()
    table = Table(title="Windy Forecast")

    # Add columns
    table.add_column("Time", justify="right")
    table.add_column("Wind Speed", justify="right")
    table.add_column("Wind Gust", justify="right")
    table.add_column("Direction", justify="right")
    table.add_column("Temperature", justify="right")

    # Get and normalize data
    # data = get_windy_forecast('gfs27_long')
    data = get_windfinder_forecast()

    # Add rows from normalized data
    for item in data:
        table.add_row(
            str(item['time']),
            f"{item['speed_knots']} knots",
            f"{item['gust_knots']} knots",
            f"{item['direction']}°",
            f"{item['temperature']}°C"
        )

    console.print(table)
    update_jericho_weather_history()
    
    # Generate website
    generate_website()
    
    run_periodic_save()
