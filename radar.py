import streamlit as st
from curl_cffi import requests
import pandas as pd
import folium
from folium.plugins import HeatMap
from streamlit_folium import st_folium, folium_static 
from geopy.geocoders import Nominatim
from streamlit_autorefresh import st_autorefresh
import numpy as np
import datetime
import os
import csv
import streamlit.components.v1 as components

# --- 1. KONFIGURACIJA ---
st.set_page_config(page_title="Wolt BI Radar v26.3 DEBUG", layout="wide", page_icon="📡")

CITIES = {
    "Niš": {"coords": (43.3209, 21.8958), "slug": "nis"},
    "Beograd": {"coords": (44.7866, 20.4489), "slug": "beograd"},
    "Novi Sad": {"coords": (45.2671, 19.8335), "slug": "novi-sad"},
    "Kragujevac": {"coords": (44.0128, 20.9114), "slug": "kragujevac"}
}

DB_FILE = "radar_history.csv"
geolocator = Nominatim(user_agent="wolt_bi_radar_v26_3")

# --- 2. SESSION STATE ---
if 'lat' not in st.session_state:
    st.session_state.lat, st.session_state.lon = CITIES["Niš"]["coords"]
if 'current_city' not in st.session_state:
    st.session_state.current_city = "Niš"

# --- 3. SKREPER (Sa Dijagnostikom) ---
@st.cache_data(ttl=60)
def fetch_wolt_data(lat, lon, city_slug):
    prazan_df = pd.DataFrame(columns=["Ime", "Wolt Link", "Kuhinja_Raw", "Kuhinja_Detalji", "Lat", "Lon", "Status", "Online", "Ocena", "Broj_Ocena"])
    url = "https://restaurant-api.wolt.com/v1/pages/restaurants"
    
    try:
        r = requests.get(url, params={"lat": lat, "lon": lon}, impersonate="chrome120", timeout=15)
        
        # DEBUG INFO (Samo ako nema podataka)
        if r.status_code != 200:
            st.error(f"❌ Wolt API odbio zahtev. Status kod: {r.status_code}")
            return prazan_df
        
        data = r.json()
        sections = data.get("sections", [])
        
        if not sections:
            st.warning("⚠️ Wolt je vratio odgovor, ali nema nijedne sekcije sa restoranima. Proveri lokaciju.")
            return prazan_df

        restorani = []
        for section in sections:
            # Wolt nekad stavlja restorane u 'items', nekad u 'templates'
            items = section.get("items", [])
            for item in items:
                v = item.get("venue")
                if v:
                    cats = v.get("categories", [])
                    kuhinje = [c.get("name") for c in cats]
                    if not kuhinje: kuhinje = v.get("tags", [])
                    
                    restorani.append({
                        "Ime": v.get("name"),
                        "Wolt Link": f"https://wolt.com/sr/srb/{city_slug}/restaurant/{v.get('slug')}",
                        "Kuhinja_Raw": kuhinje,
                        "Kuhinja_Detalji": ", ".join(kuhinje) if kuhinje else "Ostalo",
                        "Lat": float(v.get("location", [0, 0])[1]),
                        "Lon": float(v.get("location", [0, 0])[0]),
                        "Status": "Otvoreno 🟢" if v.get("online") else "Zatvoreno 🔴",
                        "Online": v.get("online", False),
                        "Ocena": v.get("rating", {}).get("score", 0),
                        "Broj_Ocena": int(v.get("rating", {}).get("volume", 0))
                    })
        
        if not restorani:
            st.info("🔎 API je povezan, ali nije pronađen nijedan restoran na ovim koordinatama.")
            return prazan_df

        return pd.DataFrame(restorani).drop_duplicates(subset=['Ime'])
    
    except Exception as e:
        st.error(f"🚨 Kritična greška u skreperu: {e}")
        return prazan_df

# --- 4. OSTATAK KODA (Standardni panel) ---
# ... (ovde ide tvoj regularni sidebar i tabovi iz v26.2) ...

# SAMO DODAJ OVO ISPOD fetch_wolt_data DA BI VIDEO REZULTATE:
df_raw = fetch_wolt_data(st.session_state.lat, st.session_state.lon, CITIES[grad_naziv]["slug"])
# (Dalje nastavi sa iscrtavanjem tabova kao u v26.2)
