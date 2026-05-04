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
st.set_page_config(page_title="Wolt BI Radar PRO v26.5", layout="wide", page_icon="📡")

CITIES = {
    "Niš": {"coords": (43.3209, 21.8958), "slug": "nis"},
    "Beograd": {"coords": (44.7866, 20.4489), "slug": "beograd"},
    "Novi Sad": {"coords": (45.2671, 19.8335), "slug": "novi-sad"},
    "Kragujevac": {"coords": (44.0128, 20.9114), "slug": "kragujevac"}
}

DB_FILE = "radar_history.csv"
geolocator = Nominatim(user_agent="wolt_bi_radar_hunter_v26_5")

# --- 2. SESSION STATE ---
if 'lat' not in st.session_state:
    st.session_state.lat, st.session_state.lon = CITIES["Niš"]["coords"]
if 'current_city' not in st.session_state:
    st.session_state.current_city = "Niš"

# --- 3. JS TAJMER ---
def countdown_timer(minutes):
    seconds = minutes * 60
    html_code = f"""
    <div id="timer-container" style="padding:15px; border-radius:10px; background-color:#f8f9fa; text-align:center; border: 1px solid #e9ecef; margin-bottom: 20px;">
        <p style="margin:0; font-size:0.85rem; color:#6c757d; font-family:sans-serif; text-transform: uppercase; letter-spacing: 1px;">Refresh za:</p>
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

# --- 4. UNAPREĐENI SKREPER ---
@st.cache_data(ttl=60)
def fetch_wolt_data(lat, lon, city_slug):
    # Kolone koje moraju da postoje da aplikacija ne puca
    cols = ["Ime", "Wolt Link", "Kuhinja_Raw", "Kuhinja_Detalji", "Lat", "Lon", "Status", "Online", "Ocena", "Broj_Ocena"]
    prazan_df = pd.DataFrame(columns=cols)
    
    url = "https://restaurant-api.wolt.com/v1/pages/restaurants"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Accept-Language": "sr-RS,sr;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": f"https://wolt.com/sr/srb/{city_slug}",
        "x-wolt-visitor-id": "radar-bi-tool-v26"
    }
    
    try:
        r = requests.get(url, params={"lat": lat, "lon": lon}, headers=headers, impersonate="chrome120", timeout=15)
        
        if r.status_code != 200:
            return prazan_df
            
        data = r.json()
        restorani = []
        
        # Greedy parsing: prolazimo kroz sve sekcije i tražimo "venue"
        sections = data.get("sections", [])
        for section in sections:
            items = section.get("items", [])
            for item in items:
                v = item.get("venue")
                if v:
                    cats = v.get("categories", [])
                    kuhinje = [c.get("name") for c in cats] or v.get("tags", [])
                    
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
            return prazan_df
            
        return pd.DataFrame(restorani).drop_duplicates(subset=['Ime'])
    except:
        return prazan_df

def save_snapshot(df):
    if not df.empty:
        df_save = df.copy().drop(columns=['Kuhinja_Raw'], errors='ignore')
        df_save['timestamp'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        df_save.to_csv(DB_FILE, mode='a', header=not os.path.exists(DB_FILE), index=False, quoting=csv.QUOTE_ALL)

# --- 5. SIDEBAR ---
st.sidebar.title("📡 Kontrola")
grad_naziv = st.sidebar.selectbox("Izaberi grad:", list(CITIES.keys()))

if grad_naziv != st.session_state.current_city:
    st.session_state.current_city = grad_naziv
    st.session_state.lat, st.session_state.lon = CITIES[grad_naziv]["coords"]
    st.cache_data.clear()
    st.rerun()

adresa = st.sidebar.text_input("📍 Pronađi drugu adresu:")
if st.sidebar.button("Lociraj"):
    loc = geolocator.geocode(adresa)
    if loc:
        st.session_state.lat, st.session_state.lon = loc.latitude, loc.longitude
        st.cache_data.clear()
        st.rerun()

filter_status = st.sidebar.radio("Status restorana:", ["Sve", "Otvoreno 🟢", "Zatvoreno 🔴"])

st.sidebar.markdown("---")
refresh_min = st.sidebar.number_input("Interval (min):", 1, 60, 5)
activate_timer = st.sidebar.toggle("▶️ Aktiviraj Tajmer")

if activate_timer:
    countdown_timer(refresh_min)
    st_autorefresh(interval=refresh_min * 60000, key="global_refresh")

# --- 6. LOGIKA PODATAKA ---
df_raw = fetch_wolt_data(st.session_state.lat, st.session_state.lon, CITIES[grad_naziv]["slug"])
df_main = df_raw.copy()

if not df_raw.empty:
    if filter_status == "Otvoreno 🟢":
        df_main = df_raw[df_raw['Online'] == True]
    elif filter_status == "Zatvoreno 🔴":
        df_main = df_raw[df_raw['Online'] == False]

# --- 7. TABOVI ---
tab1, tab2, tab3, tab4 = st.tabs(["🟢 Radar", "📉 Analiza ponude", "📈 Traffic Tracker", "☁️ Service Cloud"])

with tab1:
    st.subheader(f"📍 Radar skeniranje: {grad_naziv}")
    if df_main.empty:
        st.error("⚠️ Nema podataka! API nije vratio restorane. Pokušaj da promeniš grad ili osvežiš stranicu.")
    else:
        m1 = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=14)
        for _, r in df_main.iterrows():
            boja = "green" if r['Online'] else "red"
            folium.CircleMarker([r['Lat'], r['Lon']], radius=7, color=boja, fill=True, tooltip=r['Ime']).add_to(m1)
        
        map_resp = st_folium(m1, width="100%", height=500, key="m1")
        if map_resp and map_resp.get("last_clicked"):
            st.session_state.lat, st.session_state.lon = map_resp["last_clicked"]["lat"], map_resp["last_clicked"]["lng"]
            st.cache_data.clear()
            st.rerun()
        
        st.dataframe(df_main[["Wolt Link", "Status", "Ocena", "Kuhinja_Detalji"]], use_container_width=True, hide_index=True, column_config={"Wolt Link": st.column_config.LinkColumn("Restoran")})

with tab2:
    if not df_main.empty:
        flat_cats = [item for sublist in df_main['Kuhinja_Raw'] for item in sublist]
        unique_cats = sorted(list(set(flat_cats)))
        izbor = st.selectbox("Filtriraj po kuhinji:", ["Sve"] + unique_cats)
        df_f = df_main[df_main['Kuhinja_Raw'].apply(lambda x: izbor in x)] if izbor != "Sve" else df_main
        
        m2 = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=14)
        for _, r in df_f.iterrows():
            boja = "green" if r['Online'] else "red"
            folium.CircleMarker([r['Lat'], r['Lon']], radius=8, color=boja, fill=True, tooltip=r['Ime']).add_to(m2)
        st_folium(m2, width="100%", height=500, key="m2")
        st.dataframe(df_f[["Wolt Link", "Status", "Ocena"]], use_container_width=True, hide_index=True, column_config={"Wolt Link": st.column_config.LinkColumn("Restoran")})

with tab3:
    st.subheader("📈 Traffic Tracker")
    if st.button("💾 SNIMI TRENUTNO STANJE"):
        save_snapshot(df_raw)
        st.success("Podaci su arhivirani!")
    
    if os.path.exists(DB_FILE):
        h = pd.read_csv(DB_FILE)
        h['timestamp'] = pd.to_datetime(h['timestamp'])
        ts = sorted(h['timestamp'].unique())
        if len(ts) >= 2:
            df_now = h[h['timestamp'] == ts[-1]].copy()
            df_pre = h[h['timestamp'] == ts[-2]].copy()
            m = pd.merge(df_now, df_pre, on="Ime", suffixes=('_sad', '_pre'))
            m['Rast'] = m['Broj_Ocena_sad'].astype(int) - m['Broj_Ocena_pre'].astype(int)
            res = m[m['Rast'] > 0].sort_values(by='Rast', ascending=False)
            st.write(f"Analiza rasta: {ts[-2].strftime('%H:%M')} -> {ts[-1].strftime('%H:%M')}")
            st.dataframe(res[["Ime", "Rast"]], use_container_width=True, hide_index=True)

with tab4:
    m4 = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=13, tiles="cartodbpositron")
    df_a = df_main[df_main['Online'] == True]
    if not df_a.empty:
        pts = [[r['Lat'], r['Lon'], 1.0] for _, r in df_a.iterrows()]
        HeatMap(pts, radius=45, blur=30).add_to(m4)
    folium_static(m4, width=1400, height=800)
