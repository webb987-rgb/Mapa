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
st.set_page_config(page_title="Wolt BI Radar PRO v27.1", layout="wide", page_icon="📡")

CITIES = {
    "Niš": {"coords": (43.3209, 21.8958), "slug": "nis"},
    "Beograd": {"coords": (44.7866, 20.4489), "slug": "beograd"},
    "Novi Sad": {"coords": (45.2671, 19.8335), "slug": "novi-sad"},
    "Kragujevac": {"coords": (44.0128, 20.9114), "slug": "kragujevac"}
}

# --- UNAPREĐENE: Precizne koordinate zone dostave za Niš ---
NIS_ZONE_COORDS = [
    [43.3446, 21.8481], # Severozapad (Gornji Komren rub)
    [43.3533, 21.8690], # Severozapad rub
    [43.3571, 21.8988], # Sever (Pantelej rub)
    [43.3512, 21.9287], # Severoistok (Donja Vrežina rub)
    [43.3379, 21.9567], # Istok
    [43.3188, 21.9734], # Istok centar rub
    [43.3081, 21.9782], # Jugoistok rub (najistočnija tačka kod auto-puta)
    [43.2981, 21.9691], # Usek 1 (Brzi Brod sever)
    [43.2921, 21.9676], # Usek 2 (Brzi Brod rub)
    [43.2878, 21.9547], # Skretanje ka jugu
    [43.2831, 21.9298], # Jug (Suvi Do rub)
    [43.2802, 21.8993], # Jug (Palilula rub)
    [43.2796, 21.8687], # Jug rub
    [43.2867, 21.8497], # Jugozapad rub
    [43.2936, 21.8383], # Jugozapad najjužnija tačka (Pasi Poljana rub)
    [43.3051, 21.8329], # Skretanje ka severu
    [43.3235, 21.8315], # Zapad (Medoševac rub)
    [43.3371, 21.8356], # Severozapad rub
]

DB_FILE = "radar_history.csv"
geolocator = Nominatim(user_agent="wolt_bi_radar_v27_1")

# --- 2. SESSION STATE ---
if 'lat' not in st.session_state:
    st.session_state.lat, st.session_state.lon = CITIES["Niš"]["coords"]
if 'current_city' not in st.session_state:
    st.session_state.current_city = "Niš"
if 'timer_active' not in st.session_state:
    st.session_state.timer_active = False

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

# --- 4. SKREPER ---
@st.cache_data(ttl=60)
def fetch_wolt_data(lat, lon, city_slug):
    cols = ["Ime", "Wolt Link", "Kuhinja_Raw", "Kuhinja_Detalji", "Lat", "Lon", "Status", "Online", "Ocena", "Broj_Ocena"]
    prazan_df = pd.DataFrame(columns=cols)
    url = "https://restaurant-api.wolt.com/v1/pages/restaurants"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Accept-Language": "sr-RS,sr;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": f"https://wolt.com/sr/srb/{city_slug}",
    }
    try:
        r = requests.get(url, params={"lat": lat, "lon": lon}, headers=headers, impersonate="chrome120", timeout=15)
        if r.status_code == 200:
            restorani = []
            data = r.json()
            for section in data.get("sections", []):
                for item in section.get("items", []):
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
            if restorani:
                return pd.DataFrame(restorani).drop_duplicates(subset=['Ime'])
    except: pass
    return prazan_df

def save_snapshot(df):
    if not df.empty:
        df_save = df.copy()
        if 'Kuhinja_Raw' in df_save.columns: df_save = df_save.drop(columns=['Kuhinja_Raw'])
        df_save['timestamp'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        df_save.to_csv(DB_FILE, mode='a', header=not os.path.exists(DB_FILE), index=False, quoting=csv.QUOTE_ALL)
        return True
    return False

# --- 5. SIDEBAR ---
st.sidebar.title("🛠️ Kontrola")
grad_naziv = st.sidebar.selectbox("Grad:", list(CITIES.keys()))
if grad_naziv != st.session_state.current_city:
    st.session_state.current_city = grad_naziv
    st.session_state.lat, st.session_state.lon = CITIES[grad_naziv]["coords"]
    st.cache_data.clear()
    st.rerun()

filter_status = st.sidebar.radio("Prikaži samo:", ["Sve", "Otvoreno 🟢", "Zatvoreno 🔴"])

st.sidebar.markdown("---")
refresh_min = st.sidebar.number_input("Interval (min):", 1, 60, 5)
st.session_state.timer_active = st.sidebar.toggle("▶️ Aktiviraj Tajmer", value=st.session_state.timer_active)

if st.session_state.timer_active:
    countdown_timer(refresh_min)
    st_autorefresh(interval=refresh_min * 60000, key="global_refresh")

# --- 6. LOGIKA PODATAKA ---
df_raw = fetch_wolt_data(st.session_state.lat, st.session_state.lon, CITIES[grad_naziv]["slug"])
df_main = df_raw.copy()

if not df_raw.empty:
    if filter_status == "Otvoreno 🟢": df_main = df_raw[df_raw['Online'] == True]
    elif filter_status == "Zatvoreno 🔴": df_main = df_raw[df_raw['Online'] == False]

# --- 7. PANEL SA TABOVIMA ---
tab1, tab2, tab3, tab4 = st.tabs(["🟢 Radar", "📉 Analiza ponude", "📈 Traffic Tracker", "☁️ Service Cloud"])

# TAB 1: RADAR (Metrika + Karta + Tabela)
with tab1:
    col_m1, col_m2 = st.columns(2)
    col_m1.metric("Otvoreno 🟢", len(df_main[df_main['Online'] == True]))
    col_m2.metric("Zatvoreno 🔴", len(df_main[df_main['Online'] == False]))
    
    m1 = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=14)
    
    # Iscrtavanje zone dostave za Niš (sada preciznije)
    if grad_naziv == "Niš":
        # Koristimo malo tamniju sivu i veću prozirnost da se podudara sa visualom
        folium.Polygon(locations=NIS_ZONE_COORDS, color="#333333", weight=2, fill=True, fill_color="#333333", fill_opacity=0.25, tooltip="Zona dostave Niš").add_to(m1)
    
    folium.Marker([st.session_state.lat, st.session_state.lon], icon=folium.Icon(color='blue', icon='home')).add_to(m1)
    for _, r in df_main.iterrows():
        boja = "green" if r['Online'] else "red"
        folium.CircleMarker([r['Lat'], r['Lon']], radius=7, color=boja, fill=True, tooltip=r['Ime']).add_to(m1)
    
    st_folium(m1, width="100%", height=500, key="m1")
    st.dataframe(df_main[["Wolt Link", "Status", "Ocena", "Kuhinja_Detalji"]], use_container_width=True, hide_index=True, column_config={"Wolt Link": st.column_config.LinkColumn("Restoran")})

