import streamlit as st
from curl_cffi import requests
import pandas as pd
import folium
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim
from streamlit_autorefresh import st_autorefresh
import datetime

# --- KONFIGURACIJA ---
st.set_page_config(page_title="Wolt Market Radar v10", layout="wide", page_icon="🌐")

# Gradovi (Niš prvi)
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

geolocator = Nominatim(user_agent="wolt_radar_v10_final")

# Session State
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
                        # --- EKSTREMNO PRECIZNO RADNO VREME ---
                        is_online = v.get("online", False)
                        next_change = v.get("status_next_change") # Format: 2026-05-03T21:00:00Z
                        vreme_label = "Info u aplikaciji"
                        
                        if next_change:
                            try:
                                # Izvlačimo samo sate i minute (npr. 21:00)
                                t_str = next_change.split("T")[1][:5]
                                # Korekcija za vremensku zonu (opciono, ali Wolt šalje UTC)
                                h = int(t_str[:2]) + 2 # Približno za Srbiju (CEST)
                                if h >= 24: h -= 24
                                t_final = f"{h:02d}:{t_str[3:]}"
                                
                                if is_online:
                                    vreme_label = f"Radi do {t_final}"
                                else:
                                    vreme_label = f"Otvara u {t_final}"
                            except:
                                vreme_label = "Proveri sate"
                        
                        restorani.append({
                            "Ime": v.get("name"),
                            "Adresa": v.get("address"),
                            "Lat": v.get("location", [0, 0])[1],
                            "Lon": v.get("location", [0, 0])[0],
                            "Status": "Otvoreno 🟢" if is_online else "Zatvoreno 🔴",
                            "Online": is_online,
                            "Ocena": v.get("rating", {}).get("score", "-"),
                            "Radno Vreme": vreme_label
                        })
            df = pd.DataFrame(restorani).drop_duplicates(subset=['Ime'])
            return df.sort_values(by="Online", ascending=False)
    except: pass
    return pd.DataFrame()

# --- SIDEBAR ---
st.sidebar.title("🛠️ Kontrola")
grad = st.sidebar.selectbox("1. Grad:", list(CITIES.keys()))
if st.sidebar.button("📍 Centriraj na ovaj grad"):
    st.session_state.lat, st.session_state.lon = CITIES[grad]
    st.cache_data.clear()

st.sidebar.markdown("---")
adresa_input = st.sidebar.text_input("2. Specifična adresa:", placeholder="npr. Knjaževačka 147")
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
if st.session_state.timer_active: st_autorefresh(interval=interval*60000, key="rfrsh")

# --- GLAVNI PANEL ---
st.title(f"📍 Radar: {grad}")
df_raw = fetch_wolt_data(st.session_state.lat, st.session_state.lon)

if not df_raw.empty:
    c1, c2, c3 = st.columns(3)
    c1.metric("Ukupno", len(df_raw))
    c2.metric("Otvoreno 🟢", len(df_raw[df_raw['Online'] == True]))
    c3.metric("Zatvoreno 🔴", len(df_raw[df_raw['Online'] == False]))

df_display = df_raw.copy()
if f_open and not f_closed: df_display = df_display[df_display['Online'] == True]
elif f_closed and not f_open: df_display = df_display[df_display['Online'] == False]

# --- MAPA ---
# Default je "OpenStreetMap" (Mapa), Satelit je opcija
m = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=14, tiles="OpenStreetMap")

# Dodajemo Satelit kao opciju
folium.TileLayer(
    tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    attr='Esri', name='Satelit', overlay=False
).add_to(m)
folium.LayerControl().add_to(m)

# Pinovi
folium.Marker([st.session_state.lat, st.session_state.lon], icon=folium.Icon(color='blue', icon='home')).add_to(m)
for _, r in df_display.iterrows():
    boja = "green" if r['Online'] else "red"
    pop = f"<b>{r['Ime']}</b><br>{r['Radno Vreme']}<br>Ocena: {r['Ocena']}"
    folium.CircleMarker([r['Lat'], r['Lon']], radius=10, color=boja, fill=True, fill_color=boja, fill_opacity=0.7, tooltip=r['Ime'], popup=folium.Popup(pop, max_width=200)).add_to(m)

st.info("💡 Klikni na mapu za novu tačku ili kucaj adresu levo.")
map_data = st_folium(m, width="100%", height=600, returned_objects=["last_clicked"])

if map_data and map_data.get("last_clicked"):
    nl, ng = map_data["last_clicked"]["lat"], map_data["last_clicked"]["lng"]
    if (nl != st.session_state.lat) or (ng != st.session_state.lon):
        st.session_state.lat, st.session_state.lon = nl, ng
        st.cache_data.clear()
        st.rerun()

st.dataframe(df_display[["Ime", "Status", "Radno Vreme", "Ocena", "Adresa"]], use_container_width=True, hide_index=True)
