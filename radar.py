import streamlit as st
from curl_cffi import requests
import pandas as pd
import folium
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim
from streamlit_autorefresh import st_autorefresh
import datetime

# --- KONFIGURACIJA ---
st.set_page_config(page_title="Wolt Market Radar PRO v13", layout="wide", page_icon="🕵️")

# Gradovi (Niš prvi)
CITIES = {
    "Niš": {"coords": (43.3209, 21.8958), "slug": "nis"},
    "Beograd": {"coords": (44.7866, 20.4489), "slug": "beograd"},
    "Novi Sad": {"coords": (45.2671, 19.8335), "slug": "novi-sad"},
    "Kragujevac": {"coords": (44.0128, 20.9114), "slug": "kragujevac"},
    "Čačak": {"coords": (43.8914, 20.3502), "slug": "cacak"},
    "Kruševac": {"coords": (43.5833, 21.3267), "slug": "krusevac"},
    "Kraljevo": {"coords": (43.7258, 20.6894), "slug": "kraljevo"},
    "Novi Pazar": {"coords": (43.1407, 20.5181), "slug": "novi-pazar"},
    "Subotica": {"coords": (46.1005, 19.6651), "slug": "subotica"}
}

geolocator = Nominatim(user_agent="wolt_radar_v13_final")

# --- SESSION STATE INICIJALIZACIJA ---
if 'lat' not in st.session_state:
    st.session_state.lat, st.session_state.lon = CITIES["Niš"]["coords"]
if 'current_city' not in st.session_state:
    st.session_state.current_city = "Niš"
if 'timer_active' not in st.session_state:
    st.session_state.timer_active = False

# --- FUNKCIJA ZA PODATKE ---
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
                        v_slug = v.get("slug")
                        direct_link = f"https://wolt.com/sr/srb/{city_slug}/restaurant/{v_slug}"
                        restorani.append({
                            "Ime": v.get("name"),
                            "Adresa": v.get("address"),
                            "Lat": v.get("location", [0, 0])[1],
                            "Lon": v.get("location", [0, 0])[0],
                            "Status": "Otvoreno 🟢" if v.get("online") else "Zatvoreno 🔴",
                            "Online": v.get("online", False),
                            "Ocena": v.get("rating", {}).get("score", "-"),
                            "Wolt Link": direct_link
                        })
            df = pd.DataFrame(restorani).drop_duplicates(subset=['Ime'])
            return df.sort_values(by="Online", ascending=False)
    except: pass
    return pd.DataFrame()

# --- SIDEBAR KONTROLE ---
st.sidebar.title("🛠️ Kontrola Radara")

# 1. Automatski refresh na promenu grada
grad_naziv = st.sidebar.selectbox("1. Izaberi grad:", list(CITIES.keys()))

if grad_naziv != st.session_state.current_city:
    st.session_state.current_city = grad_naziv
    st.session_state.lat, st.session_state.lon = CITIES[grad_naziv]["coords"]
    st.cache_data.clear()
    st.rerun()

# 2. Unos adrese
st.sidebar.markdown("---")
adresa_input = st.sidebar.text_input("2. Unesi adresu:", placeholder="npr. Knjaževačka 147")
if st.sidebar.button("🔍 Nadji adresu"):
    try:
        loc = geolocator.geocode(f"{adresa_input}, {grad_naziv}, Serbia")
        if loc:
            st.session_state.lat, st.session_state.lon = loc.latitude, loc.longitude
            st.cache_data.clear()
            st.rerun()
    except: st.sidebar.error("Nije nađeno.")

# 3. Filteri
st.sidebar.markdown("---")
f_open = st.sidebar.checkbox("Samo OTVORENI")
f_closed = st.sidebar.checkbox("Samo ZATVORENI")

# 4. Tajmer
st.sidebar.markdown("---")
interval = st.sidebar.number_input("Refresh (min):", 1, 60, 5)
if st.sidebar.button("▶️ START AUTO-REFRESH"): st.session_state.timer_active = True
if st.sidebar.button("⏹️ STOP"): st.session_state.timer_active = False

if st.session_state.timer_active:
    st_autorefresh(interval=interval*60000, key="v13_refresh")

# --- GLAVNI PANEL ---
st.title(f"📍 Market Radar: {grad_naziv}")
st.caption(f"Poslednji sken: {datetime.datetime.now().strftime('%H:%M:%S')}")

df_raw = fetch_wolt_data(st.session_state.lat, st.session_state.lon, CITIES[grad_naziv]["slug"])

# Brojači
if not df_raw.empty:
    c1, c2, c3 = st.columns(3)
    c1.metric("Ukupno", len(df_raw))
    c2.metric("Otvoreno 🟢", len(df_raw[df_raw['Online'] == True]))
    c3.metric("Zatvoreno 🔴", len(df_raw[df_raw['Online'] == False]))

df_display = df_raw.copy()
if f_open and not f_closed: df_display = df_display[df_display['Online'] == True]
elif f_closed and not f_open: df_display = df_display[df_display['Online'] == False]

# --- MAPA ---
st.info("💡 Klikni na mapu da promeniš tačku skeniranja ili izaberi grad levo.")
m = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=14, tiles="OpenStreetMap")
folium.Marker([st.session_state.lat, st.session_state.lon], icon=folium.Icon(color='blue', icon='home')).add_to(m)

for _, r in df_display.iterrows():
    boja = "green" if r['Online'] else "red"
    folium.CircleMarker(
        [r['Lat'], r['Lon']], radius=10, color=boja, fill=True, fill_color=boja, fill_opacity=0.7, 
        tooltip=r['Ime'], popup=f"<b>{r['Ime']}</b><br>Ocena: {r['Ocena']}"
    ).add_to(m)

map_data = st_folium(m, width="100%", height=500, returned_objects=["last_clicked"])

if map_data and map_data.get("last_clicked"):
    nl, ng = map_data["last_clicked"]["lat"], map_data["last_clicked"]["lng"]
    if (nl != st.session_state.lat) or (ng != st.session_state.lon):
        st.session_state.lat, st.session_state.lon = nl, ng
        st.cache_data.clear()
        st.rerun()

# --- TABELA ---
st.dataframe(
    df_display[["Ime", "Status", "Ocena", "Adresa", "Wolt Link"]],
    use_container_width=True,
    hide_index=True,
    column_config={"Wolt Link": st.column_config.LinkColumn("Direktan Link", display_text="Otvori 🔗")}
)
