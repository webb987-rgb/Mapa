import streamlit as st

# PRAVILO BROJ 1: Ovo mora biti PRVA stvar u kodu!
st.set_page_config(page_title="Radar v14.1", layout="wide")

try:
    from curl_cffi import requests
    import pandas as pd
    import folium
    from streamlit_folium import st_folium
    from geopy.geocoders import Nominatim
    from streamlit_autorefresh import st_autorefresh
    import datetime
except Exception as e:
    st.error(f"❌ Problem sa instalacijom biblioteka: {e}")
    st.stop()

# --- KONFIGURACIJA ---
CITIES = {
    "Niš": {"coords": (43.3209, 21.8958), "w_slug": "nis"},
    "Beograd": {"coords": (44.7866, 20.4489), "w_slug": "beograd"},
    "Novi Sad": {"coords": (45.2671, 19.8335), "w_slug": "novi-sad"}
}

# Sigurna inicijalizacija session state-a
if 'lat' not in st.session_state:
    st.session_state.lat, st.session_state.lon = CITIES["Niš"]["coords"]
if 'current_city' not in st.session_state:
    st.session_state.current_city = "Niš"

# --- SKREPERI (Sada vraćaju isključivo listu) ---
def fetch_wolt(lat, lon, city_slug):
    url = "https://restaurant-api.wolt.com/v1/pages/restaurants"
    res = []
    try:
        r = requests.get(url, params={"lat": lat, "lon": lon}, impersonate="chrome120", timeout=10)
        if r.status_code == 200:
            data = r.json()
            for sec in data.get("sections", []):
                for item in sec.get("items", []):
                    v = item.get("venue")
                    if v:
                        res.append({
                            "Ime": v.get("name"),
                            "Platforma": "Wolt",
                            "Status": "Otvoreno 🟢" if v.get("online") else "Zatvoreno 🔴",
                            "Online": v.get("online", False),
                            "Link": f"https://wolt.com/sr/srb/{city_slug}/restaurant/{v.get('slug')}",
                            "Lat": v.get("location", [0, 0])[1],
                            "Lon": v.get("location", [0, 0])[0]
                        })
    except: pass
    return res

def fetch_mister_d(lat, lon):
    url = "https://api.misterd.rs/api/v2/consumer/order" 
    res = []
    try:
        headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://misterd.rs/"}
        r = requests.get(url, params={"lat": lat, "lng": lon, "onlyActive": "true"}, headers=headers, impersonate="chrome120", timeout=10)
        if r.status_code == 200:
            venues = r.json().get("data", {}).get("venues", [])
            for v in venues:
                res.append({
                    "Ime": v.get("name"),
                    "Platforma": "Mister D",
                    "Status": "Otvoreno 🟢" if v.get("is_open") else "Zatvoreno 🔴",
                    "Online": v.get("is_open", False),
                    "Link": f"https://misterd.rs/restoran/{v.get('slug')}",
                    "Lat": float(v.get("latitude", 0)),
                    "Lon": float(v.get("longitude", 0))
                })
    except: pass
    return res

# --- SIDEBAR ---
st.sidebar.title("📡 Kontrola Radara")
grad = st.sidebar.selectbox("Grad:", list(CITIES.keys()))

if grad != st.session_state.current_city:
    st.session_state.current_city = grad
    st.session_state.lat, st.session_state.lon = CITIES[grad]["coords"]
    st.rerun()

platforma = st.sidebar.radio("Prikaži:", ["Sve", "Wolt", "Mister D"])

# --- GLAVNA LOGIKA ---
st.title(f"📍 Radar: {grad}")

with st.spinner("Skeniram platforme..."):
    all_data = []
    if platforma in ["Sve", "Wolt"]:
        all_data.extend(fetch_wolt(st.session_state.lat, st.session_state.lon, CITIES[grad]["w_slug"]))
    if platforma in ["Sve", "Mister D"]:
        all_data.extend(fetch_mister_d(st.session_state.lat, st.session_state.lon))

df = pd.DataFrame(all_data)

if not df.empty:
    df = df.drop_duplicates(subset=['Ime'])
    
    # Metrike
    c1, c2, c3 = st.columns(3)
    c1.metric("Ukupno", len(df))
    c2.metric("Otvoreno", len(df[df['Online'] == True]))
    c3.metric("Zatvoreno", len(df[df['Online'] == False]))

    # MAPA
    m = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=14)
    folium.Marker([st.session_state.lat, st.session_state.lon], icon=folium.Icon(color='red', icon='home')).add_to(m)

    for _, r in df.iterrows():
        boja = 'blue' if r['Platforma'] == 'Wolt' else 'orange'
        folium.CircleMarker(
            location=[r['Lat'], r['Lon']],
            radius=8, color=boja, fill=True, fill_opacity=0.7,
            tooltip=f"{r['Ime']} ({r['Platforma']})"
        ).add_to(m)

    # Iscrtavanje mape
    map_data = st_folium(m, width="100%", height=500, returned_objects=["last_clicked"])
    
    # Klik na mapu
    if map_data and map_data.get("last_clicked"):
        st.session_state.lat = map_data["last_clicked"]["lat"]
        st.session_state.lon = map_data["last_clicked"]["lng"]
        st.rerun()

    # Tabela
    st.dataframe(df[["Ime", "Platforma", "Status", "Link"]], use_container_width=True, hide_index=True,
                 column_config={"Link": st.column_config.LinkColumn("Link", display_text="Otvori 🔗")})
else:
    st.warning("⚠️ Nema podataka. Proveri internet ili probaj drugi grad.")
