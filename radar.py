# --- SKREPER: WOLT ---
def fetch_wolt(lat, lon, city_slug):
    url = "https://restaurant-api.wolt.com/v1/pages/restaurants"
    try:
        r = requests.get(url, params={"lat": lat, "lon": lon}, impersonate="chrome120", timeout=10)
        res = [] # Inicijalizujemo praznu listu na početku
        if r.status_code == 200:
            data = r.json()
            for sec in data.get("sections", []):
                for item in sec.get("items", []):
                    v = item.get("venue")
                    if v:
                        res.append({
                            "Ime": v.get("name"),
                            "Status": "Otvoreno 🟢" if v.get("online") else "Zatvoreno 🔴",
                            "Online": v.get("online", False),
                            "Ocena": v.get("rating", {}).get("score", "-"),
                            "Platforma": "Wolt",
                            "Link": f"https://wolt.com/sr/srb/{city_slug}/restaurant/{v.get('slug')}",
                            "Lat": v.get("location", [0, 0])[1],
                            "Lon": v.get("location", [0, 0])[0]
                        })
        return res # Uvek vraćamo listu (praznu ili punu)
    except Exception as e:
        print(f"Wolt Error: {e}")
        return []

# --- SKREPER: MISTER D ---
def fetch_mister_d(lat, lon):
    url = "https://api.misterd.rs/api/v2/consumer/order" 
    params = {"lat": lat, "lng": lon, "onlyActive": "true"}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://misterd.rs/"
    }
    try:
        r = requests.get(url, params=params, headers=headers, impersonate="chrome120", timeout=10)
        res = [] # Inicijalizujemo praznu listu
        if r.status_code == 200:
            data = r.json()
            # Proveravamo putanju do podataka (Mister D nekad menja strukturu)
            venues = data.get("data", {}).get("venues", [])
            for v in venues:
                res.append({
                    "Ime": v.get("name"),
                    "Status": "Otvoreno 🟢" if v.get("is_open") else "Zatvoreno 🔴",
                    "Online": v.get("is_open", False),
                    "Ocena": v.get("rating", "-"),
                    "Platforma": "Mister D",
                    "Link": f"https://misterd.rs/restoran/{v.get('slug')}",
                    "Lat": float(v.get("latitude", 0)),
                    "Lon": float(v.get("longitude", 0))
                })
        return res # Uvek vraćamo listu
    except Exception as e:
        print(f"Mister D Error: {e}")
        return []
