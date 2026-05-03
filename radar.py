import streamlit as st
from curl_cffi import requests
import pandas as pd
import folium
from folium.plugins import HeatMap
from streamlit_folium import st_folium, folium_static 
from geopy.geocoders import Nominatim
from streamlit_autorefresh import st_autorefresh
import datetime
import os

# --- 1. KONFIGURACIJA ---
st.set_page_config(page_title="Wolt Market Radar v17", layout="wide", page_icon="🕵️")

CITIES = {
    "Niš": {"coords": (43.3209, 21.8958), "slug": "nis"},
    "Beograd": {"coords": (44.7866, 20.4489), "slug": "beograd"},
    "Novi Sad": {"coords": (45.2671, 19.8335), "slug": "novi-sad"}
}

DB_FILE = "radar_history.csv"
geolocator = Nominatim(user_agent="wolt_radar_v17")

# --- 2. SESSION STATE ---
if 'lat' not in st.session_state:
    st.session_state.lat, st.session_state.lon = CITIES["Niš"]["coords"]
if 'current_city' not in st.session_state:
    st.session_state.current_city = "Niš"
if 'timer_active' not in st.session_state:
    st.session_state.timer_active = False

# --- 3. FUNKCIJE ---
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
                        # Čišćenje ETA (vreme dostave)
                        eta_raw = v.get("estimate", 30)
                        try:
                            eta = int(str(eta_raw).split('-')[0])
                        except:
                            eta = 30
                        
                        restorani.append({
                            "Ime": v.get("name"),
                            "Adresa": v.get("address"),
                            "Lat": float(v.get("location", [0, 0])[1]),
                            "Lon": float(v.get("location", [0, 0])[0]),
                            "Status": "Otvoreno 🟢" if v.get("online") else "Zatvoreno 🔴",
                            "Online": v.get("online", False),
                            "Ocena": v.get("rating", {}).get("score", 0),
                            "Broj_Ocena": v.get("rating", {}).get("volume", 0),
                            "ETA": eta,
                            "Wolt Link": f"https://wolt.com/sr/srb/{city_slug}/restaurant/{v.get('slug')}"
                        })
            return pd.DataFrame(restorani).drop_duplicates(subset=['Ime'])
    except: pass
    return pd.DataFrame()

# --- 4. SIDEBAR ---
st.sidebar.title("🛠️ Kontrole")
grad_naziv = st.sidebar.selectbox("Izaberi grad:", list(CITIES.keys()))

if grad_naziv != st.session_state.current_city:
    st.session_state.current_city = grad_naziv
    st.session_state.lat, st.session_state.lon = CITIES[grad_naziv]["coords"]
    st.cache_data.clear()
    st.rerun()

adresa_input = st.sidebar.text_input("📍 Pretraga adrese:", placeholder="npr. Knjaževačka 147")
if st.sidebar.button("🔍 Osveži lokaciju"):
    try:
        loc = geolocator.geocode(f"{adresa_input}, {grad_naziv}, Serbia")
        if loc:
            st.session_state.lat, st.session_state.lon = loc.latitude, loc.longitude
            st.cache_data.clear()
            st.rerun()
    except: st.sidebar.error("Nije nađeno.")

st.sidebar.markdown("---")
if st.sidebar.button("💾 SNIMI ZA TRAFFIC"):
    df_s = fetch_wolt_data(st.session_state.lat, st.session_state.lon, CITIES[grad_naziv]["slug"])
    if not df_s.empty:
        df_s['timestamp'] = datetime.datetime.now()
        df_s.to_csv(DB_FILE, mode='a', header=not os.path.exists(DB_FILE), index=False)
        st.sidebar.success("Podaci arhivirani!")

st.sidebar.markdown("---")
interval = st.sidebar.number_input("Auto-refresh (min):", 1, 60, 5)
if st.sidebar.button("▶️ START"): st.session_state.timer_active = True
if st.sidebar.button("⏹️ STOP"): st.session_state.timer_active = False

if st.session_state.timer_active:
    st_autorefresh(interval=interval*60000, key="global_r")

