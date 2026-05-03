import streamlit as st
from curl_cffi import requests
import pandas as pd
import folium
from streamlit_folium import st_folium, folium_static 
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
from streamlit_autorefresh import st_autorefresh
import datetime
import os

# --- 1. KONFIGURACIJA ---
st.set_page_config(page_title="Wolt Market Radar v19", layout="wide", page_icon="🕵️")

CITIES = {
    "Niš": {"coords": (43.3209, 21.8958), "slug": "nis"},
    "Beograd": {"coords": (44.7866, 20.4489), "slug": "beograd"},
    "Novi Sad": {"coords": (45.2671, 19.8335), "slug": "novi-sad"}
}

DB_FILE = "radar_history.csv"
geolocator = Nominatim(user_agent="wolt_radar_v19")

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
                        dist = geodesic(user_coords, r_coords).km
                        eta_raw = v.get("estimate", 30)
                        try:
                            eta = int(str(eta_raw).split('-')[0])
                        except: eta = 30
                        
                        restorani.append({
                            "Ime": v.get("name"),
                            "Adresa": v.get("address"),
                            "Lat": r_coords[0], "Lon": r_coords[1],
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
if st.sidebar.button("💾 SNIMI ZA TRAFFIC"):
    df_s = fetch_wolt_data(st.session_state.lat, st.session_state.lon, CITIES[grad_naziv]["slug"])
    if not df_s.empty:
        df_s['timestamp'] = datetime.datetime.now()
        df_s.to_csv(DB_FILE, mode='a', header=not os.path.exists(DB_FILE), index=False)
        st.sidebar.success("Snimljeno!")

# --- 5. TABOVI ---
# Prvi tab je sada onaj stari koji najviše koristiš
tab1, tab2, tab3 = st.tabs(["🟢 Otvoreno / Zatvoreno", "🔥 Mapa Efikasnosti Dostave", "📈 Traffic Tracker"])

df_main = fetch_wolt_data(st.session_state.lat, st.session_state.lon, CITIES[grad_naziv]["slug"])

# --- TAB 1: OTVORENO / ZATVORENO ---
with tab1:
    st.title(f"📊 Radar Stanje: {grad_naziv}")
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
        
        resp = st_folium(m1, width="100%", height=500, key="radar_v19")
        if resp and resp.get("last_clicked"):
            st.session_state.lat, st.session_state.lon = resp["last_clicked"]["lat"], resp["last_clicked"]["lng"]
            st.cache_data.clear()
            st.rerun()
        
        st.dataframe(df_main[["Ime", "Status", "Ocena", "ETA", "Distanca_km", "Wolt Link"]], use_container_width=True, hide_index=True)

# --- TAB 2: MAPA EFIKASNOSTI (Prava vizuelna logika) ---
with tab2:
    st.title("🚀 Analiza brzine stizanja hrane")
    st.markdown("""
    - **Zelene zone:** Hrana stiže brzo (ispod 25 min).
    - **Žute zone:** Srednje vreme čekanja (25-45 min).
    - **Crvene zone:** Čekaćete dugo (preko 45 min ili velika udaljenost).
    """)
    
    m2 = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=14)
    folium.Marker([st.session_state.lat, st.session_state.lon], icon=folium.Icon(color='black', icon='info-sign')).add_to(m2)

    if not df_main.empty:
        df_active = df_main[df_main['Online'] == True].copy()
        
        for _, r in df_active.iterrows():
            # LOGIKA BOJA NA OSNOVU ETA
            if r['ETA'] <= 25:
                boja_zone = "green"
            elif 25 < r['ETA'] <= 45:
                boja_zone = "orange"
            else:
                boja_zone = "red"
            
            # CRTAMO ZONE: Veliki krugovi koji se preklapaju ali ne sabiraju boju
            folium.Circle(
                location=[r['Lat'], r['Lon']],
                radius=400, # Radijus u metrima (pokriva zonu oko restorana)
                color=boja_zone,
                fill=True,
                fill_color=boja_zone,
                fill_opacity=0.2, # Mala providnost da se vidi mapa ispod
                weight=1,
                tooltip=f"{r['Ime']}: {r['ETA']} min"
            ).add_to(m2)

    folium_static(m2, width=1200)

# --- TAB 3: TRAFFIC ---
with tab3:
    st.title("📈 Traffic Tracker")
    if os.path.exists(DB_FILE):
        h = pd.read_csv(DB_FILE)
        # ... tvoja logika ...
        st.info("Poredi snimke iz baze da vidiš ko raste.")
    else: st.info("Baza je prazna.")
