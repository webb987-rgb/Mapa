import streamlit as st
from curl_cffi import requests
import pandas as pd
import folium
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim
from streamlit_autorefresh import st_autorefresh
import datetime

# --- KONFIGURACIJA ---
st.set_page_config(page_title="Wolt Market Radar PRO", layout="wide", page_icon="🌐")

# Niš je prvi na listi (Default)
CITIES = {
    "Niš": (43.3209, 21.8958),
    "Beograd": (44.7866, 20.4489),
    "Novi Sad": (45.2671, 19.8335),
    "Kragujevac": (44.0128, 20.9114),
    "Čačak": (43.8914, 20.3502),
    "Kruševac": (43.5833, 21.3267),
    "Kraljevo": (43.7258, 20.6894),
    "Novi Pazar": (43.1407, 20.5181),
    "Subotica": (46.1005, 19.6651)
}

geolocator = Nominatim(user_agent="wolt_radar_v11")

if 'lat' not in st.session_state:
    st.session_state.lat, st.session_state.lon = CITIES["Niš"]
if 'timer_active' not in st.session_state:
    st.session_state.timer_active = False

# --- FUNKCIJA ZA PODATKE ---
@st.cache_data(ttl=60)
def fetch_wolt_data(lat, lon):
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
                        ime = v.get("name")
                        slug = v.get("slug")
                        # Pravimo direktan link ka Wolt stranici restorana
                        wolt_link = f"https://wolt.com/sr/search?q={ime.replace(' ', '%20')}"
                        
                        restorani.append({
                            "Ime": ime,
                            "Adresa": v.get("address"),
                            "Lat": v.get("location", [0, 0])[1],
                            "Lon": v.get("location", [0, 0])[0],
                            "Status": "Otvoreno 🟢" if v.get("online") else "Zatvoreno 🔴",
                            "Online": v.get("online", False),
                            "Ocena": v.get("rating", {}).get("score", "-"),
                            "Wolt Link": wolt_link
                        })
            df = pd.DataFrame(restorani).drop_duplicates(subset=['Ime'])
            return df.sort_values(by="Online", ascending=False)
    except: pass
    return pd.DataFrame()

# --- SIDEBAR ---
st.sidebar.title("🛠️ Kontrola Radara")
grad = st.sidebar.selectbox("1. Grad:", list(CITIES.keys()))
if st.sidebar.button("📍 Centriraj na ovaj grad"):
    st.session_state.lat, st.session_state.lon = CITIES[grad]
    st.cache_data.clear()

st.sidebar.markdown("---")
adresa_input = st.sidebar.text_input("2. Unesi adresu:", placeholder="npr. Knjaževačka 147")
if st.sidebar.button("🔍 Nadji adresu"):
    try:
        loc = geolocator.geocode(f"{adresa_input}, {grad}, Serbia")
        if loc:
            st.session_state.lat, st.session_state.lon = loc.latitude, loc.longitude
            st.cache_data.clear()
    except: st.sidebar.error("Nije nađeno.")

st.sidebar.markdown("---")
f_open = st.sidebar.checkbox("Samo OTVORENI")
f_closed = st.sidebar.checkbox("Samo ZATVORENI")

st.sidebar.markdown("---")
interval = st.sidebar.number_input("Refresh (min):", 1, 60, 5)
if st.sidebar.button("▶️ START"): st.session_state.timer_active = True
if st.sidebar.button("⏹️ STOP"): st.session_state.timer_active = False

if st.session_state.timer_active:
    st_autorefresh(interval=interval*60000, key="v11_refresh")

# --- GLAVNI PANEL ---
st.title(f"📍 Market Radar: {grad}")
df_raw = fetch_wolt_data(st.session_state.lat, st.session_state.lon)

# Brojači (Metrike)
if not df_raw.empty:
    c1, c2, c3 = st.columns(3)
    c1.metric("Ukupno na lokaciji", len(df_raw))
    c2.metric("Otvoreno 🟢", len(df_raw[df_raw['Online'] == True]))
    c3.metric("Zatvoreno 🔴", len(df_raw[df_raw['Online'] == False]))

df_display = df_raw.copy()
if f_open and not f_closed: df_display = df_display[df_display['Online'] == True]
elif f_closed and not f_open: df_display = df_display[df_display['Online'] == False]

# --- MAPA (Default: OpenStreetMap) ---
m = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=14, tiles="OpenStreetMap")

# Dodavanje satelita kao opcije (ne kao default)
folium.TileLayer(
    tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    attr='Esri', name='Satelitski pregled', overlay=False
).add_to(m)
folium.LayerControl().add_to(m)

# Pinovi na mapi
folium.Marker([st.session_state.lat, st.session_state.lon], icon=folium.Icon(color='blue', icon='home')).add_to(m)
for _, r in df_display.iterrows():
    boja = "green" if r['Online'] else "red"
    folium.CircleMarker(
        [r['Lat'], r['Lon']], radius=10, color=boja, fill=True, fill_color=boja, fill_opacity=0.7, 
        tooltip=r['Ime'], popup=f"<b>{r['Ime']}</b><br>Ocena: {r['Ocena']}"
    ).add_to(m)

st.info("💡 Klikni na mapu da promeniš tačku skeniranja. Satelit možeš upaliti u gornjem desnom uglu mape.")
map_data = st_folium(m, width="100%", height=500, returned_objects=["last_clicked"])

if map_data and map_data.get("last_clicked"):
    nl, ng = map_data["last_clicked"]["lat"], map_data["last_clicked"]["lng"]
    if (nl != st.session_state.lat) or (ng != st.session_state.lon):
        st.session_state.lat, st.session_state.lon = nl, ng
        st.cache_data.clear()
        st.rerun()

# --- TABELA SA LINKOVIMA ---
st.markdown("### 📋 Spisak restorana")
# Koristimo st.column_config da link bude klikabilan
st.dataframe(
    df_display[["Ime", "Status", "Ocena", "Adresa", "Wolt Link"]],
    use_container_width=True,
    hide_index=True,
    column_config={
        "Wolt Link": st.column_config.LinkColumn("Link do restorana", display_text="Otvori na Woltu 🔗")
    }
)
