import json, urllib.request
r = urllib.request.Request("http://127.0.0.1:7875/api/voice/save",
    data=json.dumps({"rows":"few","len":"long"}).encode(),
    headers={"Content-Type":"application/json"})
print("  ", urllib.request.urlopen(r, timeout=15).read().decode())
