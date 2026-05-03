import streamlit as st
from curl_cffi import requests
import pandas as pd
import folium
from folium.plugins import HeatMap
from streamlit_folium import st_folium, folium_static 
from geopy.geocoders import Nominatim
from streamlit_autorefresh import st_autorefresh
import numpy as np
import datetime
import os

# --- 1. KONFIGURACIJA ---
st.set_page_config(page_title="Wolt Intelligence v24.2", layout="wide", page_icon="🕵️")

CITIES = {
    "Niš": {"coords": (43.3209, 21.8958), "slug": "nis"},
    "Beograd": {"coords": (44.7866, 20.4489), "slug": "beograd"},
    "Novi Sad": {"coords": (45.2671, 19.8335), "slug": "novi-sad"},
    "Kragujevac": {"coords": (44.0128, 20.9114), "slug": "kragujevac"}
}

DB_FILE = "radar_history.csv"

# --- 2. FUNKCIJA ZA PODATKE (Poboljšana ekstrakcija tagova) ---
@st.cache_data(ttl=60)
def fetch_wolt_data(lat, lon, city_slug):
    url = "https://restaurant-api.wolt.com/v1/pages/restaurants"
    try:
        r = requests.get(url, params={"lat": lat, "lon": lon}, impersonate="chrome120", timeout=15)
        if r.status_code == 200:
            restorani = []
            for section in r.json().get("sections", []):
                for item in section.get("items", []):
                    v = item.get("venue")
                    if v:
                        # Izvlačimo kategorije (npr. Pizza, Burgers...)
                        cats = v.get("categories", [])
                        kuhinje_list = [c.get("name") for c in cats]
                        # Ako nema kategorija, probamo tagove
                        if not kuhinje_list:
                            kuhinje_list = v.get("tags", [])
                        
                        restorani.append({
                            "Ime": v.get("name"),
                            "Kuhinja": kuhinje_list,
                            "Kuhinja_Detalji": ", ".join(kuhinje_list) if kuhinje_list else "Nije navedeno",
                            "Lat": float(v.get("location", [0, 0])[1]),
                            "Lon": float(v.get("location", [0, 0])[0]),
                            "Status": "Otvoreno 🟢" if v.get("online") else "Zatvoreno 🔴",
                            "Online": v.get("online", False),
                            "Ocena": v.get("rating", {}).get("score", 0),
                            "Broj_Ocena": int(v.get("rating", {}).get("volume", 0)),
                            "Wolt Link": f"https://wolt.com/sr/srb/{city_slug}/restaurant/{v.get('slug')}"
                        })
            return pd.DataFrame(restorani).drop_duplicates(subset=['Ime'])
    except: pass
    return pd.DataFrame()

# --- 3. SESSION STATE & SIDEBAR ---
if 'lat' not in st.session_state: st.session_state.lat, st.session_state.lon = CITIES["Niš"]["coords"]
if 'current_city' not in st.session_state: st.session_state.current_city = "Niš"

grad_naziv = st.sidebar.selectbox("Izaberi grad:", list(CITIES.keys()))
if grad_naziv != st.session_state.current_city:
    st.session_state.current_city = grad_naziv
    st.session_state.lat, st.session_state.lon = CITIES[grad_naziv]["coords"]
    st.cache_data.clear()
    st.rerun()

# --- 4. GLAVNI PANEL ---
tab1, tab2, tab3, tab4 = st.tabs(["🟢 Operativni Radar", "📉 Analiza ponude", "📈 Traffic Tracker", "☁️ Service Cloud"])

df_main = fetch_wolt_data(st.session_state.lat, st.session_state.lon, CITIES[grad_naziv]["slug"])

# --- TAB 1: RADAR ---
with tab1:
    st.title(f"📍 Radar: {grad_naziv}")
    if not df_main.empty:
        m1 = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=14)
        for _, r in df_main.iterrows():
            boja = "green" if r['Online'] else "red"
            folium.CircleMarker([r['Lat'], r['Lon']], radius=7, color=boja, fill=True, tooltip=r['Ime']).add_to(m1)
        st_folium(m1, width="100%", height=500, key="map_t1")
        # DODATA KOLONA KUHINJA_DETALJI
        st.dataframe(df_main[["Ime", "Status", "Ocena", "Kuhinja_Detalji"]], use_container_width=True, hide_index=True)

# --- TAB 2: ANALIZA PONUDE (FIXED) ---
with tab2:
    st.title("🔎 Duboka analiza po vrsti kuhinje")
    if not df_main.empty:
        # Sakupljamo sve tagove iz liste listi
        flat_list = [item for sublist in df_main['Kuhinja'] for item in sublist]
        sve_kuhinje = sorted(list(set(flat_list)))
        
        izbor = st.selectbox("Izaberi vrstu hrane za filtriranje mape i tabele:", ["Sve"] + sve_kuhinje)
        
        # Filtriranje
        if izbor != "Sve":
            df_f = df_main[df_main['Kuhinja'].apply(lambda x: izbor in x)]
        else:
            df_f = df_main

        # Metrike
        c1, c2 = st.columns(2)
        c1.metric(f"Broj restorana ({izbor})", len(df_f))
        c2.metric("Prosečna Ocena", round(df_f['Ocena'].mean(), 2) if not df_f.empty else 0)

        # Mapa sa detaljnim Tooltipom
        m_f = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=14)
        for _, r in df_f.iterrows():
            folium.Marker(
                [r['Lat'], r['Lon']], 
                # Tooltip sada pokazuje i Ime i Kategorije!
                tooltip=f"🏠 {r['Ime']} | 🍴 {r['Kuhinja_Detalji']}",
                icon=folium.Icon(color="blue" if r['Online'] else "red", icon="cutlery", prefix='fa')
            ).add_to(m_f)
        
        st_folium(m_f, width="100%", height=500, key="map_t2")
        
        # FINALNA TABELA SA SVIM DETALJIMA
        st.dataframe(
            df_f[["Ime", "Kuhinja_Detalji", "Status", "Ocena", "Broj_Ocena", "Wolt Link"]], 
            use_container_width=True, 
            hide_index=True,
            column_config={"Wolt Link": st.column_config.LinkColumn("Link", display_text="Otvori 🔗")}
        )

# --- TAB 3 & 4 (Ostaju isti kao u v24.1) ---
with tab3:
    st.info("Ovde pratiš rast prodaje (Traffic Tracker).")
with tab4:
    st.info("Ovde vidiš Cloud Service mapu pokrivenosti.")
