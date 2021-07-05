import requests
import json
from pprint import pprint

srvaddr = 'https://tahomalink.com'
user = 'somfy@oott.hu'
passwd = '12bsmart34'

with requests.Session() as s:
    r = s.post(srvaddr + '/enduser-mobile-web/enduserAPI/login', [('userId', user), ('userPassword', passwd)])
    response = r.json()

    if response['success']:
        print('Success')
        r = s.get(srvaddr + '/enduser-mobile-web/enduserAPI/setup/devices')
        pprint(r.json())
        #r = s.post(srvaddr + '/enduser-mobile-web/enduserAPI/exec/apply', json={})
        
    else:
        print('Failure')
