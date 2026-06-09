
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

print(requests.get('https://0830lsh5ew.cdn.twcstorage.ru').text)