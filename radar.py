import streamlit as st
from curl_cffi import requests
import pandas as pd
import folium
from streamlit_folium import folium_static
from geopy.geocoders import Nominatim
from streamlit_autorefresh import st_autorefresh
import datetime

# --- KONFIGURACIJA ---
st.set_page_config(page_title="Wolt Radar Live", layout="wide", page_icon="🍔")

# Default koordinate za Niš
DEFAULT_LAT, DEFAULT_LON = 43.3209, 21.8958

# Inicijalizacija geolokatora
geolocator = Nominatim(user_agent="wolt_radar_nis_2026")

# --- FUNKCIJE ---

def get_coords(address):
    try:
        location = geolocator.geocode(f"{address}, Niš, Serbia")
        if location:
            return location.latitude, location.longitude
    except:
        return None, None
    return None, None

def fetch_wolt_data(lat, lon):
    url = "https://restaurant-api.wolt.com/v1/pages/restaurants"
    params = {"lat": lat, "lon": lon}
    try:
        # Koristimo curl_cffi za izbegavanje blokade
        r = requests.get(url, params=params, impersonate="chrome120", timeout=15)
        if r.status_code == 200:
            data = r.json()
            restorani = []
            for section in data.get("sections", []):
                for item in section.get("items", []):
                    v = item.get("venue")
                    if v:
                        restorani.append({
                            "Ime": v.get("name"),
                            "Adresa": v.get("address"),
                            "Lat": v.get("location", [0, 0])[1],
                            "Lon": v.get("location", [0, 0])[0],
                            "Status": "Online 🟢" if v.get("online") else "Offline 🔴",
                            "Online": v.get("online", False),
                            "Ocena": v.get("rating", {}).get("score", "-")
                        })
            return pd.DataFrame(restorani).drop_duplicates(subset=['Ime'])
    except Exception as e:
        st.error(f"Greška pri preuzimanju podataka: {e}")
    return pd.DataFrame()

# --- SIDEBAR (Podešavanja) ---
st.sidebar.header("🛠️ Podešavanja")

# 1. Refresh Tajmer
refresh_interval = st.sidebar.number_input("Interval osvežavanja (minuta):", min_value=1, max_value=60, value=5)
# Aktivacija auto-refresha (množimo sa 60.000 jer su milisekunde)
st_autorefresh(interval=refresh_interval * 60000, key="datarefresh")

# 2. Pretraga adrese
st.sidebar.markdown("---")
st.sidebar.subheader("📍 Promeni lokaciju")
address_input = st.sidebar.text_input("Unesi adresu u Nišu:", placeholder="npr. Bulevar Nemanjića")

if address_input:
    target_lat, target_lon = get_coords(address_input)
    if target_lat:
        st.sidebar.success(f"Lokacija pronađena!")
    else:
        st.sidebar.error("Adresa nije pronađena, koristim centar.")
        target_lat, target_lon = DEFAULT_LAT, DEFAULT_LON
else:
    target_lat, target_lon = DEFAULT_LAT, DEFAULT_LON

# --- GLAVNI PANEL ---
st.title("🍔 Wolt Radar - Niš Uživo")
st.write(f"Poslednje ažuriranje: **{datetime.datetime.now().strftime('%H:%M:%S')}** (Osvežavanje na svakih {refresh_interval} min)")

# Preuzimanje podataka
df = fetch_wolt_data(target_lat, target_lon)

if not df.empty:
    # Statistika
    c1, c2, c3 = st.columns(3)
    c1.metric("Ukupno restorana", len(df))
    c2.metric("Trenutno Online", len(df[df['Online'] == True]))
    c3.metric("Trenutno Offline", len(df[df['Online'] == False]))

    # Mapa
    st.markdown("### 🗺️ Interaktivna Mapa")
    m = folium.Map(location=[target_lat, target_lon], zoom_start=15, tiles="cartodbpositron")
    
    # Marker za trenutnu lokaciju (centar pretrage)
    folium.Marker(
        [target_lat, target_lon], 
        popup="Moja lokacija", 
        icon=folium.Icon(color="blue", icon="home")
    ).add_to(m)

    for _, r in df.iterrows():
        boja = "green" if r['Online'] else "red"
        folium.CircleMarker(
            location=[r['Lat'], r['Lon']],
            radius=8,
            color=boja,
            fill=True,
            fill_color=boja,
            fill_opacity=0.6,
            popup=f"<b>{r['Ime']}</b><br>Status: {r['Status']}<br>Ocena: {r['Ocena']}",
            tooltip=r['Ime']
        ).add_to(m)

    folium_static(m, width=1200, height=500)

    # Tabela podataka
    st.markdown("### 📋 Detaljan Spisak")
    st.dataframe(df[["Ime", "Status", "Ocena", "Adresa"]].sort_values(by="Online", ascending=False), use_container_width=True, hide_index=True)

else:
    st.warning("Trenutno nema dostupnih podataka. Proveri internet konekciju.")

# Dugme za ručni refresh
if st.button("🔄 Osveži odmah"):
    st.rerun()