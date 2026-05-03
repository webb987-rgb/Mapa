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

# --- 1. KONFIGURACIJA (Mora biti prva) ---
st.set_page_config(page_title="Wolt Market Radar Pro v16", layout="wide", page_icon="🕵️")

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

geolocator = Nominatim(user_agent="wolt_radar_v16")

# --- 3. FUNKCIJE ZA PODATKE ---
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
                        # BI Podaci: Ocene i procenjeno vreme (ETA)
                        volume = v.get("rating", {}).get("volume", 0)
                        eta = v.get("estimate", 30) # Default 30 min ako nema podataka
                        
                        restorani.append({
                            "Ime": v.get("name"),
                            "Adresa": v.get("address"),
                            "Lat": v.get("location", [0, 0])[1],
                            "Lon": v.get("location", [0, 0])[0],
                            "Status": "Otvoreno 🟢" if v.get("online") else "Zatvoreno 🔴",
                            "Online": v.get("online", False),
                            "Ocena": v.get("rating", {}).get("score", "-"),
                            "Broj_Ocena": volume,
                            "ETA": eta,
                            "Wolt Link": f"https://wolt.com/sr/srb/{city_slug}/restaurant/{v.get('slug')}"
                        })
            df = pd.DataFrame(restorani).drop_duplicates(subset=['Ime'])
            return df.sort_values(by="Online", ascending=False)
    except: pass
    return pd.DataFrame()

def save_to_history(df):
    df_to_save = df.copy()
    df_to_save['timestamp'] = datetime.datetime.now()
    if not os.path.isfile(DB_FILE):
        df_to_save.to_csv(DB_FILE, index=False)
    else:
        df_to_save.to_csv(DB_FILE, mode='a', header=False, index=False)

# --- 4. SIDEBAR ---
st.sidebar.title("🛠️ Kontrolna Tabla")
grad_naziv = st.sidebar.selectbox("1. Grad:", list(CITIES.keys()))

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
    df_for_save = fetch_wolt_data(st.session_state.lat, st.session_state.lon, CITIES[grad_naziv]["slug"])
    save_to_history(df_for_save)
    st.sidebar.success("Snimljeno u istoriju!")

st.sidebar.markdown("---")
interval = st.sidebar.number_input("Refresh (min):", 1, 60, 5)
if st.sidebar.button("▶️ START REFRESH"): st.session_state.timer_active = True
if st.sidebar.button("⏹️ STOP"): st.session_state.timer_active = False

if st.session_state.timer_active:
    st_autorefresh(interval=interval*60000, key="auto_rfrsh")

# --- 5. GLAVNI PANEL (TABOVI) ---
tab1, tab2, tab3 = st.tabs(["🗺️ Radar Mapa", "📈 Traffic Tracker", "🔥 Dostava HeatMap"])

# --- TAB 1: RADAR MAPA (RESTAURACIJA v13) ---
with tab1:
    st.title(f"📍 Market Radar: {grad_naziv}")
    st.caption(f"Poslednji sken: {datetime.datetime.now().strftime('%H:%M:%S')}")
    
    df = fetch_wolt_data(st.session_state.lat, st.session_state.lon, CITIES[grad_naziv]["slug"])
    
    if not df.empty:
        # Brojači
        c1, c2, c3 = st.columns(3)
        c1.metric("Ukupno", len(df))
        c2.metric("Otvoreno 🟢", len(df[df['Online'] == True]))
        c3.metric("Zatvoreno 🔴", len(df[df['Online'] == False]))

        st.info("💡 Klikni na mapu da promeniš lokaciju skeniranja.")
        
        # Mapa
        m = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=14, tiles="OpenStreetMap")
        folium.Marker([st.session_state.lat, st.session_state.lon], icon=folium.Icon(color='blue', icon='home')).add_to(m)
        
        for _, r in df.iterrows():
            boja = "green" if r['Online'] else "red"
            folium.CircleMarker(
                [r['Lat'], r['Lon']], radius=9, color=boja, fill=True, fill_opacity=0.7,
                tooltip=r['Ime'], popup=f"<b>{r['Ime']}</b><br>Ocena: {r['Ocena']}<br>ETA: {r['ETA']} min"
            ).add_to(m)
        
        map_data = st_folium(m, width="100%", height=500, key="tab1_map")
        
        if map_data and map_data.get("last_clicked"):
            nl, ng = map_data["last_clicked"]["lat"], map_data["last_clicked"]["lng"]
            if (nl != st.session_state.lat) or (ng != st.session_state.lon):
                st.session_state.lat, st.session_state.lon = nl, ng
                st.cache_data.clear()
                st.rerun()

        # Tabela
        st.dataframe(
            df[["Ime", "Status", "Ocena", "ETA", "Adresa", "Wolt Link"]],
            use_container_width=True, hide_index=True,
            column_config={"Wolt Link": st.column_config.LinkColumn("Link", display_text="Otvori 🔗")}
        )

