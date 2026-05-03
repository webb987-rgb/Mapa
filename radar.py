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

# --- 1. KONFIGURACIJA ---
st.set_page_config(page_title="Wolt BI Radar PRO v25.1", layout="wide", page_icon="📡")

CITIES = {
    "Niš": {"coords": (43.3209, 21.8958), "slug": "nis"},
    "Beograd": {"coords": (44.7866, 20.4489), "slug": "beograd"},
    "Novi Sad": {"coords": (45.2671, 19.8335), "slug": "novi-sad"},
    "Kragujevac": {"coords": (44.0128, 20.9114), "slug": "kragujevac"}
}

DB_FILE = "radar_history.csv"
geolocator = Nominatim(user_agent="wolt_bi_beast_v25_1")

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
    try:
        r = requests.get(url, params={"lat": lat, "lon": lon}, impersonate="chrome120", timeout=15)
        if r.status_code == 200:
            restorani = []
            for section in r.json().get("sections", []):
                for item in section.get("items", []):
                    v = item.get("venue")
                    if v:
                        cats = v.get("categories", [])
                        kuhinje_list = [c.get("name") for c in cats]
                        if not kuhinje_list: kuhinje_list = v.get("tags", [])
                        
                        restorani.append({
                            "Ime": v.get("name"),
                            "Kuhinja_Raw": kuhinje_list, # Lista za internu upotrebu
                            "Kuhinja_Detalji": ", ".join(kuhinje_list) if kuhinje_list else "Ostalo",
                            "Lat": float(v.get("location", [0, 0])[1]),
                            "Lon": float(v.get("location", [0, 0])[0]),
                            "Status": "Otvoreno 🟢" if v.get("online") else "Zatvoreno 🔴",
                            "Online": v.get("online", False),
                            "Ocena": v.get("rating", {}).get("score", 0),
                            "Broj_Ocena": int(v.get("rating", {}).get("volume", 0)),
                            "ETA": v.get("estimate", 30),
                            "Wolt Link": f"https://wolt.com/sr/srb/{city_slug}/restaurant/{v.get('slug')}"
                        })
            return pd.DataFrame(restorani).drop_duplicates(subset=['Ime'])
    except: pass
    return pd.DataFrame()

def save_snapshot(df):
    if not df.empty:
        df_save = df.copy()
        # KLJUČNO: Ne snimamo listu direktno, već je brišemo ili pretvaramo u string pre CSV-a
        if 'Kuhinja_Raw' in df_save.columns:
            df_save = df_save.drop(columns=['Kuhinja_Raw'])
        
        df_save['timestamp'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Koristimo quoting da zarezi u imenima restorana ne sruše CSV
        if not os.path.isfile(DB_FILE):
            df_save.to_csv(DB_FILE, index=False, quoting=csv.QUOTE_ALL)
        else:
            df_save.to_csv(DB_FILE, mode='a', header=False, index=False, quoting=csv.QUOTE_ALL)

# --- 4. SIDEBAR ---
st.sidebar.title("🛠️ Kontrola")
grad_naziv = st.sidebar.selectbox("Izaberi grad:", list(CITIES.keys()))

if grad_naziv != st.session_state.current_city:
    st.session_state.current_city = grad_naziv
    st.session_state.lat, st.session_state.lon = CITIES[grad_naziv]["coords"]
    st.cache_data.clear()
    st.rerun()

if st.sidebar.button("💾 SNIMI SNIMAK"):
    df_cur = fetch_wolt_data(st.session_state.lat, st.session_state.lon, CITIES[grad_naziv]["slug"])
    save_snapshot(df_cur)
    st.sidebar.success("Baza ažurirana!")

interval = st.sidebar.number_input("Auto-refresh (min):", 1, 60, 5)
if st.sidebar.button("▶️ START"): st.session_state.timer_active = True
if st.sidebar.button("⏹️ STOP"): st.session_state.timer_active = False

if st.session_state.timer_active:
    st_autorefresh(interval=interval*60000, key="global_r")

# --- 5. GLAVNI PANEL ---
tab1, tab2, tab3, tab4 = st.tabs(["🟢 Radar", "📉 Analiza ponude", "📈 Traffic Tracker", "☁️ Service Cloud"])

df_main = fetch_wolt_data(st.session_state.lat, st.session_state.lon, CITIES[grad_naziv]["slug"])

# TAB 1: RADAR
with tab1:
    if not df_main.empty:
        c1, c2, c3 = st.columns(3)
        c1.metric("Ukupno", len(df_main))
        c2.metric("Otvoreno 🟢", len(df_main[df_main['Online'] == True]))
        c3.metric("Zatvoreno 🔴", len(df_main[df_main['Online'] == False]))
        m1 = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=14)
        for _, r in df_main.iterrows():
            boja = "green" if r['Online'] else "red"
            folium.CircleMarker([r['Lat'], r['Lon']], radius=7, color=boja, fill=True, tooltip=r['Ime']).add_to(m1)
        st_folium(m1, width="100%", height=600, key="m1")
        st.dataframe(df_main[["Ime", "Status", "Ocena", "Kuhinja_Detalji"]], use_container_width=True, hide_index=True)

