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
st.set_page_config(page_title="Wolt BI Radar PRO v25.8", layout="wide", page_icon="📡")

CITIES = {
    "Niš": {"coords": (43.3209, 21.8958), "slug": "nis"},
    "Beograd": {"coords": (44.7866, 20.4489), "slug": "beograd"},
    "Novi Sad": {"coords": (45.2671, 19.8335), "slug": "novi-sad"},
    "Kragujevac": {"coords": (44.0128, 20.9114), "slug": "kragujevac"}
}

DB_FILE = "radar_history.csv"
geolocator = Nominatim(user_agent="wolt_bi_beast_v25_8")

# --- 2. SESSION STATE ---
if 'lat' not in st.session_state:
    st.session_state.lat, st.session_state.lon = CITIES["Niš"]["coords"]
if 'current_city' not in st.session_state:
    st.session_state.current_city = "Niš"
if 'timer_active' not in st.session_state:
    st.session_state.timer_active = False

# --- 3. SMOOTH TAJMER (JavaScript) ---
def countdown_timer(minutes):
    seconds = minutes * 60
    html_code = f"""
    <div id="timer-container" style="padding:15px; border-radius:10px; background-color:#f8f9fa; text-align:center; border: 1px solid #e9ecef; margin-bottom: 20px;">
        <p style="margin:0; font-size:0.85rem; color:#6c757d; font-family:sans-serif; text-transform: uppercase; letter-spacing: 1px;">Sledeće osvežavanje za:</p>
        <span id="timer" style="font-size:2rem; font-weight:bold; color:#00c2e8; font-family: 'Courier New', monospace;">--:--</span>
    </div>
    <script>
        var timeLeft = {seconds};
        var timerDisplay = document.getElementById('timer');
        function updateTimer() {{
            var mins = Math.floor(timeLeft / 60);
            var secs = timeLeft % 60;
            timerDisplay.innerHTML = (mins < 10 ? "0" : "") + mins + ":" + (secs < 10 ? "0" : "") + secs;
            if (timeLeft <= 0) {{ clearInterval(interval); }}
            timeLeft--;
        }}
        var interval = setInterval(updateTimer, 1000);
        updateTimer();
    </script>
    """
    return components.html(html_code, height=120)

# --- 4. FUNKCIJE ZA PODATKE ---
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
                        # Logika: Samo dostava
                        delivery_specs = v.get("delivery_specs", {})
                        is_delivery_enabled = delivery_specs.get("delivery_enabled", False)
                        is_open_for_delivery = v.get("online", False) and is_delivery_enabled
                        
                        cats = v.get("categories", [])
                        kuhinje_list = [c.get("name") for c in cats]
                        if not kuhinje_list: kuhinje_list = v.get("tags", [])
                        
                        restorani.append({
                            "Ime": v.get("name"),
                            "Wolt Link": f"https://wolt.com/sr/srb/{city_slug}/restaurant/{v.get('slug')}",
                            "Kuhinja_Raw": kuhinje_list,
                            "Kuhinja_Detalji": ", ".join(kuhinje_list) if kuhinje_list else "Ostalo",
                            "Lat": float(v.get("location", [0, 0])[1]),
                            "Lon": float(v.get("location", [0, 0])[0]),
                            "Status": "Dostava aktivna 🟢" if is_open_for_delivery else "Zatvoreno/Nema dostave 🔴",
                            "Online": is_open_for_delivery,
                            "Ocena": v.get("rating", {}).get("score", 0),
                            "Broj_Ocena": int(v.get("rating", {}).get("volume", 0))
                        })
            return pd.DataFrame(restorani).drop_duplicates(subset=['Ime'])
    except: pass
    return pd.DataFrame()

