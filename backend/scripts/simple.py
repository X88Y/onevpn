
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

print(requests.get('https://jl1x2z77a9.cdn.twcstorage.ru/32LBLkHXWLWvXAd-').text)