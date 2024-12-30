import requests

ip = requests.get('https://api.ipify.org').content.decode('utf8')


def check_ip():
    resp = requests.get("http://ip-api.com/json/?fields=status,message,countryCode")
    country_code = resp.json()["countryCode"]
    assert country_code != "RU"
    print("check_ip passed, country_code:", country_code)
