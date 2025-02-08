import requests

from src.tools.log import get_logger

# ip = requests.get('https://api.ipify.org').content.decode('utf8')

logger = get_logger(__name__)


def check_ip():
    resp = requests.get("http://ip-api.com/json/?fields=status,message,countryCode")
    country_code = resp.json()["countryCode"]
    assert country_code != "RU"
    logger.info(f"check_ip passed, country_code: {country_code}")
