import streamlit as st
from curl_cffi import requests
import pandas as pd
import folium
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim
from streamlit_autorefresh import st_autorefresh
import datetime

# --- KONFIGURACIJA ---
st.set_page_config(page_title="Wolt Market Radar", layout="wide", page_icon="🌐")

# Rečnik gradova sa koordinatama
CITIES = {
    "Beograd": (44.7866, 20.4489),
    "Niš": (43.3209, 21.8958),
    "Novi Sad": (45.2671, 19.8335),
    "Kragujevac": (44.0128, 20.9114),
    "Čačak": (43.8914, 20.3502),
    "Kruševac": (43.5833, 21.3267),
    "Kraljevo": (43.7258, 20.6894),
    "Novi Pazar": (43.1407, 20.5181),
    "Subotica": (46.1005, 19.6651)
}

geolocator = Nominatim(user_agent="wolt_multi_city_radar")

# --- FUNKCIJE ---

def fetch_wolt_data(lat, lon):
    url = "https://restaurant-api.wolt.com/v1/pages/restaurants"
    params = {"lat": lat, "lon": lon}
    kolone = ["Ime", "Status", "Ocena", "Adresa", "Info", "Online", "Lat", "Lon"]
    
    try:
        r = requests.get(url, params=params, impersonate="chrome120", timeout=15)
        if r.status_code == 200:
            data = r.json()
            restorani = []
            for section in data.get("sections", []):
                for item in section.get("items", []):
                    v = item.get("venue")
                    if v:
                        # Wolt API za radno vreme često zahteva poseban poziv po restoranu, 
                        # ovde uzimamo dostupne meta podatke o dostavi
                        deliv_info = v.get("delivery_specs", {}).get("delivery_times", "Info u aplikaciji")
                        
                        restorani.append({
                            "Ime": v.get("name", "Nepoznato"),
                            "Adresa": v.get("address", "Nema adrese"),
                            "Lat": v.get("location", [0, 0])[1],
                            "Lon": v.get("location", [0, 0])[0],
                            "Status": "Otvoreno 🟢" if v.get("online") else "Zatvoreno 🔴",
                            "Online": v.get("online", False),
                            "Ocena": v.get("rating", {}).get("score", "-"),
                            "Info": deliv_info
                        })
            return pd.DataFrame(restorani).drop_duplicates(subset=['Ime'])
    except:
        pass
    return pd.DataFrame(columns=kolone)

# --- SIDEBAR KONTROLE ---
st.sidebar.title("🌍 Wolt Kontrola")

# 1. Izbor Grada
selected_city = st.sidebar.selectbox("Izaberi grad:", list(CITIES.keys()))
city_lat, city_lon = CITIES[selected_city]

# 2. Filter Statusa
st.sidebar.markdown("---")
show_only_open = st.sidebar.checkbox("Prikaži samo OTVORENE", value=False)

# 3. Tajmer
refresh_min = st.sidebar.number_input("Auto-osvežavanje (min):", 1, 60, 5)
st_autorefresh(interval=refresh_min * 60000, key="global_refresh")

# --- GLAVNI DEO ---
st.title(f"🚀 Radar: {selected_city}")
st.caption(f"Osveženo: {datetime.datetime.now().strftime('%H:%M:%S')}")

# Povlačenje podataka
df = fetch_wolt_data(city_lat, city_lon)

# Filtriranje
if show_only_open:
    df = df[df['Online'] == True]

if not df.empty:
    # Mapa preko celog ekrana (skoro)
    m = folium.Map(location=[city_lat, city_lon], zoom_start=14, tiles="cartodbpositron", control_scale=True)

    for _, r in df.iterrows():
        boja = "green" if r['Online'] else "red"
        
        # Hover - samo ime (čisto)
        tooltip = r['Ime']
        
        # Klik (Popup) - Detalji
        popup_html = f"""
        <div style="font-family: Arial; width: 200px;">
            <h4>{r['Ime']}</h4>
            <hr>
            <b>Status:</b> {r['Status']}<br>
            <b>Dostava info:</b> {r['Info']}<br>
            <b>Ocena:</b> ⭐ {r['Ocena']}<br>
            <a href="https://wolt.com/sr/search?q={r['Ime']}" target="_blank">Otvori na Woltu</a>
        </div>
        """
        
        folium.CircleMarker(
            location=[r['Lat'], r['Lon']],
            radius=10,
            color=boja,
            fill=True,
            fill_color=boja,
            fill_opacity=0.7,
            tooltip=tooltip,
            popup=folium.Popup(popup_html, max_width=250)
        ).add_to(m)

    # Prikaz mape - širina postavljena na 100% kroz use_container_width
    st_folium(m, width=1600, height=600, returned_objects=[])

    # Tabela
    st.markdown("### 📋 Tabela restorana")
    st.dataframe(
        df[["Ime", "Status", "Ocena", "Adresa"]].sort_values(by="Status", ascending=False),
        use_container_width=True,
        hide_index=True
    )
else:
    st.error("Nema podataka za izabrani grad ili filter.")
