import streamlit as st
from curl_cffi import requests
import pandas as pd
import folium
from folium.plugins import HeatMap
from streamlit_folium import st_folium, folium_static 
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
from streamlit_autorefresh import st_autorefresh
import datetime
import os

# --- 1. KONFIGURACIJA ---
st.set_page_config(page_title="Wolt Logistics Radar v18", layout="wide", page_icon="🕵️")

CITIES = {
    "Niš": {"coords": (43.3209, 21.8958), "slug": "nis"},
    "Beograd": {"coords": (44.7866, 20.4489), "slug": "beograd"},
    "Novi Sad": {"coords": (45.2671, 19.8335), "slug": "novi-sad"}
}

DB_FILE = "radar_history.csv"
geolocator = Nominatim(user_agent="wolt_radar_v18")

# --- 2. SESSION STATE ---
if 'lat' not in st.session_state:
    st.session_state.lat, st.session_state.lon = CITIES["Niš"]["coords"]
if 'current_city' not in st.session_state:
    st.session_state.current_city = "Niš"

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
            user_coords = (lat, lon)
            
            for section in data.get("sections", []):
                for item in section.get("items", []):
                    v = item.get("venue")
                    if v:
                        r_coords = (v.get("location", [0, 0])[1], v.get("location", [0, 0])[0])
                        # Izračunavamo stvarnu udaljenost od centra skena (u km)
                        dist = geodesic(user_coords, r_coords).km
                        
                        eta_raw = v.get("estimate", 30)
                        try:
                            eta = int(str(eta_raw).split('-')[0])
                        except:
                            eta = 30
                        
                        restorani.append({
                            "Ime": v.get("name"),
                            "Adresa": v.get("address"),
                            "Lat": r_coords[0],
                            "Lon": r_coords[1],
                            "Status": "Otvoreno 🟢" if v.get("online") else "Zatvoreno 🔴",
                            "Online": v.get("online", False),
                            "Ocena": v.get("rating", {}).get("score", 0),
                            "Broj_Ocena": v.get("rating", {}).get("volume", 0),
                            "ETA": eta,
                            "Distanca_km": round(dist, 2),
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

st.sidebar.markdown("---")
interval = st.sidebar.number_input("Auto-refresh (min):", 1, 60, 5)
if st.sidebar.button("▶️ START"): st.session_state.timer_active = True
if st.sidebar.button("⏹️ STOP"): st.session_state.timer_active = False
if st.session_state.get('timer_active'):
    st_autorefresh(interval=interval*60000, key="global_refresh")

# --- 5. TABOVI ---
tab1, tab2, tab3 = st.tabs(["📊 Otvoreno / Zatvoreno", "🔥 Heatmap Dostave", "📈 Traffic Tracker"])

df_main = fetch_wolt_data(st.session_state.lat, st.session_state.lon, CITIES[grad_naziv]["slug"])

# --- TAB 1: OTVORENO / ZATVORENO (Vraćen stari izgled) ---
with tab1:
    st.title(f"📍 Radar Stanje: {grad_naziv}")
    if not df_main.empty:
        c1, c2, c3 = st.columns(3)
        c1.metric("Ukupno", len(df_main))
        c2.metric("Otvoreno", len(df_main[df_main['Online'] == True]))
        c3.metric("Zatvoreno", len(df_main[df_main['Online'] == False]))

        m1 = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=14)
        folium.Marker([st.session_state.lat, st.session_state.lon], icon=folium.Icon(color='blue', icon='home')).add_to(m1)
        for _, r in df_main.iterrows():
            boja = "green" if r['Online'] else "red"
            folium.CircleMarker([r['Lat'], r['Lon']], radius=8, color=boja, fill=True, tooltip=r['Ime']).add_to(m1)
        
        resp = st_folium(m1, width="100%", height=500, key="main_radar_map")
        if resp and resp.get("last_clicked"):
            st.session_state.lat, st.session_state.lon = resp["last_clicked"]["lat"], resp["last_clicked"]["lng"]
            st.cache_data.clear()
            st.rerun()

        st.dataframe(df_main[["Ime", "Status", "Ocena", "ETA", "Distanca_km", "Wolt Link"]], 
                     use_container_width=True, hide_index=True,
                     column_config={"Wolt Link": st.column_config.LinkColumn("Link", display_text="Otvori 🔗")})

# --- TAB 2: HEATMAP DOSTAVE (Nova Logika) ---
with tab3: # Ovo je zapravo tvoj Tab 2 (Heatmap)
    st.title("🔥 Logistička Efikasnost")
    st.write("Skala: **Zeleno** (Brzo stize) -> **Žuto** (Prosek) -> **Crveno** (Dugo čekanje/Daleko)")
    
    m_heat = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=14)
    
    if not df_main.empty:
        df_active = df_main[df_main['Online'] == True].copy()
        if not df_active.empty:
            # LOGIKA: Intenzitet je ETA. 
            # Da bismo izbegli "density" problem, koristimo fiksni gradijent.
            # Normalizujemo ETA vrednosti (npr. 20 min je nisko, 60 min je visoko)
            heat_data = []
            for _, r in df_active.iterrows():
                # Intenzitet zavisi od ETA (što veći ETA, to je bliži 1.0 - Crveno)
                intensity = min(r['ETA'] / 60.0, 1.0) 
                heat_data.append([r['Lat'], r['Lon'], intensity])

            # Gradient: 0 = Zeleno, 0.5 = Žuto, 1 = Crveno
            HeatMap(heat_data, 
                    radius=25, 
                    blur=15, 
                    gradient={0.2: 'green', 0.5: 'yellow', 1: 'red'},
                    min_opacity=0.3).add_to(m_heat)
    
    folium_static(m_heat, width=1200)

# --- TAB 3: TRAFFIC TRACKER ---
with tab2: # Ovo je zapravo tvoj Tab 3 (Traffic)
    st.title("📈 Traffic Tracker")
    if os.path.exists(DB_FILE):
        h = pd.read_csv(DB_FILE)
        # ... tvoja logika za poredjenje ocena ...
        st.write("Ovde pratiš rast ocena kroz vreme.")
    else: st.info("Snimi podatke u sidebar-u da bi video analitiku.")