# --- 5. GLAVNI PANEL (TABOVI) ---
tab1, tab2, tab3 = st.tabs(["🟢 Otvoreno / Zatvoreno", "📈 Traffic Tracker", "🔥 Heatmap Kašnjenja"])

df_main = fetch_wolt_data(st.session_state.lat, st.session_state.lon, CITIES[grad_naziv]["slug"])

# --- TAB 1: OTVORENO / ZATVORENO (Vraćena stara logika) ---
with tab1:
    st.title(f"📊 Pregled tržišta: {grad_naziv}")
    
    if not df_main.empty:
        c1, c2, c3 = st.columns(3)
        c1.metric("Ukupno", len(df_main))
        c2.metric("Otvoreno", len(df_main[df_main['Online'] == True]))
        c3.metric("Zatvoreno", len(df_main[df_main['Online'] == False]))
        
        st.markdown("### 🗺️ Interaktivna mapa")
        m1 = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=14)
        folium.Marker([st.session_state.lat, st.session_state.lon], icon=folium.Icon(color='blue', icon='home')).add_to(m1)
        
        for _, r in df_main.iterrows():
            boja = "green" if r['Online'] else "red"
            folium.CircleMarker([r['Lat'], r['Lon']], radius=8, color=boja, fill=True, tooltip=r['Ime']).add_to(m1)
        
        resp = st_folium(m1, width="100%", height=500, key="main_map")
        if resp and resp.get("last_clicked"):
            st.session_state.lat = resp["last_clicked"]["lat"]
            st.session_state.lon = resp["last_clicked"]["lng"]
            st.cache_data.clear()
            st.rerun()

        st.markdown("### 📋 Tabela restorana")
        st.dataframe(df_main[["Ime", "Status", "Ocena", "ETA", "Adresa", "Wolt Link"]], 
                     use_container_width=True, hide_index=True,
                     column_config={"Wolt Link": st.column_config.LinkColumn("Link", display_text="Otvori 🔗")})

# --- TAB 2: TRAFFIC TRACKER ---
with tab2:
    st.title("📈 Traffic Tracker (Rast ocena)")
    if os.path.exists(DB_FILE):
        h = pd.read_csv(DB_FILE)
        h['timestamp'] = pd.to_datetime(h['timestamp'])
        ts = sorted(h['timestamp'].unique())
        if len(ts) >= 2:
            df_now = h[h['timestamp'] == ts[-1]]
            df_pre = h[h['timestamp'] == ts[-2]]
            m = pd.merge(df_now, df_pre, on="Ime", suffixes=('_sad', '_pre'))
            m['Nove_Ocene'] = m['Broj_Ocena_sad'] - m['Broj_Ocena_pre']
            m['Procena_Porudžbina'] = m['Nove_Ocene'] * 10
            st.dataframe(m[m['Nove_Ocene'] > 0].sort_values(by='Nove_Ocene', ascending=False)[["Ime", "Nove_Ocene", "Procena_Porudžbina"]], use_container_width=True)
        else: st.warning("Snimi podatke bar dva puta.")
    else: st.info("Baza je prazna.")

# --- TAB 3: HEATMAP (Poboljšana logika) ---
with tab3:
    st.title("🔥 Geografija kašnjenja")
    st.write("Analiza brzine dostave samo za OTVORENE restorane.")
    
    m3 = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=14)
    
    if not df_main.empty:
        df_active = df_main[df_main['Online'] == True].copy()
        if not df_active.empty:
            # Smanjujemo radijus (radius=20) da tačke ne bi "gutale" jedna drugu u centru
            # Weight je ETA
            h_data = df_active[['Lat', 'Lon', 'ETA']].dropna().values.tolist()
            HeatMap(h_data, radius=20, blur=15, min_opacity=0.3).add_to(m3)
            st.success(f"Prikazujem podatke za {len(df_active)} otvorenih lokacija.")
        else:
            st.warning("Trenutno nema otvorenih restorana.")
            
    folium_static(m3, width=1200)
    st.write("🔴 **Crveno** = Duže čekanje (visok ETA) | 🔵 **Plavo/Zeleno** = Brza dostava.")
