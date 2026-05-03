import streamlit as st
from curl_cffi import requests
import pandas as pd
import folium
from streamlit_folium import st_folium, folium_static 
from geopy.geocoders import Nominatim
import datetime
import os

# --- 1. KONFIGURACIJA ---
st.set_page_config(page_title="Wolt Concentric Radar v20", layout="wide", page_icon="🎯")

CITIES = {
    "Niš": {"coords": (43.3209, 21.8958), "slug": "nis"},
    "Beograd": {"coords": (44.7866, 20.4489), "slug": "beograd"},
    "Novi Sad": {"coords": (45.2671, 19.8335), "slug": "novi-sad"}
}

DB_FILE = "radar_history.csv"
geolocator = Nominatim(user_agent="wolt_radar_v20")

# --- 2. SESSION STATE ---
if 'lat' not in st.session_state:
    st.session_state.lat, st.session_state.lon = CITIES["Niš"]["coords"]
if 'current_city' not in st.session_state:
    st.session_state.current_city = "Niš"

# --- 3. SKREPER ---
@st.cache_data(ttl=60)
def fetch_wolt_data(lat, lon, city_slug):
    url = "https://restaurant-api.wolt.com/v1/pages/restaurants"
    params = {"lat": lat, "lon": lon}
    try:
        r = requests.get(url, params=params, impersonate="chrome120", timeout=15)
        if r.status_code == 200:
            data = r.json()
            restorani = []
            for section in data.get("sections", []):
                for item in section.get("items", []):
                    v = item.get("venue")
                    if v:
                        restorani.append({
                            "Ime": v.get("name"),
                            "Lat": float(v.get("location", [0, 0])[1]),
                            "Lon": float(v.get("location", [0, 0])[0]),
                            "Status": "Otvoreno 🟢" if v.get("online") else "Zatvoreno 🔴",
                            "Online": v.get("online", False),
                            "Ocena": v.get("rating", {}).get("score", 0),
                            "Broj_Ocena": v.get("rating", {}).get("volume", 0),
                            "Wolt Link": f"https://wolt.com/sr/srb/{city_slug}/restaurant/{v.get('slug')}"
                        })
            return pd.DataFrame(restorani).drop_duplicates(subset=['Ime'])
    except: pass
    return pd.DataFrame()

# --- 4. SIDEBAR ---
st.sidebar.title("🛠️ Kontrola")
grad_naziv = st.sidebar.selectbox("Izaberi grad:", list(CITIES.keys()))

if grad_naziv != st.session_state.current_city:
    st.session_state.current_city = grad_naziv
    st.session_state.lat, st.session_state.lon = CITIES[grad_naziv]["coords"]
    st.cache_data.clear()
    st.rerun()

if st.sidebar.button("💾 SNIMI ZA TRAFFIC"):
    df_s = fetch_wolt_data(st.session_state.lat, st.session_state.lon, CITIES[grad_naziv]["slug"])
    if not df_s.empty:
        df_s['timestamp'] = datetime.datetime.now()
        df_s.to_csv(DB_FILE, mode='a', header=not os.path.exists(DB_FILE), index=False)
        st.sidebar.success("Podaci sačuvani!")

# --- 5. TABOVI ---
tab1, tab2, tab3 = st.tabs(["🟢 Otvoreno / Zatvoreno", "🎯 Zone Dostupnosti", "📈 Traffic Tracker"])

df_main = fetch_wolt_data(st.session_state.lat, st.session_state.lon, CITIES[grad_naziv]["slug"])

# --- TAB 1: RADAR (Standardni pregled) ---
with tab1:
    st.title(f"📊 Radar: {grad_naziv}")
    if not df_main.empty:
        c1, c2, c3 = st.columns(3)
        c1.metric("Ukupno", len(df_main))
        c2.metric("Otvoreno", len(df_main[df_main['Online'] == True]))
        c3.metric("Zatvoreno", len(df_main[df_main['Online'] == False]))

        m1 = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=14)
        folium.Marker([st.session_state.lat, st.session_state.lon], icon=folium.Icon(color='blue', icon='home')).add_to(m1)
        for _, r in df_main.iterrows():
            boja = "green" if r['Online'] else "red"
            folium.CircleMarker([r['Lat'], r['Lon']], radius=7, color=boja, fill=True, tooltip=r['Ime']).add_to(m1)
        
        resp = st_folium(m1, width="100%", height=500, key="radar_v20")
        if resp and resp.get("last_clicked"):
            st.session_state.lat, st.session_state.lon = resp["last_clicked"]["lat"], resp["last_clicked"]["lng"]
            st.cache_data.clear()
            st.rerun()
        
        st.dataframe(df_main[["Ime", "Status", "Ocena", "Wolt Link"]], use_container_width=True, hide_index=True)

# --- TAB 2: KONCENTRIČNE ZONE (Tvoja nova logika) ---
with tab2:
    st.title("🎯 Geografija Pokrivenosti")
    st.write("Što je zona tamnija, to je više restorana dostupno na toj distanci.")
    
    m2 = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=13)
    folium.Marker([st.session_state.lat, st.session_state.lon], icon=folium.Icon(color='black')).add_to(m2)

    if not df_main.empty:
        df_active = df_main[df_main['Online'] == True].copy()
        
        # Definicija krugova (Od najvećeg ka najmanjem da bi se manji videli "preko")
        # Radi se obrnuto: Maroon (3km) -> Bordo -> Dark Red -> Light Red -> Orange -> Yellow -> Green
        zones = [
            {"r": 3000, "c": "#800000", "label": "Bordo (3km)"},      # Bordo
            {"r": 2500, "c": "#b30000", "label": "Tamno crvena (2.5km)"}, # Tamno crvena
            {"r": 2000, "c": "#ff4d4d", "label": "Svetlo crvena (2km)"}, # Svetlo crvena
            {"r": 1500, "c": "#ffa500", "label": "Narandžasta (1.5km)"}, # Narandžasta
            {"r": 1000, "c": "#ffff00", "label": "Žuta (1km)"},          # Žuta
            {"r": 500,  "c": "#008000", "label": "Zelena (500m)"}        # Zelena
        ]

        for _, r in df_active.iterrows():
            # Za svaki restoran crtamo svih 6 krugova
            for zone in zones:
                folium.Circle(
                    location=[r['Lat'], r['Lon']],
                    radius=zone['r'],
                    color=zone['c'],
                    weight=1,
                    fill=True,
                    fill_color=zone['c'],
                    fill_opacity=0.03, # Jako niska providnost da bi se slojevi lepo sabirali
                    tooltip=f"{r['Ime']} - {zone['label']}"
                ).add_to(m2)

    folium_static(m2, width=1200)

# --- TAB 3: TRAFFIC ---
with tab3:
    st.title("📈 Traffic Tracker")
    if os.path.exists(DB_FILE):
        h = pd.read_csv(DB_FILE)
        st.success("Podaci su u bazi. Uporedi snimke za analizu prodaje.")
    else: st.info("Baza je prazna.")
