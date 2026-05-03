import streamlit as st
from curl_cffi import requests
import pandas as pd
import folium
from streamlit_folium import folium_static
from geopy.geocoders import Nominatim
from streamlit_autorefresh import st_autorefresh
import datetime

# --- KONFIGURACIJA STRANICE ---
st.set_page_config(page_title="Wolt Niš Radar 2026", layout="wide", page_icon="🍔")

# Default koordinate za Niš
DEFAULT_LAT, DEFAULT_LON = 43.3209, 21.8958
geolocator = Nominatim(user_agent="wolt_radar_nis_v2")

# --- FUNKCIJA ZA GEOLOKACIJU ---
def get_coords(address):
    try:
        location = geolocator.geocode(f"{address}, Niš, Serbia")
        if location:
            return location.latitude, location.longitude
    except:
        return None, None
    return None, None

# --- FUNKCIJA ZA SKUPLJANJE PODATAKA (CURL_CFFI) ---
def fetch_wolt_data(lat, lon):
    url = "https://restaurant-api.wolt.com/v1/pages/restaurants"
    params = {"lat": lat, "lon": lon}
    
    # Predefinisane kolone da Pandas nikad ne pukne (KeyError fix)
    kolone = ["Ime", "Status", "Ocena", "Adresa", "Radno Vreme", "Online", "Lat", "Lon"]
    
    try:
        # Koristimo impersonate za Chrome 120 da nas Wolt ne blokira
        r = requests.get(url, params=params, impersonate="chrome120", timeout=15)
        
        if r.status_code == 200:
            data = r.json()
            restorani = []
            
            for section in data.get("sections", []):
                for item in section.get("items", []):
                    v = item.get("venue")
                    if v:
                        # Pokušavamo da izvučemo radno vreme ili procenjeno vreme dostave
                        # Wolt često drži radno vreme u 'delivery_specs' ili 'short_description'
                        radno_vreme = v.get("short_description", "Pogledaj u aplikaciji")
                        if not radno_vreme:
                            radno_vreme = "Radno vreme nije dostupno"
                        
                        restorani.append({
                            "Ime": v.get("name", "Nepoznato"),
                            "Adresa": v.get("address", "Nema adrese"),
                            "Lat": v.get("location", [0, 0])[1],
                            "Lon": v.get("location", [0, 0])[0],
                            "Status": "Otvoreno 🟢" if v.get("online") else "Zatvoreno 🔴",
                            "Online": v.get("online", False),
                            "Ocena": v.get("rating", {}).get("score", "-"),
                            "Radno Vreme": radno_vreme
                        })
            
            if not restorani:
                return pd.DataFrame(columns=kolone)
            
            return pd.DataFrame(restorani).drop_duplicates(subset=['Ime'])
            
    except Exception as e:
        st.error(f"Greška pri konekciji sa API-jem: {e}")
    
    return pd.DataFrame(columns=kolone)

# --- SIDEBAR: KONTROLE ---
st.sidebar.title("🛠️ Kontrolna Tabla")

# 1. Autorefresh tajmer
refresh_min = st.sidebar.number_input("Osvežavanje (minuta):", min_value=1, max_value=60, value=5)
st_autorefresh(interval=refresh_min * 60000, key="wolt_refresher")

st.sidebar.markdown("---")

# 2. Promena lokacije
address_input = st.sidebar.text_input("📍 Proveri drugu adresu (Niš):", placeholder="npr. Bulevar Nemanjića")

if address_input:
    target_lat, target_lon = get_coords(address_input)
    if not target_lat:
        st.sidebar.error("Adresa nije nađena, koristim centar Niša.")
        target_lat, target_lon = DEFAULT_LAT, DEFAULT_LON
else:
    target_lat, target_lon = DEFAULT_LAT, DEFAULT_LON

# --- GLAVNI EKRAN ---
st.title("🍔 Wolt Radar Niš - Uživo")
st.caption(f"Poslednji sken urađen u: **{datetime.datetime.now().strftime('%H:%M:%S')}**")

# Povlačenje podataka
df = fetch_wolt_data(target_lat, target_lon)

# --- PRIKAZ PODATAKA ---
if not df.empty:
    # 1. Statistika na vrhu
    s1, s2, s3 = st.columns(3)
    s1.metric("Ukupno restorana", len(df))
    s2.metric("Otvoreno", len(df[df['Online'] == True]))
    s3.metric("Zatvoreno", len(df[df['Online'] == False]))

    # 2. Mapa sa tooltipovima (Hover radno vreme)
    st.markdown("### 🗺️ Interaktivna mapa")
    m = folium.Map(location=[target_lat, target_lon], zoom_start=15, tiles="cartodbpositron")
    
    # Marker za tvoju lokaciju
    folium.Marker(
        [target_lat, target_lon],
        icon=folium.Icon(color="blue", icon="home"),
        popup="Tvoja lokacija pretrage"
    ).add_to(m)

    for _, r in df.iterrows():
        if r['Lat'] == 0: continue
        
        boja = "green" if r['Online'] else "red"
        
        # Sklapanje teksta za TOOLTIP (prikazuje se na HOVER - kad staviš miša)
        tooltip_html = f"""
        <div style="font-family: Arial; font-size: 13px;">
            <b>{r['Ime']}</b><br>
            Status: {r['Status']}<br>
            Radno vreme/Opis: {r['Radno Vreme']}<br>
            ⭐ Ocena: {r['Ocena']}
        </div>
        """
        
        folium.CircleMarker(
            location=[r['Lat'], r['Lon']],
            radius=9,
            color=boja,
            fill=True,
            fill_color=boja,
            fill_opacity=0.7,
            tooltip=folium.Tooltip(tooltip_html), # Ovo je deo za hover
            popup=f"<b>{r['Ime']}</b><br>{r['Adresa']}"
        ).add_to(m)

    folium_static(m, width=1200, height=500)

    # 3. Tabela ispod mape
    st.markdown("### 📋 Spisak svih restorana")
    # Sortiramo da otvoreni uvek budu prvi
    df_sorted = df[["Ime", "Status", "Radno Vreme", "Ocena", "Adresa"]].sort_values(by="Status", ascending=False)
    st.dataframe(df_sorted, use_container_width=True, hide_index=True)

else:
    st.warning("Trenutno nema podataka. Pokušaj da promeniš adresu ili osvežiš stranicu.")

# Footer
st.markdown("---")
st.markdown("🚀 *Sveti Gral Radar v3.1*")
