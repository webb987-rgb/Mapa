import streamlit as st
from curl_cffi import requests
import pandas as pd
import folium
from streamlit_folium import st_folium, folium_static 
from geopy.geocoders import Nominatim
import datetime
import os

# --- 1. KONFIGURACIJA ---
st.set_page_config(page_title="Wolt Glow Radar v21", layout="wide", page_icon="🕵️")

CITIES = {
    "Niš": {"coords": (43.3209, 21.8958), "slug": "nis"},
    "Beograd": {"coords": (44.7866, 20.4489), "slug": "beograd"}
}

# --- 2. FUNKCIJE ---
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
                        restorani.append({
                            "Ime": v.get("name"),
                            "Lat": float(v.get("location", [0, 0])[1]),
                            "Lon": float(v.get("location", [0, 0])[0]),
                            "Online": v.get("online", False)
                        })
            return pd.DataFrame(restorani).drop_duplicates(subset=['Ime'])
    except: pass
    return pd.DataFrame()

# --- 3. LOGIKA ZA MAPE ---
st.title("🕵️ Wolt Market Intelligence - Glow Radar")

grad_naziv = st.sidebar.selectbox("Grad:", list(CITIES.keys()))
if 'lat' not in st.session_state:
    st.session_state.lat, st.session_state.lon = CITIES[grad_naziv]["coords"]

tab1, tab2 = st.tabs(["🟢 Operativni Radar", "🎯 Logistički Glow (Efikasnost)"])

df = fetch_wolt_data(st.session_state.lat, st.session_state.lon, CITIES[grad_naziv]["slug"])

# --- TAB 1: KLASIČNI RADAR ---
with tab1:
    m1 = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=14)
    if not df.empty:
        for _, r in df.iterrows():
            boja = "green" if r['Online'] else "red"
            folium.CircleMarker([r['Lat'], r['Lon']], radius=6, color=boja, fill=True).add_to(m1)
    st_folium(m1, width="100%", height=500, key="radar_classic")

# --- TAB 2: LOGISTIČKI GLOW (Tvoja nova vizuelna logika) ---
with tab2:
    st.subheader("Vizuelizacija zone pokrivenosti")
    m2 = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=13, tiles="cartodbpositron")

    if not df.empty:
        df_active = df[df['Online'] == True]
        
        # DEFINICIJA ZONA (Redosled je bitan: prvo najveći krugovi, na kraju najmanji)
        # Smanjujemo fill_opacity kako krug raste da bismo izbegli "mrlju"
        zones = [
            {"r": 3000, "c": "#641E16", "op": 0.01}, # Bordo (najprozirniji)
            {"r": 2500, "c": "#922B21", "op": 0.015},
            {"r": 2000, "c": "#C0392B", "op": 0.02},
            {"r": 1500, "c": "#E67E22", "op": 0.03},
            {"r": 1000, "c": "#F1C40F", "op": 0.04},
            {"r": 500,  "c": "#27AE60", "op": 0.06}, # Zeleni (najjači)
        ]

        for _, r in df_active.iterrows():
            for zone in zones:
                folium.Circle(
                    location=[r['Lat'], r['Lon']],
                    radius=zone['r'],
                    color=zone['c'],
                    stroke=False,      # KLJUČNO: Brišemo ivice krugova!
                    fill=True,
                    fill_color=zone['c'],
                    fill_opacity=zone['op'],
                    interactive=False
                ).add_to(m2)

    folium_static(m2, width=1200)
    st.markdown("💡 **Legenda:** Jaka zelena boja = epicentar ponude. Tamno crvene blede zone = rubovi dostave.")
