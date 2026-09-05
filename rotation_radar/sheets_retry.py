"""Bounded retries for transient Google API failures; never retry data contracts."""
import time
import requests


def request(method, *args, **kwargs):
    for attempt in range(3):
        try:
            response = method(*args, **kwargs)
            if response.status_code not in {408, 429, 500, 502, 503, 504} or attempt == 2:
                return response
        except (requests.Timeout, requests.ConnectionError):
            if attempt == 2:
                raise
        time.sleep(2 ** attempt)