# TAB 2: ANALIZA PONUDE
with tab2:
    if not df_main.empty:
        flat_cats = [item for sublist in df_main['Kuhinja_Raw'] for item in sublist]
        unique_cats = sorted(list(set(flat_cats)))
        izbor = st.selectbox("Vrsta hrane:", ["Sve"] + unique_cats)
        
        df_f = df_main[df_main['Kuhinja_Raw'].apply(lambda x: izbor in x)] if izbor != "Sve" else df_main
        st.metric(f"Broj {izbor} objekata", len(df_f))
        
        m2 = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=14)
        for _, r in df_f.iterrows():
            folium.Marker([r['Lat'], r['Lon']], tooltip=r['Ime'], icon=folium.Icon(color="blue", icon="cutlery", prefix='fa')).add_to(m2)
        st_folium(m2, width="100%", height=500, key="m2")
        st.dataframe(df_f[["Ime", "Kuhinja_Detalji", "Ocena", "Wolt Link"]], use_container_width=True, hide_index=True)

# TAB 3: TRAFFIC TRACKER (Sada otporan na greške)
with tab3:
    if os.path.exists(DB_FILE):
        try:
            # KLJUČNO: on_bad_lines='skip' sprečava pucanje ako je CSV korumpiran
            h = pd.read_csv(DB_FILE, on_bad_lines='skip')
            h['timestamp'] = pd.to_datetime(h['timestamp'], errors='coerce')
            h = h.dropna(subset=['timestamp'])
            ts = sorted(h['timestamp'].unique())
            
            if len(ts) >= 2:
                df_now = h[h['timestamp'] == ts[-1]].copy()
                df_pre = h[h['timestamp'] == ts[-2]].copy()
                df_now['Broj_Ocena'] = pd.to_numeric(df_now['Broj_Ocena'], errors='coerce').fillna(0)
                df_pre['Broj_Ocena'] = pd.to_numeric(df_pre['Broj_Ocena'], errors='coerce').fillna(0)
                
                m = pd.merge(df_now, df_pre, on="Ime", suffixes=('_sad', '_pre'))
                m['Nove_Ocene'] = m['Broj_Ocena_sad'] - m['Broj_Ocena_pre']
                st.subheader(f"Rast: {ts[-2].strftime('%H:%M')} -> {ts[-1].strftime('%H:%M')}")
                st.dataframe(m[m['Nove_Ocene'] > 0].sort_values(by='Nove_Ocene', ascending=False)[["Ime", "Nove_Ocene"]], use_container_width=True)
            else: st.warning("Snimi podatke bar dva puta.")
        except Exception as e: st.error(f"Greška pri čitanju baze. Obriši {DB_FILE} i probaj ponovo.")
    else: st.info("Baza je prazna.")

# TAB 4: SERVICE CLOUD
with tab4:
    m4 = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=13, tiles="cartodbpositron")
    if not df_main.empty:
        df_a = df_main[df_main['Online'] == True]
        pts = []
        for _, r in df_a.iterrows():
            pts.append([r['Lat'], r['Lon'], 1.0])
            for ang in range(0, 360, 45):
                rad = np.radians(ang)
                pts.append([r['Lat'] + 0.007 * np.cos(rad), r['Lon'] + 0.009 * np.sin(rad), 0.6])
        if pts: HeatMap(pts, radius=45, blur=30, gradient={0.2: 'red', 0.5: 'yellow', 1.0: 'green'}, min_opacity=0.2).add_to(m4)
        folium_static(m4, width=1400, height=800)
