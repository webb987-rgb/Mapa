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

# --- 1. KONFIGURACIJA ---
st.set_page_config(page_title="Wolt Market Radar PRO v23", layout="wide", page_icon="📡")

# Gradovi koje si tražio
CITIES = {
    "Niš": {"coords": (43.3209, 21.8958), "slug": "nis"},
    "Beograd": {"coords": (44.7866, 20.4489), "slug": "beograd"},
    "Novi Sad": {"coords": (45.2671, 19.8335), "slug": "novi-sad"},
    "Kragujevac": {"coords": (44.0128, 20.9114), "slug": "kragujevac"}
}

DB_FILE = "radar_history.csv"
geolocator = Nominatim(user_agent="wolt_radar_v23")

# --- 2. SESSION STATE ---
if 'lat' not in st.session_state:
    st.session_state.lat, st.session_state.lon = CITIES["Niš"]["coords"]
if 'current_city' not in st.session_state:
    st.session_state.current_city = "Niš"
if 'timer_active' not in st.session_state:
    st.session_state.timer_active = False

# --- 3. FUNKCIJE ZA PODATKE ---
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

def save_snapshot(df):
    if not df.empty:
        df_save = df.copy()
        df_save['timestamp'] = datetime.datetime.now()
        if not os.path.isfile(DB_FILE):
            df_save.to_csv(DB_FILE, index=False)
        else:
            df_save.to_csv(DB_FILE, mode='a', header=False, index=False)

# --- 4. SIDEBAR ---
st.sidebar.title("📡 Kontrolna Tabla")
grad_naziv = st.sidebar.selectbox("Izaberi grad:", list(CITIES.keys()))

if grad_naziv != st.session_state.current_city:
    st.session_state.current_city = grad_naziv
    st.session_state.lat, st.session_state.lon = CITIES[grad_naziv]["coords"]
    st.cache_data.clear()
    st.rerun()

adresa_input = st.sidebar.text_input("📍 Pretraga adrese:", placeholder="npr. Knjaževačka 147")
if st.sidebar.button("🔍 Lociraj"):
    try:
        loc = geolocator.geocode(f"{adresa_input}, {grad_naziv}, Serbia")
        if loc:
            st.session_state.lat, st.session_state.lon = loc.latitude, loc.longitude
            st.cache_data.clear()
            st.rerun()
    except: st.sidebar.error("Nije nađeno.")

st.sidebar.markdown("---")
if st.sidebar.button("💾 SNIMI ZA ANALIZU PRODAJE"):
    df_current = fetch_wolt_data(st.session_state.lat, st.session_state.lon, CITIES[grad_naziv]["slug"])
    save_snapshot(df_current)
    st.sidebar.success("Podaci arhivirani!")

st.sidebar.markdown("---")
interval = st.sidebar.number_input("Auto-refresh (min):", 1, 60, 5)
if st.sidebar.button("▶️ START REFRESH"): st.session_state.timer_active = True
if st.sidebar.button("⏹️ STOP"): st.session_state.timer_active = False
if st.session_state.timer_active:
    st_autorefresh(interval=interval*60000, key="radar_rfrsh")

# --- 5. GLAVNI TABOVI ---
tab1, tab2, tab3 = st.tabs(["🟢 Otvoreno / Zatvoreno", "📈 Traffic Tracker", "☁️ Service Cloud"])

df_main = fetch_wolt_data(st.session_state.lat, st.session_state.lon, CITIES[grad_naziv]["slug"])

# --- TAB 1: RADAR MAPA (OSNOVNI PREGLED) ---
with tab1:
    st.title(f"📍 Radar Stanje: {grad_naziv}")
    if not df_main.empty:
        c1, c2, c3 = st.columns(3)
        c1.metric("Ukupno", len(df_main))
        c2.metric("Otvoreno 🟢", len(df_main[df_main['Online'] == True]))
        c3.metric("Zatvoreno 🔴", len(df_main[df_main['Online'] == False]))

        m1 = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=14)
        folium.Marker([st.session_state.lat, st.session_state.lon], icon=folium.Icon(color='blue', icon='home')).add_to(m1)
        for _, r in df_main.iterrows():
            boja = "green" if r['Online'] else "red"
            folium.CircleMarker([r['Lat'], r['Lon']], radius=7, color=boja, fill=True, tooltip=r['Ime']).add_to(m1)
        
        resp = st_folium(m1, width="100%", height=500, key="tab1_map")
        if resp and resp.get("last_clicked"):
            st.session_state.lat, st.session_state.lon = resp["last_clicked"]["lat"], resp["last_clicked"]["lng"]
            st.cache_data.clear()
            st.rerun()

        st.dataframe(df_main[["Ime", "Status", "Ocena", "Wolt Link"]], use_container_width=True, hide_index=True,
                     column_config={"Wolt Link": st.column_config.LinkColumn("Direktan Link", display_text="Otvori 🔗")})

# --- TAB 2: TRAFFIC TRACKER (ANALIZA PORUDŽBINA) ---
with tab2:
    st.title("📈 Procena prodaje")
    if os.path.exists(DB_FILE):
        h = pd.read_csv(DB_FILE)
        h['timestamp'] = pd.to_datetime(h['timestamp'])
        ts = sorted(h['timestamp'].unique())
        if len(ts) >= 2:
            df_now = h[h['timestamp'] == ts[-1]]
            df_pre = h[h['timestamp'] == ts[-2]]
            m = pd.merge(df_now, df_prev := df_pre, on="Ime", suffixes=('_sad', '_pre'))
            m['Nove_Ocene'] = m['Broj_Ocena_sad'] - m['Broj_Ocena_pre']
            m['Procena_Porudžbina'] = m['Nove_Ocene'] * 10
            st.subheader(f"Rast od {ts[-2].strftime('%H:%M')} do {ts[-1].strftime('%H:%M')}")
            st.dataframe(m[m['Nove_Ocene'] > 0].sort_values(by='Nove_Ocene', ascending=False)[["Ime", "Nove_Ocene", "Procena_Porudžbina"]], use_container_width=True)
        else: st.warning("Snimi podatke bar 2 puta u toku dana.")
    else: st.info("Baza je prazna. Klikni 'Snimi' u sidebar-u.")

# --- TAB 3: SERVICE CLOUD (TVOJA LOGIKA OBLAKA) ---
with tab3:
    st.title("☁️ Mapa efikasnosti pokrivenosti")
    st.write("Zeleno = Najjača ponuda | Crveno = Rubna zona")
    
    m_cloud = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=13, tiles="cartodbpositron")
    
    if not df_main.empty:
        df_active = df_main[df_main['Online'] == True]
        heat_points = []
        for _, r in df_active.iterrows():
            lat, lon = r['Lat'], r['Lon']
            heat_points.append([lat, lon, 1.0]) # Epicentar
            for angle in range(0, 360, 45):
                rad = np.radians(angle)
                heat_points.append([lat + 0.007 * np.cos(rad), lon + 0.009 * np.sin(rad), 0.6]) # 800m
                heat_points.append([lat + 0.018 * np.cos(rad), lon + 0.022 * np.sin(rad), 0.2]) # 2km
        
        HeatMap(heat_points, radius=40, blur=25, gradient={0.2: 'red', 0.5: 'yellow', 1.0: 'green'}, min_opacity=0.2).add_to(m_cloud)
        folium_static(m_cloud, width=1200)
