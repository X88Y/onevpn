
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

print(requests.get('https://5yswutjnkk.cdn.twcstorage.ru', verify=False))