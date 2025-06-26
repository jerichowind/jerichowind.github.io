import json
from datetime import datetime, timedelta
import pytz
import sys
import os

# Add the current directory to Python path to import from main.py
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from main import FORECASTS, vancouver_tz
from jinja2 import Template

def get_all_forecasts():
    """Get forecasts from all providers and organize by time."""
    all_forecasts = {}
    
    for provider_name, forecast_func in FORECASTS.items():
        try:
            data = forecast_func()
            all_forecasts[provider_name] = data
        except Exception as e:
            print(f"Error getting forecast for {provider_name}: {e}")
            all_forecasts[provider_name] = []
    
    return all_forecasts

def organize_forecast_by_time(all_forecasts, days=5):
    """Organize forecasts by time slots for easier display."""
    now = datetime.now(vancouver_tz)
    end_time = now + timedelta(days=days)
    
    # Create time slots (hourly, only 9 AM to 9 PM)
    time_slots = []
    current = now.replace(minute=0, second=0, microsecond=0)
    
    while current <= end_time:
        # Only include hours between 9 AM (09:00) and 9 PM (21:00)
        if 9 <= current.hour <= 21:
            time_slots.append(int(current.timestamp()))
        current += timedelta(hours=1)
    
    organized_data = []
    
    for timestamp in time_slots:
        slot_data = {
            'timestamp': timestamp,
            'datetime': datetime.fromtimestamp(timestamp, vancouver_tz),
            'forecasts': {}
        }
        
        # Find closest forecast for each provider
        for provider, forecasts in all_forecasts.items():
            closest_forecast = None
            min_diff = float('inf')
            
            for forecast in forecasts:
                diff = abs(forecast['time'] - timestamp)
                if diff < min_diff:
                    min_diff = diff
                    closest_forecast = forecast
            
            if closest_forecast and min_diff <= 3600:  # Within 1 hour
                slot_data['forecasts'][provider] = closest_forecast
        
        organized_data.append(slot_data)
    
    return organized_data

def get_website_data():
    """Get all data needed for the website."""
    all_forecasts = get_all_forecasts()
    organized_forecasts = organize_forecast_by_time(all_forecasts)
    
    # Group forecasts by day
    days_data = []
    current_date = None
    current_day_forecasts = []
    
    for slot in organized_forecasts:
        slot_date = slot['datetime'].date()
        
        if current_date != slot_date:
            # Save previous day if exists
            if current_date is not None:
                days_data.append({
                    'date': current_date,
                    'forecasts': current_day_forecasts
                })
            
            # Start new day
            current_date = slot_date
            current_day_forecasts = [slot]
        else:
            current_day_forecasts.append(slot)
    
    # Add last day
    if current_date is not None:
        days_data.append({
            'date': current_date,
            'forecasts': current_day_forecasts
        })
    
    return {
        'forecasts': organized_forecasts,
        'days_data': days_data,
        'providers': list(FORECASTS.keys()),
        'generated_at': datetime.now(vancouver_tz)
    }

def generate_website_html():
    """Generate the website HTML file."""
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
    return html_content

if __name__ == "__main__":
    # Generate website when run directly
    generate_website_html()
