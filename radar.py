import streamlit as st
from curl_cffi import requests
import pandas as pd
import folium
from folium.plugins import HeatMap
from streamlit_folium import st_folium, folium_static 
from streamlit_autorefresh import st_autorefresh
import numpy as np
import datetime
import os
import csv
import streamlit.components.v1 as components

# --- 1. KONFIGURACIJA ---
st.set_page_config(page_title="Wolt Delivery Radar v25.6", layout="wide", page_icon="🛵")

CITIES = {
    "Niš": {"coords": (43.3209, 21.8958), "slug": "nis"},
    "Beograd": {"coords": (44.7866, 20.4489), "slug": "beograd"},
    "Novi Sad": {"coords": (45.2671, 19.8335), "slug": "novi-sad"}
}

DB_FILE = "radar_history.csv"

# --- 2. SMOOTH TAJMER (JS) ---
def countdown_timer(minutes):
    seconds = minutes * 60
    html_code = f"""
    <div id="timer-container" style="padding:15px; border-radius:10px; background-color:#f8f9fa; text-align:center; border: 1px solid #e9ecef; margin-bottom: 20px;">
        <p style="margin:0; font-size:0.85rem; color:#6c757d; font-family:sans-serif; text-transform: uppercase; letter-spacing: 1px;">Osvežavanje za:</p>
        <span id="timer" style="font-size:2rem; font-weight:bold; color:#00c2e8; font-family: 'Courier New', monospace;">--:--</span>
    </div>
    <script>
        var timeLeft = {seconds};
        var timerDisplay = document.getElementById('timer');
        function updateTimer() {{
            var mins = Math.floor(timeLeft / 60);
            var secs = timeLeft % 60;
            timerDisplay.innerHTML = (mins < 10 ? "0" : "") + mins + ":" + (secs < 10 ? "0" : "") + secs;
            if (timeLeft <= 0) {{ clearInterval(interval); }}
            timeLeft--;
        }}
        var interval = setInterval(updateTimer, 1000);
        updateTimer();
    </script>
    """
    return components.html(html_code, height=120)

# --- 3. SKREPER ---
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
                        # PROVERA DOSTAVE
                        delivery_specs = v.get("delivery_specs", {})
                        is_delivery_enabled = delivery_specs.get("delivery_enabled", False)
                        
                        # Otvoren samo ako je ONLINE i ako RADU DOSTAVU
                        is_open_for_delivery = v.get("online", False) and is_delivery_enabled
                        
                        cats = v.get("categories", [])
                        kuhinje = [c.get("name") for c in cats]
                        
                        restorani.append({
                            "Ime": v.get("name"),
                            "Wolt_Link": f"https://wolt.com/sr/srb/{city_slug}/restaurant/{v.get('slug')}",
                            "Kuhinja_Raw": kuhinje,
                            "Kuhinja_Detalji": ", ".join(kuhinje) if kuhinje else "Ostalo",
                            "Lat": float(v.get("location", [0, 0])[1]),
                            "Lon": float(v.get("location", [0, 0])[0]),
                            "Online": is_open_for_delivery,
                            "Status": "Dostava aktivna 🟢" if is_open_for_delivery else "Zatvoreno/Nema dostave 🔴",
                            "Ocena": v.get("rating", {}).get("score", 0),
                            "Broj_Ocena": int(v.get("rating", {}).get("volume", 0))
                        })
            if restorani:
                return pd.DataFrame(restorani).drop_duplicates(subset=['Ime'])
    except: pass
    return pd.DataFrame(columns=["Ime", "Wolt_Link", "Online", "Status", "Lat", "Lon", "Ocena", "Broj_Ocena", "Kuhinja_Raw", "Kuhinja_Detalji"])

# --- 4. SIDEBAR ---
st.sidebar.title("🛵 Radar")
grad_naziv = st.sidebar.selectbox("Grad:", list(CITIES.keys()))
filter_status = st.sidebar.radio("Filter:", ["Sve", "Samo Dostupna Dostava 🟢", "Zatvoreno/Nema Dostave 🔴"])

st.sidebar.markdown("---")
refresh_min = st.sidebar.number_input("Osveži na (min):", 1, 60, 5)
run_timer = st.sidebar.toggle("▶️ Tajmer", value=True)
if run_timer:
    countdown_timer(refresh_min)
    st_autorefresh(interval=refresh_min * 60000, key="refresh_v25_6")

# --- 5. PODACI ---
df_raw = fetch_wolt_data(CITIES[grad_naziv]["coords"][0], CITIES[grad_naziv]["coords"][1], CITIES[grad_naziv]["slug"])
df_main = df_raw.copy()
if not df_raw.empty:
    if filter_status == "Samo Dostupna Dostava 🟢":
        df_main = df_raw[df_raw['Online'] == True]
    elif filter_status == "Zatvoreni/Nema Dostave 🔴":
        df_main = df_raw[df_raw['Online'] == False]

# --- 6. TABOVI ---
tab1, tab2, tab3 = st.tabs(["📍 Mapa Dostave", "📉 Analiza", "☁️ Service Cloud"])

with tab1:
    if df_main.empty:
        st.warning("Nema restorana za prikaz.")
    else:
        m1 = folium.Map(location=CITIES[grad_naziv]["coords"], zoom_start=14)
        for _, r in df_main.iterrows():
            boja = "green" if r['Online'] else "red"
            folium.CircleMarker([r['Lat'], r['Lon']], radius=7, color=boja, fill=True, tooltip=r['Ime']).add_to(m1)
        st_folium(m1, width="100%", height=600, key="map_fixed")
        
        # TABELA SA LINKOVIMA
        st.dataframe(
            df_main[["Wolt_Link", "Status", "Ocena", "Kuhinja_Detalji"]],
            use_container_width=True,
            hide_index=True,
            column_config={
                "Wolt_Link": st.column_config.LinkColumn(
                    "Restoran (Klikni za Wolt)",
                    display_text=r"https://wolt\.com/sr/srb/[^/]+/restaurant/([^/]+)" # Izvlači slug za lepši prikaz
                )
            }
        )

with tab2:
    if not df_main.empty:
        # Pretraga po kuhinji
        all_cats = sorted(list(set([it for sub in df_main['Kuhinja_Raw'] for it in sub])))
        izbor = st.selectbox("Kategorija:", ["Sve"] + all_cats)
        df_f = df_main[df_main['Kuhinja_Raw'].apply(lambda x: izbor in x)] if izbor != "Sve" else df_main
        st.dataframe(df_f[["Ime", "Status", "Ocena"]], use_container_width=True, hide_index=True)

with tab3:
    m3 = folium.Map(location=CITIES[grad_naziv]["coords"], zoom_start=13, tiles="cartodbpositron")
    df_a = df_main[df_main['Online'] == True]
    if not df_a.empty:
        pts = [[r['Lat'], r['Lon'], 1.0] for _, r in df_a.iterrows()]
        HeatMap(pts, radius=45, blur=30, gradient={0.2: 'blue', 0.5: 'cyan', 1.0: 'green'}).add_to(m3)
    folium_static(m3, width=1400, height=800)