# TAB 2: ANALIZA PONUDE (Sa preciznom zonom)
with tab2:
    if not df_main.empty:
        flat_cats = [item for sublist in df_main['Kuhinja_Raw'] for item in sublist]
        unique_cats = sorted(list(set(flat_cats)))
        izbor = st.selectbox("Vrsta hrane:", ["Sve"] + unique_cats)
        df_f = df_main[df_main['Kuhinja_Raw'].apply(lambda x: izbor in x)] if izbor != "Sve" else df_main
        
        col_f1, col_f2 = st.columns(2)
        col_f1.metric(f"{izbor} Otvoreno 🟢", len(df_f[df_f['Online'] == True]))
        col_f2.metric(f"{izbor} Zatvoreno 🔴", len(df_f[df_f['Online'] == False]))
        
        m2 = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=14)
        
        # Iscrtavanje precizne zone za Niš
        if grad_naziv == "Niš":
            folium.Polygon(locations=NIS_ZONE_COORDS, color="#333333", weight=2, fill=True, fill_color="#333333", fill_opacity=0.25).add_to(m2)
            
        for _, r in df_f.iterrows():
            boja = "green" if r['Online'] else "red"
            folium.CircleMarker([r['Lat'], r['Lon']], radius=8, color=boja, fill=True, tooltip=r['Ime']).add_to(m2)
        st_folium(m2, width="100%", height=500, key="m2")
        st.dataframe(df_f[["Wolt Link", "Status", "Ocena"]], use_container_width=True, hide_index=True, column_config={"Wolt Link": st.column_config.LinkColumn("Restoran")})

# TAB 3: TRAFFIC TRACKER
with tab3:
    st.title("📈 Traffic Tracker")
    if st.button("💾 SNIMI I UPOREDI"):
        prev_data = pd.DataFrame()
        if os.path.exists(DB_FILE):
            h_temp = pd.read_csv(DB_FILE)
            h_temp['timestamp'] = pd.to_datetime(h_temp['timestamp'])
            last_ts = h_temp['timestamp'].max()
            prev_data = h_temp[h_temp['timestamp'] == last_ts].copy()

        st.cache_data.clear()
        current_data = fetch_wolt_data(st.session_state.lat, st.session_state.lon, CITIES[grad_naziv]["slug"])
        save_snapshot(current_data)
        
        if not prev_data.empty and not current_data.empty:
            df_now = current_data.copy()
            df_pre = prev_data.copy()
            df_now['Broj_Ocena'] = pd.to_numeric(df_now['Broj_Ocena'], errors='coerce').fillna(0)
            df_pre['Broj_Ocena'] = pd.to_numeric(df_pre['Broj_Ocena'], errors='coerce').fillna(0)
            m = pd.merge(df_now, df_pre, on="Ime", suffixes=('_sad', '_pre'))
            m['Rast_Ocena'] = m['Broj_Ocena_sad'] - m['Broj_Ocena_pre']
            m['Est_Porudžbine'] = m['Rast_Ocena'] * 10
            res = m[m['Rast_Ocena'] > 0].sort_values(by='Rast_Ocena', ascending=False)
            st.session_state.traffic_result = res
            st.session_state.traffic_total = int(res['Est_Porudžbine'].sum())
            st.session_state.traffic_time = f"{last_ts.strftime('%H:%M:%S')} ➔ {datetime.datetime.now().strftime('%H:%M:%S')}"
        else:
            st.info("Ovo je tvoj prvi snimak. Klikni ponovo za analizu rasta čim prođe malo vremena.")

    if 'traffic_result' in st.session_state:
        st.success(f"Analiza: {st.session_state.traffic_time}")
        if not st.session_state.traffic_result.empty:
            st.metric("Ukupno novih porudžbina (procena)", st.session_state.traffic_total)
            st.dataframe(st.session_state.traffic_result[["Ime", "Rast_Ocena", "Est_Porudžbine"]], use_container_width=True, hide_index=True)
        else:
            st.warning("Nema promena u ocenama.")

# TAB 4: SERVICE CLOUD
with tab4:
    m4 = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=13, tiles="cartodbpositron")
    df_a = df_main[df_main['Online'] == True] if not df_main.empty else pd.DataFrame()
    if not df_a.empty:
        pts = [[r['Lat'], r['Lon'], 1.0] for _, r in df_a.iterrows()]
        inverted_gradient = {0.2: '#FF0000', 0.4: '#FF8C00', 0.6: '#FFFF00', 0.8: '#00FF00', 1.0: '#0000FF'}
        HeatMap(pts, radius=45, blur=30, gradient=inverted_gradient).add_to(m4)
        folium_static(m4, width=1400, height=800)
