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
st.set_page_config(page_title="Wolt Delivery Radar v25.5", layout="wide", page_icon="🛵")

CITIES = {
    "Niš": {"coords": (43.3209, 21.8958), "slug": "nis"},
    "Beograd": {"coords": (44.7866, 20.4489), "slug": "beograd"},
    "Novi Sad": {"coords": (45.2671, 19.8335), "slug": "novi-sad"}
}

DB_FILE = "radar_history.csv"

# --- 2. SMOOTH TAJMER (JavaScript) ---
def countdown_timer(minutes):
    seconds = minutes * 60
    html_code = f"""
    <div id="timer-container" style="padding:15px; border-radius:10px; background-color:#f8f9fa; text-align:center; border: 1px solid #e9ecef; margin-bottom: 20px;">
        <p style="margin:0; font-size:0.85rem; color:#6c757d; font-family:sans-serif; text-transform: uppercase; letter-spacing: 1px;">Sledeće osvežavanje</p>
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

# --- 3. SKREPER (Samo Dostava Logika) ---
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
                        # LOGIKA: Proveravamo da li je DOSTAVA omogućena i da li je restoran Online
                        # delivery_specs.delivery_enabled nam govori da li taj restoran uopšte radi dostavu preko Wolta
                        delivery_specs = v.get("delivery_specs", {})
                        is_delivery_enabled = delivery_specs.get("delivery_enabled", False)
                        
                        # Restoran je za nas "Otvoren" samo ako radi dostavu TRENUTNO
                        is_open_for_delivery = v.get("online", False) and is_delivery_enabled
                        
                        cats = v.get("categories", [])
                        kuhinje = [c.get("name") for c in cats]
                        
                        restorani.append({
                            "Ime": v.get("name"),
                            "Wolt Link": f"https://wolt.com/sr/srb/{city_slug}/restaurant/{v.get('slug')}",
                            "Kuhinja_Raw": kuhinje,
                            "Kuhinja_Detalji": ", ".join(kuhinje) if kuhinje else "Ostalo",
                            "Lat": float(v.get("location", [0, 0])[1]),
                            "Lon": float(v.get("location", [0, 0])[0]),
                            "Online": is_delivery_open := is_open_for_delivery,
                            "Status": "Dostava aktivna 🟢" if is_delivery_open else "Nema dostave 🔴",
                            "Ocena": v.get("rating", {}).get("score", 0),
                            "Broj_Ocena": int(v.get("rating", {}).get("volume", 0))
                        })
            if restorani:
                return pd.DataFrame(restorani).drop_duplicates(subset=['Ime'])
    except: pass
    return pd.DataFrame(columns=["Ime", "Wolt Link", "Online", "Status", "Lat", "Lon", "Ocena", "Broj_Ocena", "Kuhinja_Raw"])

# --- 4. SIDEBAR ---
st.sidebar.title("🛵 Delivery Radar")
grad_naziv = st.sidebar.selectbox("Grad:", list(CITIES.keys()))
filter_status = st.sidebar.radio("Filter:", ["Sve", "Samo Dostupna Dostava 🟢", "Zatvoreni/Nema Dostave 🔴"])

st.sidebar.markdown("---")
refresh_min = st.sidebar.number_input("Refresh interval (min):", 1, 60, 5)
run_timer = st.sidebar.toggle("▶️ Aktiviraj Tajmer", value=True)

if run_timer:
    countdown_timer(refresh_min)
    st_autorefresh(interval=refresh_min * 60000, key="delivery_refresh")

# --- 5. LOGIKA PODATAKA ---
df_raw = fetch_wolt_data(CITIES[grad_naziv]["coords"][0], CITIES[grad_naziv]["coords"][1], CITIES[grad_naziv]["slug"])

df_main = df_raw.copy()
if not df_raw.empty:
    if filter_status == "Samo Dostupna Dostava 🟢":
        df_main = df_raw[df_raw['Online'] == True]
    elif filter_status == "Zatvoreni/Nema Dostave 🔴":
        df_main = df_raw[df_raw['Online'] == False]

# --- 6. TABOVI ---
tab1, tab2, tab3 = st.tabs(["📍 Mapa Dostave", "📉 Analiza Kuhinja", "☁️ Service Cloud"])

with tab1:
    st.subheader(f"🛵 Pregled dostave: {grad_naziv}")
    if df_main.empty:
        st.warning("Nema restorana koji ispunjavaju uslov.")
    else:
        # MAPA
        m1 = folium.Map(location=CITIES[grad_naziv]["coords"], zoom_start=14)
        for _, r in df_main.iterrows():
            boja = "green" if r['Online'] else "red"
            folium.CircleMarker([r['Lat'], r['Lon']], radius=7, color=boja, fill=True, tooltip=r['Ime']).add_to(m1)
        st_folium(m1, width="100%", height=600, key="map_delivery")
        
        # TABELA SA HYPERLINKOM NA IMENU
        st.dataframe(
            df_main[["Wolt Link", "Status", "Ocena", "Kuhinja_Detalji"]],
            use_container_width=True,
            hide_index=True,
            column_config={
                "Wolt Link": st.column_config.LinkColumn(
                    "Restoran (Klikni za Wolt)",
                    help="Klikni na ime za otvaranje sajta",
                    display_text=r"https://wolt\.com/sr/srb/[^/]+/restaurant/([^/]+)" 
                    # Napomena: Iznad je regex za lepši prikaz, ali najjednostavnije je da koristimo Ime kao link
                )
            }
        )
        
        # Ako želiš da BAŠ ime bude link, Streamlit zahteva da kolona sa linkom bude vidljiva. 
        # Ovako smo stavili da kolona sa linkom bude glavna za navigaciju.

with tab2:
    if not df_main.empty:
        flat_cats = [item for sublist in df_main['Kuhinja_Raw'] for item in sublist]
        unique_cats = sorted(list(set(flat_cats)))
        izbor = st.selectbox("Vrsta hrane:", ["Sve"] + unique_cats)
        df_f = df_main[df_main['Kuhinja_Raw'].apply(lambda x: izbor in x)] if izbor != "Sve" else df_main
        st.dataframe(df_f[["Ime", "Status", "Ocena"]], use_container_width=True, hide_index=True)

with tab3:
    st.subheader("☁️ Cloud Dostave (Gde je najjača ponuda)")
    m3 = folium.Map(location=CITIES[grad_naziv]["coords"], zoom_start=13, tiles="cartodbpositron")
    df_active = df_main[df_main['Online'] == True]
    if not df_active.empty:
        pts = [[r['Lat'], r['Lon'], 1.0] for _, r in df_active.iterrows()]
        HeatMap(pts, radius=45, blur=30, gradient={0.2: 'blue', 0.5: 'cyan', 1.0: 'green'}).add_to(m3)
    folium_static(m3, width=1400, height=800)
