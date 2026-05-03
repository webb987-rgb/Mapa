import streamlit as st
from curl_cffi import requests
import pandas as pd
import folium
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim
from streamlit_autorefresh import st_autorefresh
import datetime

# --- KONFIGURACIJA ---
st.set_page_config(page_title="Wolt Market Radar PRO v9", layout="wide", page_icon="🌐")

# Gradovi (Niš postavljen na prvo mesto da bi bio default)
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

geolocator = Nominatim(user_agent="wolt_radar_v9_final")

# Inicijalizacija session state-a
if 'lat' not in st.session_state:
    st.session_state.lat, st.session_state.lon = CITIES["Niš"]
if 'timer_active' not in st.session_state:
    st.session_state.timer_active = False

# --- FUNKCIJA ZA PREUZIMANJE PODATAKA ---
@st.cache_data(ttl=60)
def fetch_wolt_data(lat, lon):
    url = "https://restaurant-api.wolt.com/v1/pages/restaurants"
    params = {"lat": lat, "lon": lon}
    kolone = ["Ime", "Status", "Radno Vreme", "Ocena", "Adresa", "Online", "Lat", "Lon"]
    
    try:
        r = requests.get(url, params=params, impersonate="chrome120", timeout=15)
        if r.status_code == 200:
            data = r.json()
            restorani = []
            for section in data.get("sections", []):
                for item in section.get("items", []):
                    v = item.get("venue")
                    if v:
                        # EKSTRAKCIJA RADNOG VREMENA (Pokušaj izvlačenja iz meta podataka)
                        raw_time = v.get("status_next_change")
                        is_online = v.get("online", False)
                        radno_vreme = "Proveri u aplikaciji"
                        
                        if raw_time:
                            try:
                                t_part = raw_time.split("T")[1][:5]
                                radno_vreme = f"Radi do {t_part}" if is_online else f"Otvara u {t_part}"
                            except: pass
                        elif v.get("delivery_specs", {}).get("delivery_times"):
                            radno_vreme = v.get("delivery_specs").get("delivery_times")

                        restorani.append({
                            "Ime": v.get("name", "Nepoznato"),
                            "Adresa": v.get("address", "Nema adrese"),
                            "Lat": v.get("location", [0, 0])[1],
                            "Lon": v.get("location", [0, 0])[0],
                            "Status": "Otvoreno 🟢" if is_online else "Zatvoreno 🔴",
                            "Online": is_online,
                            "Ocena": v.get("rating", {}).get("score", "-"),
                            "Radno Vreme": radno_vreme
                        })
            df = pd.DataFrame(restorani).drop_duplicates(subset=['Ime'])
            return df.sort_values(by="Online", ascending=False)
    except: pass
    return pd.DataFrame(columns=kolone)

# --- SIDEBAR KONTROLE ---
st.sidebar.title("🛠️ Kontrola Radara")

# 1. Izbor Grada
izabrani_grad = st.sidebar.selectbox("1. Izaberi grad:", list(CITIES.keys()), index=0)
if st.sidebar.button("📍 Centriraj grad"):
    st.session_state.lat, st.session_state.lon = CITIES[izabrani_grad]
    st.cache_data.clear()

# 2. Unos adrese (Ručno)
st.sidebar.markdown("---")
adresa_input = st.sidebar.text_input("2. Unesi adresu:", placeholder="npr. Knjaževačka 147")
if st.sidebar.button("🔍 Nađi adresu"):
    try:
        loc = geolocator.geocode(f"{adresa_input}, {izabrani_grad}, Serbia")
        if loc:
            st.session_state.lat, st.session_state.lon = loc.latitude, loc.longitude
            st.cache_data.clear()
            st.sidebar.success("Adresa locirana!")
    except:
        st.sidebar.error("Greška u pretrazi.")

# 3. Filteri
st.sidebar.markdown("---")
f_open = st.sidebar.checkbox("Samo OTVORENI", value=False)
f_closed = st.sidebar.checkbox("Samo ZATVORENI", value=False)

# 4. Tajmer
st.sidebar.markdown("---")
refresh_min = st.sidebar.number_input("Osvežavanje (min):", 1, 60, 5)
if st.sidebar.button("▶️ START AUTO-REFRESH"):
    st.session_state.timer_active = True
if st.sidebar.button("⏹️ STOP"):
    st.session_state.timer_active = False

if st.session_state.timer_active:
    st_autorefresh(interval=refresh_min * 60000, key="auto_refresh")

# --- GLAVNI PANEL ---
st.title(f"📍 Market Radar: {izabrani_grad}")
df_raw = fetch_wolt_data(st.session_state.lat, st.session_state.lon)

# Brojači
if not df_raw.empty:
    c1, c2, c3 = st.columns(3)
    c1.metric("Ukupno", len(df_raw))
    c2.metric("Otvoreno 🟢", len(df_raw[df_raw['Online'] == True]))
    c3.metric("Zatvoreno 🔴", len(df_raw[df_raw['Online'] == False]))

# Primena filtera
df_display = df_raw.copy()
if f_open and not f_closed:
    df_display = df_display[df_display['Online'] == True]
elif f_closed and not f_open:
    df_display = df_display[df_display['Online'] == False]

# --- MAPA ---
# SATELLITE TILES: Esri World Imagery (najbolji besplatni satelit)
m = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=14)

# Dodavanje slojeva: Standardni + Satelitski
folium.TileLayer('OpenStreetMap', name='Standardna Mapa').add_to(m)
folium.TileLayer(
    tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    attr='Esri',
    name='Satelitski snimak',
    overlay=False,
    control=True
).add_to(m)

folium.LayerControl().add_to(m) # Dugme za promenu mape u gornjem desnom uglu

# Pin za lokaciju
folium.Marker([st.session_state.lat, st.session_state.lon], icon=folium.Icon(color='blue', icon='home')).add_to(m)

for _, r in df_display.iterrows():
    boja = "green" if r['Online'] else "red"
    popup_html = f"<b>{r['Ime']}</b><br>Radno vreme: {r['Radno Vreme']}<br>⭐ Ocena: {r['Ocena']}"
    folium.CircleMarker(
        location=[r['Lat'], r['Lon']], radius=10, color=boja, fill=True, fill_color=boja, fill_opacity=0.7,
        tooltip=r['Ime'], popup=folium.Popup(popup_html, max_width=250)
    ).add_to(m)

st.info("💡 Klikni na mapu da promeniš tačku skeniranja ili koristi 'Satelit' opciju gore desno na mapi.")
map_data = st_folium(m, width="100%", height=600, returned_objects=["last_clicked"])

# Hvatanje klika za novu lokaciju
if map_data and map_data.get("last_clicked"):
    nl, ng = map_data["last_clicked"]["lat"], map_data["last_clicked"]["lng"]
    if (nl != st.session_state.lat) or (ng != st.session_state.lon):
        st.session_state.lat, st.session_state.lon = nl, ng
        st.cache_data.clear()
        st.rerun()

# --- TABELA ---
st.dataframe(df_display[["Ime", "Status", "Radno Vreme", "Ocena", "Adresa"]], use_container_width=True, hide_index=True)
