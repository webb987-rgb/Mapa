import streamlit as st
from curl_cffi import requests
import pandas as pd
import folium
from folium.plugins import HeatMap
from streamlit_folium import st_folium, folium_static 
from streamlit_autorefresh import st_autorefresh
import numpy as np
import datetime
import os
import csv
import streamlit.components.v1 as components

# --- 1. KONFIGURACIJA ---
st.set_page_config(page_title="Wolt BI Radar v25.3", layout="wide", page_icon="📡")

CITIES = {
    "Niš": {"coords": (43.3209, 21.8958), "slug": "nis"},
    "Beograd": {"coords": (44.7866, 20.4489), "slug": "beograd"},
    "Novi Sad": {"coords": (45.2671, 19.8335), "slug": "novi-sad"},
    "Kragujevac": {"coords": (44.0128, 20.9114), "slug": "kragujevac"}
}

DB_FILE = "radar_history.csv"

# --- 2. SMOOTH TAJMER (JS) ---
def countdown_timer(minutes):
    seconds = minutes * 60
    html_code = f"""
    <div id="timer-container" style="padding:10px; border-radius:10px; background-color:#f0f2f6; text-align:center; border: 1px solid #d1d5db;">
        <p style="margin:0; font-size:0.8rem; color:#6b7280; font-family:sans-serif;">Sledeće osvežavanje za:</p>
        <span id="timer" style="font-size:1.5rem; font-weight:bold; color:#ff4b4b; font-family:monospace;">--:--</span>
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
    return components.html(html_code, height=100)

# --- 3. SKREPER ---
@st.cache_data(ttl=60)
def fetch_wolt_data(lat, lon, city_slug):
    url = "https://restaurant-api.wolt.com/v1/pages/restaurants"
    try:
        # FIX: Ispravljeni params
        r = requests.get(url, params={"lat": lat, "lon": lon}, impersonate="chrome120", timeout=15)
        if r.status_code == 200:
            restorani = []
            for section in r.json().get("sections", []):
                for item in section.get("items", []):
                    v = item.get("venue")
                    if v:
                        cats = v.get("categories", [])
                        kuhinje = [c.get("name") for c in cats]
                        restorani.append({
                            "Ime": v.get("name"),
                            "Kuhinja_Raw": kuhinje,
                            "Kuhinja_Detalji": ", ".join(kuhinje) if kuhinje else "Ostalo",
                            "Lat": float(v.get("location", [0, 0])[1]),
                            "Lon": float(v.get("location", [0, 0])[0]),
                            "Status": "Otvoreno 🟢" if v.get("online") else "Zatvoreno 🔴",
                            "Online": v.get("online", False),
                            "Ocena": v.get("rating", {}).get("score", 0),
                            "Broj_Ocena": int(v.get("rating", {}).get("volume", 0)),
                            "Wolt Link": f"https://wolt.com/sr/srb/{city_slug}/restaurant/{v.get('slug')}"
                        })
            if restorani:
                return pd.DataFrame(restorani).drop_duplicates(subset=['Ime'])
    except: pass
    # Vraćamo prazan DF sa definisanim kolonama da izbegnemo KeyError
    return pd.DataFrame(columns=["Ime", "Online", "Status", "Lat", "Lon", "Ocena", "Kuhinja_Raw"])

# --- 4. SIDEBAR ---
st.sidebar.title("📡 Radar Kontrola")
grad_naziv = st.sidebar.selectbox("Grad:", list(CITIES.keys()))
filter_status = st.sidebar.radio("Prikaži restorane:", ["Sve", "Samo Otvoreno 🟢", "Samo Zatvoreno 🔴"])

st.sidebar.markdown("---")
if st.sidebar.button("💾 SNIMI ZA ANALIZU"):
    df_raw = fetch_wolt_data(st.session_state.lat, st.session_state.lon, CITIES[grad_naziv]["slug"])
    if not df_raw.empty:
        df_save = df_raw.copy().drop(columns=['Kuhinja_Raw'], errors='ignore')
        df_save['timestamp'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        df_save.to_csv(DB_FILE, mode='a', header=not os.path.exists(DB_FILE), index=False, quoting=csv.QUOTE_ALL)
        st.sidebar.success("Podaci sačuvani!")

refresh_min = st.sidebar.number_input("Interval osvežavanja (min):", 1, 60, 5)
run_timer = st.sidebar.toggle("▶️ Aktiviraj Auto-Refresh", value=False)
if run_timer:
    countdown_timer(refresh_min)
    st_autorefresh(interval=refresh_min * 60000, key="global_refresh")

# --- 5. LOGIKA PODATAKA ---
if 'lat' not in st.session_state:
    st.session_state.lat, st.session_state.lon = CITIES[grad_naziv]["coords"]

df_raw = fetch_wolt_data(st.session_state.lat, st.session_state.lon, CITIES[grad_naziv]["slug"])

# BEZBEDNO FILTRIRANJE (KeyError Fix)
df_main = df_raw.copy()
if not df_raw.empty:
    if filter_status == "Samo Otvoreno 🟢":
        df_main = df_raw[df_raw['Online'] == True]
    elif filter_status == "Samo Zatvoreno 🔴":
        df_main = df_raw[df_raw['Online'] == False]

# --- 6. TABOVI ---
tab1, tab2, tab3, tab4 = st.tabs(["🟢 Radar", "📉 Analiza ponude", "📈 Traffic Tracker", "☁️ Service Cloud"])

with tab1:
    st.subheader(f"📍 Stanje: {grad_naziv} ({filter_status})")
    if df_main.empty:
        st.warning("Trenutno nema podataka za izabrani grad/filter.")
    else:
        m1 = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=14)
        for _, r in df_main.iterrows():
            boja = "green" if r['Online'] else "red"
            folium.CircleMarker([r['Lat'], r['Lon']], radius=7, color=boja, fill=True, tooltip=r['Ime']).add_to(m1)
        st_folium(m1, width="100%", height=600, key="main_map")
        st.dataframe(df_main[["Ime", "Status", "Ocena", "Kuhinja_Detalji"]], use_container_width=True, hide_index=True)

with tab2:
    if not df_main.empty and 'Kuhinja_Raw' in df_main.columns:
        flat_cats = [item for sublist in df_main['Kuhinja_Raw'] for item in sublist]
        unique_cats = sorted(list(set(flat_cats)))
        izbor = st.selectbox("Vrsta hrane:", ["Sve"] + unique_cats)
        df_f = df_main[df_main['Kuhinja_Raw'].apply(lambda x: izbor in x)] if izbor != "Sve" else df_main
        st.dataframe(df_f[["Ime", "Kuhinja_Detalji", "Ocena", "Status"]], use_container_width=True, hide_index=True)

with tab3:
    st.subheader("📈 Analiza prodaje")
    if os.path.exists(DB_FILE):
        h = pd.read_csv(DB_FILE, on_bad_lines='skip')
        h['timestamp'] = pd.to_datetime(h['timestamp'], errors='coerce')
        h = h.dropna(subset=['timestamp'])
        ts = sorted(h['timestamp'].unique())
        if len(ts) >= 2:
            df_now = h[h['timestamp'] == ts[-1]].copy()
            df_pre = h[h['timestamp'] == ts[-2]].copy()
            m = pd.merge(df_now, df_pre, on="Ime", suffixes=('_sad', '_pre'))
            m['Nove_Ocene'] = m['Broj_Ocena_sad'] - m['Broj_Ocena_pre']
            st.write(f"Promena: {ts[-2].strftime('%H:%M')} -> {ts[-1].strftime('%H:%M')}")
            st.dataframe(m[m['Nove_Ocene'] > 0].sort_values(by='Nove_Ocene', ascending=False)[["Ime", "Nove_Ocene"]], use_container_width=True)
        else: st.info("Potrebno je više snimaka u bazi.")
    else: st.info("Baza je prazna.")

with tab4:
    st.subheader("☁️ Service Cloud (Aktivna pokrivenost)")
    m4 = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=13, tiles="cartodbpositron")
    if not df_main.empty:
        df_a = df_main[df_main['Online'] == True]
        if not df_a.empty:
            pts = []
            for _, r in df_a.iterrows():
                pts.append([r['Lat'], r['Lon'], 1.0])
                for ang in range(0, 360, 45):
                    rad = np.radians(ang)
                    pts.append([r['Lat'] + 0.007 * np.cos(rad), r['Lon'] + 0.009 * np.sin(rad), 0.6])
            HeatMap(pts, radius=45, blur=30, gradient={0.2: 'red', 0.5: 'yellow', 1.0: 'green'}).add_to(m4)
    folium_static(m4, width=1400, height=800)
