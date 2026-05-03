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
st.set_page_config(page_title="Wolt Market Radar PRO v25", layout="wide", page_icon="📡")

CITIES = {
    "Niš": {"coords": (43.3209, 21.8958), "slug": "nis"},
    "Beograd": {"coords": (44.7866, 20.4489), "slug": "beograd"},
    "Novi Sad": {"coords": (45.2671, 19.8335), "slug": "novi-sad"},
    "Kragujevac": {"coords": (44.0128, 20.9114), "slug": "kragujevac"}
}

DB_FILE = "radar_history.csv"
geolocator = Nominatim(user_agent="wolt_beast_v25")

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
                        # EKSTRAKCIJA KUHINJA/TAGOVA
                        cats = v.get("categories", [])
                        kuhinje_list = [c.get("name") for c in cats]
                        if not kuhinje_list: kuhinje_list = v.get("tags", [])
                        
                        restorani.append({
                            "Ime": v.get("name"),
                            "Kuhinja": kuhinje_list,
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
        df_save['timestamp'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        if not os.path.isfile(DB_FILE):
            df_save.to_csv(DB_FILE, index=False)
        else:
            df_save.to_csv(DB_FILE, mode='a', header=False, index=False)

# --- 4. SIDEBAR KONTROLE ---
st.sidebar.title("🛠️ Kontrolna Tabla")
grad_naziv = st.sidebar.selectbox("Izaberi grad:", list(CITIES.keys()))

if grad_naziv != st.session_state.current_city:
    st.session_state.current_city = grad_naziv
    st.session_state.lat, st.session_state.lon = CITIES[grad_naziv]["coords"]
    st.cache_data.clear()
    st.rerun()

st.sidebar.markdown("---")
if st.sidebar.button("💾 SNIMI ZA ANALIZU PRODAJE"):
    df_cur = fetch_wolt_data(st.session_state.lat, st.session_state.lon, CITIES[grad_naziv]["slug"])
    save_snapshot(df_cur)
    st.sidebar.success("Snimljeno u bazu!")

st.sidebar.markdown("---")
interval = st.sidebar.number_input("Auto-refresh (min):", 1, 60, 5)
if st.sidebar.button("▶️ START REFRESH"): st.session_state.timer_active = True
if st.sidebar.button("⏹️ STOP"): st.session_state.timer_active = False

if st.session_state.timer_active:
    st_autorefresh(interval=interval*60000, key="global_refresh")

# --- 5. GLAVNI PANEL (TABOVI) ---
tab1, tab2, tab3, tab4 = st.tabs(["🟢 Radar", "📉 Analiza ponude", "📈 Traffic Tracker", "☁️ Service Cloud"])

df_main = fetch_wolt_data(st.session_state.lat, st.session_state.lon, CITIES[grad_naziv]["slug"])

# --- TAB 1: OPERATIVNI RADAR ---
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
        
        resp = st_folium(m1, width="100%", height=600, key="map_t1")
        if resp and resp.get("last_clicked"):
            st.session_state.lat, st.session_state.lon = resp["last_clicked"]["lat"], resp["last_clicked"]["lng"]
            st.cache_data.clear()
            st.rerun()

        st.dataframe(df_main[["Ime", "Status", "Ocena", "Kuhinja_Detalji"]], use_container_width=True, hide_index=True)

# --- TAB 2: ANALIZA PONUDE (FILTERI KUHINJA) ---
with tab2:
    st.title("🔎 Analiza po vrsti kuhinje")
    if not df_main.empty:
        flat_list = [item for sublist in df_main['Kuhinja'] for item in sublist]
        sve_kuhinje = sorted(list(set(flat_list)))
        izbor = st.selectbox("Filtriraj mapu i tabelu po kuhinji:", ["Sve"] + sve_kuhinje)
        
        df_f = df_main[df_main['Kuhinja'].apply(lambda x: izbor in x)] if izbor != "Sve" else df_main

        col1, col2 = st.columns(2)
        col1.metric(f"Broj restorana ({izbor})", len(df_f))
        col2.metric("Prosečna Ocena", round(df_f['Ocena'].mean(), 2) if not df_f.empty else 0)

        m_f = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=14)
        for _, r in df_f.iterrows():
            folium.Marker([r['Lat'], r['Lon']], tooltip=f"{r['Ime']} | {r['Kuhinja_Detalji']}", 
                          icon=folium.Icon(color="blue" if r['Online'] else "red", icon="cutlery", prefix='fa')).add_to(m_f)
        st_folium(m_f, width="100%", height=500, key="map_t2")
        st.dataframe(df_f[["Ime", "Kuhinja_Detalji", "Status", "Ocena", "Broj_Ocena", "Wolt Link"]], 
                     use_container_width=True, hide_index=True,
                     column_config={"Wolt Link": st.column_config.LinkColumn("Link", display_text="Otvori 🔗")})

# --- TAB 3: TRAFFIC TRACKER (ANALIZA PRODAJE) ---
with tab3:
    st.title("📈 Procena prodaje")
    if os.path.exists(DB_FILE):
        h = pd.read_csv(DB_FILE)
        h['timestamp'] = pd.to_datetime(h['timestamp'], errors='coerce')
        h = h.dropna(subset=['timestamp'])
        ts = sorted(h['timestamp'].unique())
        
        if len(ts) >= 2:
            t_now, t_pre = ts[-1], ts[-2]
            df_now = h[h['timestamp'] == t_now].copy()
            df_pre = h[h['timestamp'] == t_pre].copy()
            df_now['Broj_Ocena'] = pd.to_numeric(df_now['Broj_Ocena'], errors='coerce').fillna(0)
            df_pre['Broj_Ocena'] = pd.to_numeric(df_pre['Broj_Ocena'], errors='coerce').fillna(0)
            
            m = pd.merge(df_now, df_pre, on="Ime", suffixes=('_sad', '_pre'))
            m['Nove_Ocene'] = m['Broj_Ocena_sad'] - m['Broj_Ocena_pre']
            m['Procena_Porudžbina'] = m['Nove_Ocene'] * 10
            
            st.subheader(f"Analiza: {t_pre.strftime('%H:%M')} -> {t_now.strftime('%H:%M')}")
            res = m[m['Nove_Ocene'] > 0].sort_values(by='Nove_Ocene', ascending=False)
            st.dataframe(res[["Ime", "Nove_Ocene", "Procena_Porudžbina"]], use_container_width=True, hide_index=True)
        else: st.warning("Snimi podatke bar dva puta u bazu.")
    else: st.info("Baza je prazna. Koristi dugme u Sidebaru.")

# --- TAB 4: SERVICE CLOUD (VELIKA MAPA POKRIVENOSTI) ---
with tab4:
    st.title("☁️ Service Cloud: Big Screen Analitika")
    m_cloud = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=13, tiles="cartodbpositron")
    if not df_main.empty:
        df_active = df_main[df_main['Online'] == True]
        heat_points = []
        for _, r in df_active.iterrows():
            lat, lon = r['Lat'], r['Lon']
            heat_points.append([lat, lon, 1.0])
            for angle in range(0, 360, 45):
                rad = np.radians(angle)
                heat_points.append([lat + 0.007 * np.cos(rad), lon + 0.009 * np.sin(rad), 0.6])
                heat_points.append([lat + 0.018 * np.cos(rad), lon + 0.022 * np.sin(rad), 0.2])
        if heat_points:
            HeatMap(heat_points, radius=45, blur=30, gradient={0.2: 'red', 0.5: 'yellow', 1.0: 'green'}, min_opacity=0.2).add_to(m_cloud)
        folium_static(m_cloud, width=1400, height=800)
