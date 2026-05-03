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

# --- 1. KONFIGURACIJA ---
st.set_page_config(page_title="Wolt BI Radar Pro v16.1", layout="wide", page_icon="🕵️")

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

DB_FILE = "radar_history.csv"
geolocator = Nominatim(user_agent="wolt_radar_v16_final")

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
                        rating_data = v.get("rating", {})
                        restorani.append({
                            "Ime": v.get("name"),
                            "Adresa": v.get("address"),
                            "Lat": v.get("location", [0, 0])[1],
                            "Lon": v.get("location", [0, 0])[0],
                            "Status": "Otvoreno 🟢" if v.get("online") else "Zatvoreno 🔴",
                            "Online": v.get("online", False),
                            "Ocena": rating_data.get("score", 0),
                            "Broj_Ocena": rating_data.get("volume", 0),
                            "ETA": v.get("estimate", 30),
                            "Wolt Link": f"https://wolt.com/sr/srb/{city_slug}/restaurant/{v.get('slug')}"
                        })
            df = pd.DataFrame(restorani).drop_duplicates(subset=['Ime'])
            return df.sort_values(by="Online", ascending=False)
    except: pass
    return pd.DataFrame()

def save_to_history(df):
    if not df.empty:
        df_save = df.copy()
        df_save['timestamp'] = datetime.datetime.now()
        if not os.path.isfile(DB_FILE):
            df_save.to_csv(DB_FILE, index=False)
        else:
            df_save.to_csv(DB_FILE, mode='a', header=False, index=False)

# --- 4. SIDEBAR ---
st.sidebar.title("🛠️ Kontrolna Tabla")
grad_naziv = st.sidebar.selectbox("1. Izaberi grad:", list(CITIES.keys()))

if grad_naziv != st.session_state.current_city:
    st.session_state.current_city = grad_naziv
    st.session_state.lat, st.session_state.lon = CITIES[grad_naziv]["coords"]
    st.cache_data.clear()
    st.rerun()

adresa_input = st.sidebar.text_input("2. Unesi adresu:", placeholder="npr. Knjaževačka 147")
if st.sidebar.button("🔍 Pronađi"):
    try:
        loc = geolocator.geocode(f"{adresa_input}, {grad_naziv}, Serbia")
        if loc:
            st.session_state.lat, st.session_state.lon = loc.latitude, loc.longitude
            st.cache_data.clear()
            st.rerun()
    except: st.sidebar.error("Adresa nije nađena.")

st.sidebar.markdown("---")
if st.sidebar.button("💾 SNIMI TRENUTNO STANJE"):
    curr_df = fetch_wolt_data(st.session_state.lat, st.session_state.lon, CITIES[grad_naziv]["slug"])
    save_to_history(curr_df)
    st.sidebar.success("Podaci arhivirani!")

st.sidebar.markdown("---")
interval = st.sidebar.number_input("Refresh (min):", 1, 60, 5)
if st.sidebar.button("▶️ START AUTO-REFRESH"): st.session_state.timer_active = True
if st.sidebar.button("⏹️ STOP"): st.session_state.timer_active = False

if st.session_state.timer_active:
    st_autorefresh(interval=interval*60000, key="global_refresh")

# --- 5. GLAVNI PANEL (TABOVI) ---
tab1, tab2, tab3 = st.tabs(["🗺️ Radar Mapa", "📈 Traffic Tracker", "🔥 Dostava HeatMap"])

# POVLAČENJE PODATAKA (Zajedničko za tabove)
df_main = fetch_wolt_data(st.session_state.lat, st.session_state.lon, CITIES[grad_naziv]["slug"])

