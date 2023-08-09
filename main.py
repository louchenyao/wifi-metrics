#! /usr/bin/env python3

import os
import subprocess
import threading
import time

from dotenv import load_dotenv
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

load_dotenv()

token = os.getenv('INFLUXDB_TOKEN')
org = os.getenv('INFLUXDB_ORG')
bucket = os.getenv('INFLUXDB_BUCKET')
url = os.getenv('INFLUXDB_URL')


def airport_get_info():
    cmd = "/System/Library/PrivateFrameworks/Apple80211.framework/Versions/A/Resources/airport -I"
    result = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        return None
    
    # parse output
    output = result.stdout.decode('utf-8').strip().splitlines()
    info = {}
    for line in output:
        pair= line.split(": ")
        if len(pair) == 2:
            key, value = pair
        elif len(pair) == 1:
            key = pair[0]
            value = ""
        else:
            continue
        info[key.strip()] = value.strip()
    return info

def ping(host):
    """ Returns latency if host (str) responds to a ping request. Else returns None
    """
    # ping once with 1 second timeout
    cmd = "ping -c 1 -t 1 " + host
    result = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode == 0:
        return float(result.stdout.decode('utf-8').split("time=")[1].split(" ms")[0])
    else:
        return None

def gateway_ip():
    cmd = "netstat -nr | grep default | grep -E -o \"([0-9]{1,3}[\.]){3}[0-9]{1,3}\""
    result = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode == 0:
        return result.stdout.decode('utf-8').strip()
    else:
        return None

def hostname():
    return subprocess.run("hostname", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.decode('utf-8').strip()

def sleep(last_time, interval):
    """ Sleep until the next interval, return the wake up time
    """
    rem = interval - (time.time() - last_time)
    if rem > 0:
        time.sleep(rem)
    return time.time()

def ping_and_upload():
    interval = 0.5
    last_time = 0
    host = hostname()
    client = InfluxDBClient(url=url, token=token, org=org)
    write_api = client.write_api(write_options=SYNCHRONOUS)
    while True:
        last_time = sleep(last_time=last_time, interval=interval)
        latency = ping(gateway_ip())
        print(f"latency: {latency} ms")
        if latency is None:
            latency = 999.0 # set to 999 if ping fails

        # write to influxdb
        point = (
            Point("latency")
            .tag("host", host)
            .field("latency", latency)
        )
        write_api.write(bucket=bucket, org=org, record=point)

def get_info_and_upload():
    interval = 0.5
    last_time = 0
    host = hostname()
    client = InfluxDBClient(url=url, token=token, org=org)
    write_api = client.write_api(write_options=SYNCHRONOUS)
    while True:
        last_time = sleep(last_time=last_time, interval=interval)
        info = airport_get_info()
        
        last_tx_rate = float(info.get("lastTxRate", 0))
        max_rate  = float(info.get("maxRate", 0))
        bssid = info.get("BSSID", "")
        rssi = float(info.get("agrCtlRSSI", 0))
        noise = float(info.get("agrCtlNoise", 0))

        print(f"last_tx_rate: {last_tx_rate} Mbps")

        # write to influxdb
        point = (
            Point("wifi")
            .tag("host", host)
            .tag("bssid", bssid)
            .field("last_tx_rate", last_tx_rate)
            .field("max_rate", max_rate)
            .field("rssi", rssi)
            .field("noise", noise)
        )
        write_api.write(bucket=bucket, org=org, record=point)

def main():
    ping_thread = threading.Thread(target=ping_and_upload)
    ping_thread.start()
    get_info_thread = threading.Thread(target=get_info_and_upload)
    get_info_thread.start()
    ping_thread.join()
    get_info_thread.join()

if __name__ == "__main__":
    main()
