import streamlit as st
from curl_cffi import requests
import pandas as pd
import folium
from folium.plugins import HeatMap
# Dodajemo folium_static za maksimalnu kompatibilnost u tabovima
from streamlit_folium import st_folium, folium_static 
from geopy.geocoders import Nominatim
from streamlit_autorefresh import st_autorefresh
import datetime
import os

# --- 1. KONFIGURACIJA ---
st.set_page_config(page_title="Wolt BI Radar v16.3", layout="wide", page_icon="🕵️")

CITIES = {
    "Niš": {"coords": (43.3209, 21.8958), "slug": "nis"},
    "Beograd": {"coords": (44.7866, 20.4489), "slug": "beograd"},
    "Novi Sad": {"coords": (45.2671, 19.8335), "slug": "novi-sad"}
}

DB_FILE = "radar_history.csv"

# --- 2. SESSION STATE ---
if 'lat' not in st.session_state:
    st.session_state.lat, st.session_state.lon = CITIES["Niš"]["coords"]
if 'current_city' not in st.session_state:
    st.session_state.current_city = "Niš"
if 'timer_active' not in st.session_state:
    st.session_state.timer_active = False

# --- 3. FUNKCIJA ZA PODATKE ---
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
                        rating_data = v.get("rating", {})
                        # Čistimo ETA - uzimamo broj
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
                            "Ocena": rating_data.get("score", 0),
                            "Broj_Ocena": rating_data.get("volume", 0),
                            "ETA": eta,
                            "Wolt Link": f"https://wolt.com/sr/srb/{city_slug}/restaurant/{v.get('slug')}"
                        })
            return pd.DataFrame(restorani).drop_duplicates(subset=['Ime'])
    except: pass
    return pd.DataFrame()

# --- 4. SIDEBAR ---
st.sidebar.title("🛠️ Kontrola")
grad_naziv = st.sidebar.selectbox("Grad:", list(CITIES.keys()))

if grad_naziv != st.session_state.current_city:
    st.session_state.current_city = grad_naziv
    st.session_state.lat, st.session_state.lon = CITIES[grad_naziv]["coords"]
    st.cache_data.clear()
    st.rerun()

st.sidebar.markdown("---")
if st.sidebar.button("💾 SNIMI STANJE"):
    df_snimak = fetch_wolt_data(st.session_state.lat, st.session_state.lon, CITIES[grad_naziv]["slug"])
    if not df_snimak.empty:
        df_snimak['timestamp'] = datetime.datetime.now()
        df_snimak.to_csv(DB_FILE, mode='a', header=not os.path.exists(DB_FILE), index=False)
        st.sidebar.success("Arhivirano!")

# --- 5. GLAVNI PANEL ---
tab1, tab2, tab3 = st.tabs(["🗺️ Radar Mapa", "📈 Traffic Tracker", "🔥 Dostava HeatMap"])

df_main = fetch_wolt_data(st.session_state.lat, st.session_state.lon, CITIES[grad_naziv]["slug"])

# TAB 1: OPERATIVNA MAPA (v13 stil)
with tab1:
    st.title(f"📍 Radar: {grad_naziv}")
    if not df_main.empty:
        m1 = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=14)
        folium.Marker([st.session_state.lat, st.session_state.lon], icon=folium.Icon(color='blue', icon='home')).add_to(m1)
        for _, r in df_main.iterrows():
            boja = "green" if r['Online'] else "red"
            folium.CircleMarker([r['Lat'], r['Lon']], radius=8, color=boja, fill=True, tooltip=r['Ime']).add_to(m1)
        
        # Ovde koristimo st_folium jer nam treba interakcija (klik)
        map_resp = st_folium(m1, width="100%", height=500, key="radar_map")
        
        if map_resp and map_resp.get("last_clicked"):
            st.session_state.lat = map_resp["last_clicked"]["lat"]
            st.session_state.lon = map_resp["last_clicked"]["lng"]
            st.cache_data.clear()
            st.rerun()
            
        st.dataframe(df_main[["Ime", "Status", "Ocena", "ETA", "Wolt Link"]], use_container_width=True, hide_index=True)

# TAB 2: TRAFFIC
with tab2:
    st.title("📈 Analiza rasta ocena")
    if os.path.exists(DB_FILE):
        h = pd.read_csv(DB_FILE)
        st.write("Podaci su dostupni u bazi. Uporedi poslednja dva snimka.")
        # Ovde ide tvoja logika za traffic...
    else: st.info("Baza je prazna.")

# TAB 3: HEATMAP (FIXED)
with tab3:
    st.title("🔥 Mapa kašnjenja i gužve")
    
    # Kreiramo mapu
    m3 = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=14)
    
    if not df_main.empty:
        # Uzimamo samo otvorene
        df_active = df_main[df_main['Online'] == True].copy()
        
        if not df_active.empty:
            # Priprema podataka
            h_data = df_active[['Lat', 'Lon', 'ETA']].dropna().values.tolist()
            # Dodajemo HeatMap
            HeatMap(h_data, radius=30, blur=15, min_opacity=0.5).add_to(m3)
            st.success(f"Analizirano {len(df_active)} otvorenih restorana.")
        else:
            st.warning("Nema otvorenih restorana trenutno.")
    
    # REŠENJE: folium_static umesto st_folium za Tab 3
    # Ovo prisiljava Streamlit da iscrta mapu odmah, bez obzira na tabove
    folium_static(m3, width=1200)

    st.markdown("""
    ---
    - 🔴 **Vrele tačke:** Visok ETA (gužva).
    - 🔵 **Hladne tačke:** Brza dostava.
    """)
