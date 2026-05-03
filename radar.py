import streamlit as st
from curl_cffi import requests
import pandas as pd
import folium
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim
from streamlit_autorefresh import st_autorefresh
import datetime

# --- KONFIGURACIJA ---
st.set_page_config(page_title="Multi-Platform Radar v14", layout="wide", page_icon="📡")

CITIES = {
    "Niš": {"coords": (43.3209, 21.8958), "wolt_slug": "nis", "md_id": "nis"},
    "Beograd": {"coords": (44.7866, 20.4489), "wolt_slug": "beograd", "md_id": "beograd"},
    "Novi Sad": {"coords": (45.2671, 19.8335), "wolt_slug": "novi-sad", "md_id": "novi-sad"}
}

geolocator = Nominatim(user_agent="radar_dual_v14")

if 'lat' not in st.session_state:
    st.session_state.lat, st.session_state.lon = CITIES["Niš"]["coords"]
if 'current_city' not in st.session_state:
    st.session_state.current_city = "Niš"

# --- SKREPER: WOLT ---
def fetch_wolt(lat, lon, city_slug):
    url = "https://restaurant-api.wolt.com/v1/pages/restaurants"
    try:
        r = requests.get(url, params={"lat": lat, "lon": lon}, impersonate="chrome120", timeout=10)
        if r.status_code == 200:
            res = []
            for sec in r.json().get("sections", []):
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
            return res
    except: return []

# --- SKREPER: MISTER D (Novo!) ---
def fetch_mister_d(lat, lon):
    # Endpoint koji si našao u Network tabu
    url = "https://api.misterd.rs/api/v2/consumer/order" 
    params = {
        "lat": lat,
        "lng": lon,
        "onlyActive": "true"
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0",
        "Referer": "https://misterd.rs/"
    }
    try:
        r = requests.get(url, params=params, impersonate="chrome120", timeout=10)
        if r.status_code == 200:
            data = r.json()
            res = []
            # Mister D struktura (podešena prema API odgovorima)
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
            return res
    except: return []

# --- SIDEBAR ---
st.sidebar.title("📡 Radar Postavke")
grad_naziv = st.sidebar.selectbox("Grad:", list(CITIES.keys()))
platforma = st.sidebar.radio("Platforma:", ["Sve zajedno", "Samo Wolt", "Samo Mister D"])

if grad_naziv != st.session_state.current_city:
    st.session_state.current_city = grad_naziv
    st.session_state.lat, st.session_state.lon = CITIES[grad_naziv]["coords"]
    st.rerun()

# --- PODACI ---
all_data = []
if platforma in ["Sve zajedno", "Samo Wolt"]:
    all_data.extend(fetch_wolt(st.session_state.lat, st.session_state.lon, CITIES[grad_naziv]["wolt_slug"]))
if platforma in ["Sve zajedno", "Samo Mister D"]:
    all_data.extend(fetch_mister_d(st.session_state.lat, st.session_state.lon))

df = pd.DataFrame(all_data).drop_duplicates(subset=['Ime'])

# --- PANEL ---
st.title(f"📍 {platforma}: {grad_naziv}")

if not df.empty:
    c1, c2, c3 = st.columns(3)
    c1.metric("Ukupno restorana", len(df))
    c2.metric("Wolt", len(df[df['Platforma'] == "Wolt"]))
    c3.metric("Mister D", len(df[df['Platforma'] == "Mister D"]))

    # MAPA
    m = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=15)
    
    for _, r in df.iterrows():
        # Boja markera: Wolt Plava/Zelena, Mister D Crvena/Narandžasta
        if r['Platforma'] == "Wolt":
            boja = "blue" if r['Online'] else "lightgray"
        else:
            boja = "orange" if r['Online'] else "darkred"
            
        folium.Marker(
            [r['Lat'], r['Lon']], 
            tooltip=f"{r['Ime']} ({r['Platforma']})",
            icon=folium.Icon(color=boja, icon="cutlery", prefix="fa")
        ).add_to(m)

    st_folium(m, width="100%", height=500)

    # TABELA
    st.dataframe(
        df[["Ime", "Platforma", "Status", "Ocena", "Link"]],
        use_container_width=True,
        hide_index=True,
        column_config={"Link": st.column_config.LinkColumn("Link", display_text="Otvori 🔗")}
    )
