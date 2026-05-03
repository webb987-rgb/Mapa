import streamlit as st
from curl_cffi import requests
import pandas as pd
import folium
from folium.plugins import HeatMap
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim
from streamlit_autorefresh import st_autorefresh
import datetime
import os

# --- KONFIGURACIJA ---
st.set_page_config(page_title="Wolt BI Radar v15", layout="wide", page_icon="📈")

CITIES = {
    "Niš": {"coords": (43.3209, 21.8958), "slug": "nis"},
    "Beograd": {"coords": (44.7866, 20.4489), "slug": "beograd"},
    "Novi Sad": {"coords": (45.2671, 19.8335), "slug": "novi-sad"}
}

DB_FILE = "radar_history.csv"

# --- FUNKCIJE ZA BAZU ---
def save_to_history(df):
    """Snima trenutne podatke u CSV fajl sa vremenskom oznakom"""
    df['timestamp'] = datetime.datetime.now()
    if not os.path.isfile(DB_FILE):
        df.to_csv(DB_FILE, index=False)
    else:
        df.to_csv(DB_FILE, mode='a', header=False, index=False)

def load_history():
    if os.path.exists(DB_FILE):
        return pd.read_csv(DB_FILE)
    return pd.DataFrame()

# --- SKREPER ---
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
                        # Izvlačimo ključne BI podatke: Broj ocena i vreme dostave
                        rating_data = v.get("rating", {})
                        volume = rating_data.get("volume", 0) # Broj ljudi koji su ocenili
                        
                        # Procena vremena dostave (kao težina za Hot Zone)
                        delivery_time = v.get("estimate", 30) 
                        
                        restorani.append({
                            "Ime": v.get("name"),
                            "Adresa": v.get("address"),
                            "Lat": v.get("location", [0, 0])[1],
                            "Lon": v.get("location", [0, 0])[0],
                            "Status": "Otvoreno" if v.get("online") else "Zatvoreno",
                            "Online": v.get("online", False),
                            "Ocena": rating_data.get("score", 0),
                            "Broj_Ocena": volume,
                            "Dostava_Min": delivery_time,
                            "Slug": v.get("slug")
                        })
            return pd.DataFrame(restorani).drop_duplicates(subset=['Ime'])
    except: pass
    return pd.DataFrame()

# --- SESSION STATE ---
if 'lat' not in st.session_state:
    st.session_state.lat, st.session_state.lon = CITIES["Niš"]["coords"]
if 'current_city' not in st.session_state:
    st.session_state.current_city = "Niš"

# --- SIDEBAR ---
st.sidebar.title("🛠️ BI Kontrola")
grad_naziv = st.sidebar.selectbox("Grad:", list(CITIES.keys()))
if grad_naziv != st.session_state.current_city:
    st.session_state.current_city = grad_naziv
    st.session_state.lat, st.session_state.lon = CITIES[grad_naziv]["coords"]
    st.rerun()

st.sidebar.markdown("---")
if st.sidebar.button("💾 SNIMI TRENUTNO STANJE"):
    df_current = fetch_wolt_data(st.session_state.lat, st.session_state.lon, CITIES[grad_naziv]["slug"])
    save_to_history(df_current)
    st.sidebar.success("Podaci arhivirani!")

# --- GLAVNI TABOVI ---
tab1, tab2, tab3 = st.tabs(["🗺️ Radar Mapa", "📈 Traffic Tracker", "🔥 Hot Zone Analitika"])

# --- TAB 1: RADAR MAPA (Tvoja stara proverena mapa) ---
with tab1:
    st.title("Uživo Pregled Tržišta")
    df = fetch_wolt_data(st.session_state.lat, st.session_state.lon, CITIES[grad_naziv]["slug"])
    
    if not df.empty:
        m = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=14)
        for _, r in df.iterrows():
            boja = "green" if r['Online'] else "red"
            folium.CircleMarker([r['Lat'], r['Lon']], radius=8, color=boja, fill=True, tooltip=r['Ime']).add_to(m)
        
        st_folium(m, width="100%", height=500, key="mapa_radar")
        st.dataframe(df[["Ime", "Status", "Ocena", "Broj_Ocena", "Adresa"]], use_container_width=True)

# --- TAB 2: TRAFFIC TRACKER (Analiza prodaje) ---
with tab2:
    st.title("Procena prometa (Rating Delta)")
    history = load_history()
    
    if not history.empty:
        # Uzimamo poslednja dva unosa za svaki restoran da vidimo razliku
        latest_ts = history['timestamp'].max()
        prev_ts = history[history['timestamp'] < latest_ts]['timestamp'].max()
        
        if pd.notnull(prev_ts):
            df_now = history[history['timestamp'] == latest_ts]
            df_prev = history[history['timestamp'] == prev_ts]
            
            merged = pd.merge(df_now, df_prev, on="Ime", suffixes=('_sad', '_pre'))
            merged['Nove_Ocene'] = merged['Broj_Ocena_sad'] - merged['Broj_Ocena_pre']
            
            # MAGIJA: Procena porudžbina (Multiplier 10 - svaki deseti ocenjuje)
            merged['Procena_Porudžbina'] = merged['Nove_Ocene'] * 10
            
            st.subheader(f"Promene između {prev_ts[11:16]}h i {latest_ts[11:16]}h")
            top_prodaja = merged[merged['Nove_Ocene'] > 0].sort_values(by='Nove_Ocene', ascending=False)
            
            if not top_prodaja.empty:
                st.write("Restorani sa najvećim rastom u ovom periodu:")
                st.dataframe(top_prodaja[["Ime", "Broj_Ocena_pre", "Broj_Ocena_sad", "Nove_Ocene", "Procena_Porudžbina"]], use_container_width=True)
            else:
                st.info("Nema zabeleženih novih ocena u ovom periodu.")
        else:
            st.warning("Potrebna su bar dva snimka podataka da bi se izračunao trend. Klikni 'Snimi' više puta u razmaku od par sati.")
    else:
        st.info("Baza je prazna. Klikni 'Snimi trenutno stanje' u Sidebar-u.")

# --- TAB 3: HOT ZONE ANALITIKA (Gde je najveća gužva) ---
with tab3:
    st.title("Vrele zone dostave")
    st.write("Zone su definisane na osnovu vremena dostave i zauzetosti restorana.")
    
    df_hot = fetch_wolt_data(st.session_state.lat, st.session_state.lon, CITIES[grad_naziv]["slug"])
    
    if not df_hot.empty:
        m_heat = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=14)
        
        # HeatMap data: [lat, lon, weight] 
        # Težina (weight) je vreme dostave - što veće vreme, to je zona "crvenija" (veća gužva)
        heat_data = [[row['Lat'], row['Lon'], row['Dostava_Min']] for index, row in df_hot.iterrows()]
        
        HeatMap(heat_data, radius=25, blur=15, min_opacity=0.5).add_to(m_heat)
        
        st_folium(m_heat, width="100%", height=600, key="mapa_heat")
        
        st.write("🔴 **Crvene zone:** Restorani imaju dugačka vremena dostave (preko 45 min) ili su 'Busy'.")
        st.write("🟢 **Svetle zone:** Brza dostava, mali pritisak na kurire.")