# --- TAB 1: RADAR MAPA (OPERATIVNA) ---
with tab1:
    st.title(f"📍 Market Radar: {grad_naziv}")
    if not df_main.empty:
        c1, c2, c3 = st.columns(3)
        c1.metric("Ukupno", len(df_main))
        c2.metric("Otvoreno 🟢", len(df_main[df_main['Online'] == True]))
        c3.metric("Zatvoreno 🔴", len(df_main[df_main['Online'] == False]))

        st.info("💡 Klikni na mapu za novu tačku skeniranja.")
        
        m1 = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=14)
        folium.Marker([st.session_state.lat, st.session_state.lon], icon=folium.Icon(color='blue', icon='home')).add_to(m1)
        
        for _, r in df_main.iterrows():
            boja = "green" if r['Online'] else "red"
            folium.CircleMarker(
                [r['Lat'], r['Lon']], radius=9, color=boja, fill=True, fill_opacity=0.7,
                tooltip=r['Ime'], popup=f"<b>{r['Ime']}</b><br>Ocena: {r['Ocena']}"
            ).add_to(m1)
        
        map_out = st_folium(m1, width="100%", height=500, key="map_radar_main")
        
        if map_out and map_out.get("last_clicked"):
            nl, ng = map_out["last_clicked"]["lat"], map_out["last_clicked"]["lng"]
            if (nl != st.session_state.lat) or (ng != st.session_state.lon):
                st.session_state.lat, st.session_state.lon = nl, ng
                st.cache_data.clear()
                st.rerun()

        st.dataframe(
            df_main[["Ime", "Status", "Ocena", "ETA", "Adresa", "Wolt Link"]],
            use_container_width=True, hide_index=True,
            column_config={"Wolt Link": st.column_config.LinkColumn("Link", display_text="Otvori 🔗")}
        )

# --- TAB 2: TRAFFIC TRACKER (BI) ---
with tab2:
    st.title("📈 Analiza prodaje")
    if os.path.exists(DB_FILE):
        hist = pd.read_csv(DB_FILE)
        hist['timestamp'] = pd.to_datetime(hist['timestamp'])
        ts = sorted(hist['timestamp'].unique())
        if len(ts) >= 2:
            t_now, t_prev = ts[-1], ts[-2]
            df_now, df_prev = hist[hist['timestamp'] == t_now], hist[hist['timestamp'] == t_prev]
            merged = pd.merge(df_now, df_prev, on="Ime", suffixes=('_sad', '_pre'))
            merged['Nove_Ocene'] = merged['Broj_Ocena_sad'] - merged['Broj_Ocena_pre']
            merged['Procena_Porudžbina'] = merged['Nove_Ocene'] * 10
            st.subheader(f"Period: {t_prev.strftime('%H:%M')}h -> {t_now.strftime('%H:%M')}h")
            top = merged[merged['Nove_Ocene'] > 0].sort_values(by='Nove_Ocene', ascending=False)
            st.dataframe(top[["Ime", "Nove_Ocene", "Procena_Porudžbina"]], use_container_width=True, hide_index=True)
        else: st.warning("Potrebno je više snimaka podataka u bazi.")
    else: st.info("Baza je prazna. Klikni 'Snimi' u sidebar-u.")

# --- TAB 3: HEATMAP (LOGISTIKA) ---
with tab3:
    st.title("🔥 Mapa kašnjenja i gužve")
    st.write("Što je zona **CRVENIJA**, to kupci duže čekaju na dostavu (ETA).")
    
    m_heat = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=14)
    
    if not df_main.empty:
        df_active = df_main[df_main['Online'] == True]
        if not df_active.empty:
            # Priprema: [lat, lon, weight] - weight je ETA
            heat_data = [[float(r['Lat']), float(r['Lon']), int(r['ETA'])] for _, r in df_active.iterrows()]
            HeatMap(heat_data, radius=35, blur=20, min_opacity=0.4).add_to(m_heat)
        else:
            st.warning("Trenutno nema otvorenih restorana za analizu.")
    
    # Render mape je van uslova da bi uvek bio prikazan
    st_folium(m_heat, width="100%", height=600, key="map_heatmap_bi")

    st.markdown("""
    ---
    - 🔴 **Vrele tačke:** Visok ETA (preko 40 min). Gužva u kuhinji ili manjak kurira u tom krugu.
    - 🔵 **Hladne tačke:** Dostava je brza (ispod 25 min).
    """)
