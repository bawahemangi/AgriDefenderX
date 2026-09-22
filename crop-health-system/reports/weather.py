"""
Fetches current weather for a farm's coordinates.

If OPENWEATHER_API_KEY is configured, calls the real OpenWeatherMap API.
Otherwise falls back to season-representative synthetic weather for
Maharashtra so the risk-scoring pipeline still runs end-to-end in a demo
without any API key configured. The fallback is clearly not real data --
swap in a real key for anything beyond a demo.
"""
from __future__ import annotations

import datetime as dt
import random

import requests
from django.conf import settings
from django.utils import timezone

from .models import Farm, WeatherSnapshot


def _synthetic_weather(farm: Farm) -> dict:
    """Season-representative synthetic weather for Maharashtra, seeded by
    farm id + day so it's stable within a day rather than random noise on
    every call."""
    seed = farm.id * 10_000 + dt.date.today().toordinal()
    rng = random.Random(seed)

    month = dt.date.today().month
    if month in (6, 7, 8, 9):        # monsoon
        temp = rng.uniform(24, 30)
        humidity = rng.uniform(75, 95)
        rainfall = rng.uniform(20, 90)
        wind = rng.uniform(8, 18)
    elif month in (11, 12, 1, 2):    # winter
        temp = rng.uniform(15, 26)
        humidity = rng.uniform(35, 60)
        rainfall = rng.uniform(0, 5)
        wind = rng.uniform(3, 10)
    else:                             # summer
        temp = rng.uniform(28, 40)
        humidity = rng.uniform(20, 45)
        rainfall = rng.uniform(0, 10)
        wind = rng.uniform(5, 15)

    return {
        "temperature_c": round(temp, 1),
        "humidity_pct": round(humidity, 1),
        "rainfall_mm_7d": round(rainfall, 1),
        "wind_kmh": round(wind, 1),
        "source": "synthetic",
    }


def _fetch_openweathermap(farm: Farm) -> dict | None:
    api_key = settings.OPENWEATHER_API_KEY
    if not api_key:
        return None
    try:
        resp = requests.get(
            "https://api.openweathermap.org/data/2.5/weather",
            params={"lat": farm.latitude, "lon": farm.longitude, "appid": api_key, "units": "metric"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "temperature_c": data["main"]["temp"],
            "humidity_pct": data["main"]["humidity"],
            # OpenWeatherMap's free current-weather endpoint doesn't give 7-day
            # rainfall; approximate from the last-hour/3-hour field if present.
            "rainfall_mm_7d": (data.get("rain", {}).get("1h", 0) or 0) * 24 * 7,
            "wind_kmh": data["wind"]["speed"] * 3.6,
            "source": "openweathermap",
        }
    except Exception:
        return None


def get_or_fetch_weather(farm: Farm) -> WeatherSnapshot:
    """Returns a fresh-enough (same-day) WeatherSnapshot for the farm,
    fetching new data only if we don't already have one from today."""
    today_start = timezone.make_aware(dt.datetime.combine(dt.date.today(), dt.time.min))
    existing = farm.weather_snapshots.filter(fetched_at__gte=today_start).first()
    if existing:
        return existing

    data = _fetch_openweathermap(farm) or _synthetic_weather(farm)
    return WeatherSnapshot.objects.create(farm=farm, **data)
