import streamlit as st
from curl_cffi import requests
import pandas as pd
import folium
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim
from streamlit_autorefresh import st_autorefresh
import datetime

# --- KONFIGURACIJA ---
st.set_page_config(page_title="Wolt Market Radar PRO", layout="wide", page_icon="🕵️")

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

geolocator = Nominatim(user_agent="wolt_market_spy_v5")

# Inicijalizacija session state-a za tajmer
if 'timer_active' not in st.session_state:
    st.session_state.timer_active = False

# --- FUNKCIJE ---

def fetch_wolt_data(lat, lon):
    url = "https://restaurant-api.wolt.com/v1/pages/restaurants"
    params = {"lat": lat, "lon": lon}
    kolone = ["Ime", "Status", "Radno Vreme", "Ocena", "Adresa", "Online", "Lat", "Lon"]
    
    try:
        r = requests.get(url, params=params, impersonate="chrome120", timeout=15)
        if r.status_code == 200:
            data = r.json()
            restorani = []
            for section in data.get("sections", []):
                for item in section.get("items", []):
                    v = item.get("venue")
                    if v:
                        # EKSTRAKCIJA RADNOG VREMENA
                        # Wolt nekad šalje status tipa "Zatvara se u 23:00" u polju 'status_next_change'
                        status_text = v.get("short_description", "")
                        
                        restorani.append({
                            "Ime": v.get("name", "Nepoznato"),
                            "Adresa": v.get("address", "Nema adrese"),
                            "Lat": v.get("location", [0, 0])[1],
                            "Lon": v.get("location", [0, 0])[0],
                            "Status": "Otvoreno 🟢" if v.get("online") else "Zatvoreno 🔴",
                            "Online": v.get("online", False),
                            "Ocena": v.get("rating", {}).get("score", "-"),
                            "Radno Vreme": status_text if status_text else "Info u aplikaciji"
                        })
            # Brisanje duplikata i sortiranje (Otvoreni prvo)
            df = pd.DataFrame(restorani).drop_duplicates(subset=['Ime'])
            return df.sort_values(by="Online", ascending=False)
    except:
        pass
    return pd.DataFrame(columns=kolone)

# --- SIDEBAR ---
st.sidebar.title("🛠️ Kontrola Radara")

# 1. Grad i Adresa
selected_city = st.sidebar.selectbox("1. Izaberi grad:", list(CITIES.keys()))
base_lat, base_lon = CITIES[selected_city]

address_input = st.sidebar.text_input("2. Unesi specifičnu adresu (opciono):", placeholder="npr. Bulevar Nemanjića 15")

target_lat, target_lon = base_lat, base_lon
if address_input:
    try:
        location = geolocator.geocode(f"{address_input}, {selected_city}, Serbia")
        if location:
            target_lat, target_lon = location.latitude, location.longitude
            st.sidebar.success("Adresa locirana!")
    except:
        st.sidebar.warning("Adresa nije pronađena, koristim centar.")

# 2. Filteri
st.sidebar.markdown("---")
st.sidebar.subheader("3. Filteri prikaza")
filter_open = st.sidebar.checkbox("Samo OTVORENI", value=False)
filter_closed = st.sidebar.checkbox("Samo ZATVORENI", value=False)

# 3. Tajmer i Start
st.sidebar.markdown("---")
st.sidebar.subheader("4. Automatizacija")
refresh_min = st.sidebar.number_input("Interval (min):", 1, 60, 5)

if st.sidebar.button("▶️ START REFRESH"):
    st.session_state.timer_active = True

if st.sidebar.button("⏹️ STOP"):
    st.session_state.timer_active = False

if st.session_state.timer_active:
    st_autorefresh(interval=refresh_min * 60000, key="auto_refresh_node")
    st.sidebar.info(f"🔄 Automatsko osvežavanje aktivno ({refresh_min} min)")

# --- GLAVNI PANEL ---
st.title(f"📍 Market Radar: {selected_city}")
if address_input:
    st.write(f"Lokacija: **{address_input}**")

# Povlačenje podataka
df = fetch_wolt_data(target_lat, target_lon)

# Primena filtera
if filter_open and not filter_closed:
    df = df[df['Online'] == True]
elif filter_closed and not filter_open:
    df = df[df['Online'] == False]
elif filter_open and filter_closed:
    st.warning("Izabrali ste oba filtera, prikazujem sve.")

if not df.empty:
    # MAPA - Proširena
    m = folium.Map(location=[target_lat, target_lon], zoom_start=15, tiles="cartodbpositron")
    
    # Marker za adresu pretrage
    folium.Marker([target_lat, target_lon], icon=folium.Icon(color='blue', icon='home')).add_to(m)

    for _, r in df.iterrows():
        boja = "green" if r['Online'] else "red"
        
        # Popup sadržaj - čist i bez nepotrebnih informacija
        popup_html = f"""
        <div style="font-family: Arial; width: 180px;">
            <b style="font-size: 14px;">{r['Ime']}</b><br>
            <hr style="margin: 5px 0;">
            <b>Status:</b> {r['Status']}<br>
            <b>Radno vreme:</b> {r['Radno Vreme']}<br>
            <b>Ocena:</b> ⭐ {r['Ocena']}
        </div>
        """
        
        folium.CircleMarker(
            location=[r['Lat'], r['Lon']],
            radius=10,
            color=boja,
            fill=True,
            fill_color=boja,
            fill_opacity=0.7,
            tooltip=r['Ime'], # Hover samo ime
            popup=folium.Popup(popup_html, max_width=250)
        ).add_to(m)

    st_folium(m, width=1800, height=600, use_container_width=True)

    # TABELA - Sortirana: Otvoreni pa Zatvoreni
    st.markdown("### 📋 Uporedni prikaz restorana")
    st.dataframe(
        df[["Ime", "Status", "Radno Vreme", "Ocena", "Adresa"]],
        use_container_width=True,
        hide_index=True
    )
else:
    st.error("Nema podataka za zadate parametre.")