# --- TAB 2: TRAFFIC TRACKER ---
with tab2:
    st.title("📈 Procena prodaje na osnovu ocena")
    if os.path.exists(DB_FILE):
        hist = pd.read_csv(DB_FILE)
        hist['timestamp'] = pd.to_datetime(hist['timestamp'])
        
        timestamps = sorted(hist['timestamp'].unique())
        if len(timestamps) >= 2:
            t_now = timestamps[-1]
            t_prev = timestamps[-2]
            
            df_now = hist[hist['timestamp'] == t_now]
            df_prev = hist[hist['timestamp'] == t_prev]
            
            merged = pd.merge(df_now, df_prev, on="Ime", suffixes=('_sad', '_pre'))
            merged['Nove_Ocene'] = merged['Broj_Ocena_sad'] - merged['Broj_Ocena_pre']
            merged['Procena_Porudžbina'] = merged['Nove_Ocene'] * 10
            
            st.subheader(f"Analiza: {t_prev.strftime('%H:%M')} -> {t_now.strftime('%H:%M')}")
            res = merged[merged['Nove_Ocene'] > 0].sort_values(by='Nove_Ocene', ascending=False)
            st.dataframe(res[["Ime", "Nove_Ocene", "Procena_Porudžbina"]], use_container_width=True)
        else:
            st.warning("Potrebno je bar 2 puta kliknuti 'Snimi' u razmaku od sat vremena.")
    else:
        st.info("Istorija je prazna. Koristi dugme u sidebar-u da počneš prikupljanje.")

# --- TAB 3: DOSTAVA HEATMAP (Korisnička perspektiva) ---
with tab3:
    st.title("🔥 Mapa kašnjenja i gužve")
    st.write("Što je zona **CRVENIJA**, to kupci u tom delu grada duže čekaju na hranu.")
    
    df_h = fetch_wolt_data(st.session_state.lat, st.session_state.lon, CITIES[grad_naziv]["slug"])
    
    if not df_h.empty:
        # Filtriramo samo otvorene restorane jer oni utiču na trenutnu dostavu
        df_open_only = df_h[df_h['Online'] == True]
        
        m_h = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=14)
        
        # LOGIKA: Težina je ETA (vreme dostave). 
        # Ako je ETA 45+, to je 'vruća' tačka.
        heat_data = [[r['Lat'], r['Lon'], r['ETA']] for _, r in df_open_only.iterrows()]
        
        HeatMap(heat_data, radius=30, blur=20, min_opacity=0.4).add_to(m_h)
        st_folium(m_h, width="100%", height=600, key="tab3_map")
        
        st.markdown("""
        - 🔴 **Vrele tačke:** Restorani u ovoj zoni imaju dugačko vreme dostave (preopterećeni kuriri ili spora kuhinja).
        - 🔵 **Hladne tačke:** Hrana stiže brzo, mala je gužva.
        """)
