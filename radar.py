import streamlit as st
from curl_cffi import requests
import pandas as pd
import folium
from streamlit_folium import st_folium
from streamlit_autorefresh import st_autorefresh
import datetime

# --- KONFIGURACIJA ---
st.set_page_config(page_title="Wolt Market Radar v8", layout="wide", page_icon="🕵️")

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

# --- KEŠIRANJE (Rešava problem sivila i brzine) ---
@st.cache_data(ttl=60)  # Podaci se čuvaju 60 sekundi u memoriji
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
                        # ISPRAVKA RADNOG VREMENA:
                        # Tražimo informaciju o sledećoj promeni statusa (npr. "Zatvara se u 23:00")
                        next_change = v.get("delivery_specs", {}).get("delivery_times", "Info u aplikaciji")
                        
                        # Ako nema specifičnog vremena, koristimo polje koje Wolt popunjava za 'vreme rada'
                        vreme_info = v.get("status_next_change")
                        if vreme_info:
                            # Pretvaramo ISO vreme u čitljiv format ako postoji
                            try:
                                dt = datetime.datetime.fromisoformat(vreme_info.replace('Z', '+00:00'))
                                radno_vreme = f"Promena u {dt.strftime('%H:%M')}"
                            except:
                                radno_vreme = "Proveri u aplikaciji"
                        else:
                            radno_vreme = "Nije navedeno"

                        restorani.append({
                            "Ime": v.get("name", "Nepoznato"),
                            "Adresa": v.get("address", "Nema adrese"),
                            "Lat": v.get("location", [0, 0])[1],
                            "Lon": v.get("location", [0, 0])[0],
                            "Status": "Otvoreno 🟢" if v.get("online") else "Zatvoreno 🔴",
                            "Online": v.get("online", False),
                            "Ocena": v.get("rating", {}).get("score", "-"),
                            "Radno Vreme": radno_vreme
                        })
            df = pd.DataFrame(restorani).drop_duplicates(subset=['Ime'])
            return df.sort_values(by="Online", ascending=False)
    except:
        pass
    return pd.DataFrame(columns=kolone)

# --- SESSION STATE ---
if 'lat' not in st.session_state:
    st.session_state.lat, st.session_state.lon = CITIES["Niš"]
if 'timer_active' not in st.session_state:
    st.session_state.timer_active = False

# --- SIDEBAR ---
st.sidebar.title("🛠️ Kontrola Radara")
grad = st.sidebar.selectbox("1. Izaberi grad:", list(CITIES.keys()))
if st.sidebar.button("📍 Centriraj grad"):
    st.session_state.lat, st.session_state.lon = CITIES[grad]
    st.cache_data.clear() # Brišemo keš da odmah povuče novi grad

st.sidebar.markdown("---")
filter_open = st.sidebar.checkbox("Samo OTVORENI", value=False)
filter_closed = st.sidebar.checkbox("Samo ZATVORENI", value=False)

st.sidebar.markdown("---")
refresh_min = st.sidebar.number_input("Interval (min):", 1, 60, 5)
if st.sidebar.button("▶️ START REFRESH"):
    st.session_state.timer_active = True
if st.sidebar.button("⏹️ STOP"):
    st.session_state.timer_active = False

if st.session_state.timer_active:
    st_autorefresh(interval=refresh_min * 60000, key="auto_refresh")

# --- GLAVNI PANEL ---
st.title(f"📍 Market Radar: {grad}")
df_raw = fetch_wolt_data(st.session_state.lat, st.session_state.lon)

# Brojači
if not df_raw.empty:
    c1, c2, c3 = st.columns(3)
    c1.metric("Ukupno", len(df_raw))
    c2.metric("Otvoreno 🟢", len(df_raw[df_raw['Online'] == True]))
    c3.metric("Zatvoreno 🔴", len(df_raw[df_raw['Online'] == False]))

# Filteri
df_display = df_raw.copy()
if filter_open and not filter_closed:
    df_display = df_display[df_display['Online'] == True]
elif filter_closed and not filter_open:
    df_display = df_display[df_display['Online'] == False]

# --- MAPA (OpenStreetMap sa optimizacijom) ---
m = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=17, tiles="OpenStreetMap")
folium.Marker([st.session_state.lat, st.session_state.lon], icon=folium.Icon(color='blue', icon='home')).add_to(m)

for _, r in df_display.iterrows():
    boja = "green" if r['Online'] else "red"
    popup_html = f"<b>{r['Ime']}</b><br>Status: {r['Status']}<br>Radno vreme: {r['Radno Vreme']}<br>⭐ Ocena: {r['Ocena']}"
    folium.CircleMarker(
        location=[r['Lat'], r['Lon']],
        radius=10, color=boja, fill=True, fill_color=boja, fill_opacity=0.7,
        tooltip=r['Ime'], popup=folium.Popup(popup_html, max_width=250)
    ).add_to(m)

# st_folium sa returned_objects optimizacijom sprečava stalni refresh
map_data = st_folium(m, width="100%", height=600, returned_objects=["last_clicked"])

if map_data and map_data.get("last_clicked"):
    nl, ng = map_data["last_clicked"]["lat"], map_data["last_clicked"]["lng"]
    if (nl != st.session_state.lat) or (ng != st.session_state.lon):
        st.session_state.lat, st.session_state.lon = nl, ng
        st.cache_data.clear() # Brišemo keš jer smo promenili lokaciju
        st.rerun()

# --- TABELA ---
st.dataframe(df_display[["Ime", "Status", "Radno Vreme", "Ocena", "Adresa"]], use_container_width=True, hide_index=True)
