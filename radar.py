import streamlit as st
from curl_cffi import requests
import pandas as pd
import folium
from folium.plugins import HeatMap
from streamlit_folium import st_folium, folium_static 
import numpy as np

# --- 1. KONFIGURACIJA ---
st.set_page_config(page_title="Wolt Cloud Radar v22", layout="wide", page_icon="☁️")

# Gradovi
CITIES = {
    "Niš": (43.3209, 21.8958),
    "Beograd": (44.7866, 20.4489)
}

@st.cache_data(ttl=60)
def fetch_wolt_data(lat, lon):
    url = "https://restaurant-api.wolt.com/v1/pages/restaurants"
    try:
        r = requests.get(url, params={"lat": lat, "lon": lon}, impersonate="chrome120", timeout=15)
        if r.status_code == 200:
            res = []
            for section in r.json().get("sections", []):
                for item in section.get("items", []):
                    v = item.get("venue")
                    if v and v.get("online"):
                        res.append([v.get("location")[1], v.get("location")[0]])
            return res
    except: return []

st.title("☁️ Wolt Service Cloud - Analiza pokrivenosti")

grad = st.sidebar.selectbox("Izaberi grad:", list(CITIES.keys()))
center = CITIES[grad]

# POVLAČENJE PODATAKA
restorani_koordinate = fetch_wolt_data(center[0], center[1])

if restorani_koordinate:
    # --- MOZAK OPERACIJE: GENERISANJE "OBLAKA" ---
    # Za svaki restoran pravimo sistem tačaka koji simulira tvoje krugove
    heat_points = []
    
    for lat, lon in restorani_koordinate:
        # 1. Centar (Zelena zona - najjači intenzitet)
        heat_points.append([lat, lon, 1.0])
        
        # 2. Simuliramo širenje (dodajemo virtuelne tačke oko restorana)
        # Ovo pravi "mekan" prelaz umesto oštrih krugova koji prave haos
        for angle in range(0, 360, 45): # Na svakih 45 stepeni
            rad = np.radians(angle)
            # Tačke na 800m (Žuta zona)
            heat_points.append([lat + 0.007 * np.cos(rad), lon + 0.009 * np.sin(rad), 0.6])
            # Tačke na 2km (Crvena zona - najslabiji intenzitet)
            heat_points.append([lat + 0.018 * np.cos(rad), lon + 0.022 * np.sin(rad), 0.2])

    # KREIRANJE MAPE
    # Koristimo "CartoDB Positron" jer je bela i čista podloga
    m = folium.Map(location=center, zoom_start=13, tiles="cartodbpositron")

    # CUSTOM GRADIENT: Tvoja logika boja
    # 0.2 (daleko) = Crveno, 0.5 (srednje) = Žuto/Narandžasto, 1.0 (blizu) = Zeleno
    gradient_config = {
        0.2: 'red',
        0.4: 'orange',
        0.6: 'yellow',
        1.0: 'green'
    }

    HeatMap(
        heat_points, 
        radius=40, 
        blur=25, 
        gradient=gradient_config,
        min_opacity=0.2
    ).add_to(m)

    # Dodajemo male tačkice gde su zapravo restorani da se lakše snađeš
    for lat, lon in restorani_koordinate:
        folium.CircleMarker([lat, lon], radius=2, color='black', fill=True, opacity=0.3).add_to(m)

    folium_static(m, width=1200)

    st.markdown("""
    ### 📖 Kako čitati ovu mapu:
    - **Jaka Zelena:** Ovde si "kralj". Imaš gomilu restorana koji su ti pod nosom.
    - **Žuta/Narandžasta:** Dobra pokrivenost, ali restorani su na 1-1.5km.
    - **Crvena/Bleda:** Rubne zone. Ovde hrana putuje najduže i izbor je najslabiji.
    - **Belo:** Pustinja. Srećno sa poručivanjem.
    """)
else:
    st.error("Nema otvorenih restorana ili je API blokiran.")
