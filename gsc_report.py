#!/usr/bin/env python3
import json, urllib.request, urllib.parse, datetime, sys
sys.path.insert(0, '.')
from zens_ink.search_performance import get_access_token

token = get_access_token()
end = datetime.date.today() - datetime.timedelta(days=1)
start = end - datetime.timedelta(days=27)

sites = [
    ('sc-domain:uzenlabs.com', 'uzenlabs.com'),
    ('sc-domain:valdos.xyz', 'valdos.xyz'),
    ('sc-domain:jask.dev', 'jask.dev'),
    ('sc-domain:echoir.xyz', 'echoir.xyz'),
    ('sc-domain:theonchaindiary.com', 'onchaindiary.com'),
    ('https://weekly.jask.dev/', 'weekly.jask.dev'),
    ('sc-domain:zens.ink', 'zens.ink'),
]

print(f'Period: {start} to {end} (28 days)')
print(f'{"Site":25s} {"Clicks":>7s} {"Impr":>8s} {"CTR":>6s} {"Pos":>6s}')
print('-' * 57)

for site_raw, label in sites:
    s = urllib.parse.quote(site_raw, safe='')
    api = f'https://searchconsole.googleapis.com/webmasters/v3/sites/{s}/searchAnalytics/query'
    payload = {'startDate': start.isoformat(), 'endDate': end.isoformat(), 'dimensions': [], 'rowLimit': 1}
    req = urllib.request.Request(api, data=json.dumps(payload).encode(),
        headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'})
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        rows = json.loads(resp.read().decode()).get('rows', [])
        if rows:
            r = rows[0]
            print(f'{label:25s} {int(r["clicks"]):>7d} {int(r["impressions"]):>8d} {r["ctr"]*100:>5.1f}% {r["position"]:>6.1f}')
        else:
            print(f'{label:25s}       0        0      -      -')
    except Exception as e:
        print(f'{label:25s} ERROR: {e}')

# Detail: top queries + pages for each site
for site_raw, label in sites:
    s = urllib.parse.quote(site_raw, safe='')
    api = f'https://searchconsole.googleapis.com/webmasters/v3/sites/{s}/searchAnalytics/query'

    # Top queries
    payload = {'startDate': start.isoformat(), 'endDate': end.isoformat(), 'dimensions': ['query'], 'rowLimit': 10}
    req = urllib.request.Request(api, data=json.dumps(payload).encode(),
        headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'})
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        rows = json.loads(resp.read().decode()).get('rows', [])
        if rows:
            rows.sort(key=lambda x: -x['impressions'])
            print(f'\n--- {label} Top Queries ---')
            print(f'{"Query":40s} {"Clicks":>6s} {"Impr":>6s} {"Pos":>6s}')
            for r in rows[:8]:
                q = r['keys'][0][:38]
                print(f'{q:40s} {int(r["clicks"]):>6d} {int(r["impressions"]):>6d} {r["position"]:>6.1f}')
    except:
        pass

    # Top pages
    payload = {'startDate': start.isoformat(), 'endDate': end.isoformat(), 'dimensions': ['page'], 'rowLimit': 10}
    req = urllib.request.Request(api, data=json.dumps(payload).encode(),
        headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'})
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        rows = json.loads(resp.read().decode()).get('rows', [])
        if rows:
            rows.sort(key=lambda x: -x['impressions'])
            print(f'\n--- {label} Top Pages ---')
            for r in rows[:5]:
                p = r['keys'][0].replace('https://','').replace('http://','')[:58]
                print(f'  {p:58s}  impr={int(r["impressions"]):>5d}  clicks={int(r["clicks"]):>3d}  pos={r["position"]:>5.1f}')
    except:
        pass