def save_snapshot(df):
    if not df.empty:
        df_save = df.copy()
        if 'Kuhinja_Raw' in df_save.columns:
            df_save = df_save.drop(columns=['Kuhinja_Raw'])
        df_save['timestamp'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        df_save.to_csv(DB_FILE, mode='a', header=not os.path.exists(DB_FILE), index=False, quoting=csv.QUOTE_ALL)

# --- 5. SIDEBAR ---
st.sidebar.title("🛠️ Kontrola")
grad_naziv = st.sidebar.selectbox("Izaberi grad:", list(CITIES.keys()))

if grad_naziv != st.session_state.current_city:
    st.session_state.current_city = grad_naziv
    st.session_state.lat, st.session_state.lon = CITIES[grad_naziv]["coords"]
    st.cache_data.clear()
    st.rerun()

# Pretraga adrese
adresa_input = st.sidebar.text_input("📍 Unesi adresu:")
if st.sidebar.button("Lociraj"):
    loc = geolocator.geocode(adresa_input)
    if loc:
        st.session_state.lat, st.session_state.lon = loc.latitude, loc.longitude
        st.cache_data.clear()
        st.rerun()

filter_status = st.sidebar.radio("Filter statusa:", ["Sve", "Otvoreno 🟢", "Zatvoreno 🔴"])

st.sidebar.markdown("---")
interval = st.sidebar.number_input("Auto-refresh (min):", 1, 60, 5)
if st.sidebar.button("▶️ START TAJMER"): st.session_state.timer_active = True
if st.sidebar.button("⏹️ STOP TAJMER"): st.session_state.timer_active = False

if st.session_state.timer_active:
    countdown_timer(interval)
    st_autorefresh(interval=interval*60000, key="global_r")

# --- 6. GLAVNI PANEL ---
df_raw = fetch_wolt_data(st.session_state.lat, st.session_state.lon, CITIES[grad_naziv]["slug"])
df_main = df_raw.copy()

if not df_raw.empty:
    if filter_status == "Otvoreno 🟢": df_main = df_raw[df_raw['Online'] == True]
    elif filter_status == "Zatvoreno 🔴": df_main = df_raw[df_raw['Online'] == False]

tab1, tab2, tab3, tab4 = st.tabs(["🟢 Radar", "📉 Analiza ponude", "📈 Traffic Tracker", "☁️ Service Cloud"])

# TAB 1: RADAR
with tab1:
    if not df_main.empty:
        m1 = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=14)
        folium.Marker([st.session_state.lat, st.session_state.lon], icon=folium.Icon(color='blue', icon='home')).add_to(m1)
        for _, r in df_main.iterrows():
            boja = "green" if r['Online'] else "red"
            folium.CircleMarker([r['Lat'], r['Lon']], radius=7, color=boja, fill=True, tooltip=r['Ime']).add_to(m1)
        
        map_resp = st_folium(m1, width="100%", height=600, key="m1")
        if map_resp and map_resp.get("last_clicked"):
            st.session_state.lat, st.session_state.lon = map_resp["last_clicked"]["lat"], map_resp["last_clicked"]["lng"]
            st.cache_data.clear()
            st.rerun()
            
        st.dataframe(
            df_main[["Wolt Link", "Status", "Ocena", "Kuhinja_Detalji"]], 
            use_container_width=True, hide_index=True,
            column_config={"Wolt Link": st.column_config.LinkColumn("Restoran (Klikni za Wolt)")}
        )

# TAB 2: ANALIZA PONUDE + MAPA
with tab2:
    if not df_main.empty:
        flat_cats = [item for sublist in df_main['Kuhinja_Raw'] for item in sublist]
        unique_cats = sorted(list(set(flat_cats)))
        izbor = st.selectbox("Vrsta hrane:", ["Sve"] + unique_cats)
        
        df_f = df_main[df_main['Kuhinja_Raw'].apply(lambda x: izbor in x)] if izbor != "Sve" else df_main
        st.metric(f"Broj {izbor} objekata", len(df_f))
        
        # DODATA MAPA U ANALIZU
        m2 = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=14)
        for _, r in df_f.iterrows():
            boja = "green" if r['Online'] else "red"
            folium.Marker([r['Lat'], r['Lon']], tooltip=r['Ime'], icon=folium.Icon(color="blue" if r['Online'] else "gray")).add_to(m2)
        st_folium(m2, width="100%", height=500, key="m2")
        
        if st.button("💾 SNIMI SNIMAK"):
            save_snapshot(df_raw)
            st.success("Snimljeno!")
            
        st.dataframe(
            df_f[["Wolt Link", "Kuhinja_Detalji", "Ocena", "Broj_Ocena"]], 
            use_container_width=True, hide_index=True,
            column_config={"Wolt Link": st.column_config.LinkColumn("Restoran (Klikni za Wolt)")}
        )

# TAB 3: TRAFFIC TRACKER
with tab3:
    if os.path.exists(DB_FILE):
        try:
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
                st.write(f"Rast: {ts[-2].strftime('%H:%M')} -> {ts[-1].strftime('%H:%M')}")
                st.dataframe(m[m['Nove_Ocene'] > 0].sort_values(by='Nove_Ocene', ascending=False)[["Ime", "Nove_Ocene"]], use_container_width=True)
            else: st.warning("Potrebno je bar 2 snimka.")
        except Exception as e: st.error("Greška sa bazom.")
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
