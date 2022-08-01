import requests
import json
import time
import mariadb
import sys

cano_rrule_week=""
cano_rrule_month=""
cano_rrule_spec=""
rdowntime_id_dict = {}


days_of_weeks = {
  "1": "MO",
  "2": "TU",
  "3": "WE",
  "4": "TH",
  "5": "FR",
  "6": "SA",
  "7": "SU"
}

spec_week_day = {
  "first": "1",
  "second": "2",
  "third": "3",
  "fourth": "4",
  "last": "-1"
}

# WE,MO,TU,TH,FR,SA,SU
url_auth = "http://192.168.10.70/centreon/api/index.php?action=authenticate"

payload={
    'username': 'apicall',
    'password': 'nFM$UnppLZ96'
}

files=[
]

headers = {
  'Accept': 'application/x-www-form-urlencoded'
}

token_req = requests.request("POST", url_auth, headers=headers, data=payload, files=files)

token = json.loads(token_req.text)
url_clapi = "http://192.168.10.70/centreon/api/index.php?action=action&object=centreon_clapi"

api_dt_list = json.dumps({
  "action": "SHOW",
  "object": "DOWNTIME"
})


headers_clapi = {
  'centreon-auth-token': token['authToken'],
  'Content-Type': 'application/json'
}

resp = requests.request("POST", url_clapi, headers=headers_clapi, data=api_dt_list)

downtime_list = json.loads(resp.text)['result']

for dt in downtime_list:
    if dt['activate'] == "1":
        payload_period_list = json.dumps({
            "action": "listperiods",
            "object": "DOWNTIME",
            "values": dt['name']
        })
        response = requests.request("POST", url_clapi, headers=headers_clapi, data=payload_period_list)

        recurence = json.loads(response.text)['result']
        
        for r in recurence:
            #check if this rr is weekly
            if r['month cycle'] == "all" and r['day of month'] == "":
                cano_rrule= "RRULE:FREQ=WEEKLY;BYDAY="
                for d in r['day of week'].split(','):
                    cano_rrule += days_of_weeks[d] + ","
                
                cano_rrule = cano_rrule.strip(',')

            #check if this rr is monthly
            if r['month cycle'] == "none" and r['day of week'] == "":
                cano_rrule = "RRULE:FREQ=MONTHLY;BYMONTHDAY=" + r['day of month']

            #check if this rr is spec 
            if r['month cycle'] != 'none' and r['month cycle'] != 'all':
                cano_rrule = 'RRULE:FREQ=MONTHLY;BYDAY='
                cano_rrule += days_of_weeks["1"] + ";BYSETPOS="
                cano_rrule += spec_week_day[r['month cycle']]
                
        rdowntime_id_dict.update({ dt['id']: { 'rrule': cano_rrule,'tstart':'','tstop':'','filter':'','comment':'','enable': True,'type':'Maintenance','name':'','author':'','_id':'', 'svc_dep': [], 'host_dep': [] }})

#connection to centreon bdd to get recurent downtime config centreon api is shitty

try:
    conn = mariadb.connect(
        user="centreon",
        password="mike1984",
        host="192.168.10.70",
        port=3306,
        database="centreon"

    )
except mariadb.Error as e:
    print(f"Error connecting centreon bdd: {e}")
    sys.exit(1)


# Get Cursor
cur = conn.cursor()

# get host dt relation to rdt id
cur.execute(
    "SELECT dthr.dt_id, h.host_name  FROM downtime d, host h, downtime_host_relation dthr WHERE \
        h.host_id = dthr.host_host_id AND d.dt_activate = '1' AND d.dt_id = dthr.dt_id")

host_dep=[]

for rdth in cur:
    rdowntime_id_dict[str(rdth[0])]['host_dep'].append(rdth[1])
    host_dep.append(rdth)


cur.execute(
    "SELECT dtsr.dt_id, h.host_name, s.service_description FROM \
        downtime d, host h, service s,downtime_service_relation dtsr WHERE \
            h.host_id = dtsr.host_host_id AND s.service_id = dtsr.service_service_id AND \
                d.dt_activate = '1' AND dtsr.dt_id = d.dt_id")


for rdts in cur:
    # if no downtime on host we can add service dependency
    if len(host_dep) == 0:
        rdowntime_id_dict[str(rdts[0])]['svc_dep'].append(rdts[2] + '/' + rdts[1])
        
    for h_exclusion in host_dep:
        if rdts[0] == h_exclusion[0]  and rdts[1] == h_exclusion[1]:
            print("host is in downtime for this recurrent downtime no need to add")
        else:
            rdowntime_id_dict[str(rdts[0])]['svc_dep'].append(rdts[2] + '/' + rdts[1])


print(rdowntime_id_dict)


# build api v4 pdh object canopsis

