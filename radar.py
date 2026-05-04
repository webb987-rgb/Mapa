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
st.set_page_config(page_title="Wolt BI Radar v25.7", layout="wide", page_icon="🛵")

CITIES = {
    "Niš": {"coords": (43.3209, 21.8958), "slug": "nis"},
    "Beograd": {"coords": (44.7866, 20.4489), "slug": "beograd"},
    "Novi Sad": {"coords": (45.2671, 19.8335), "slug": "novi-sad"}
}

DB_FILE = "radar_history.csv"

# --- 2. POMOĆNE FUNKCIJE ---
def save_snapshot(df):
    """Snima trenutno stanje u CSV datoteku"""
    if not df.empty:
        df_save = df.copy().drop(columns=['Kuhinja_Raw'], errors='ignore')
        df_save['timestamp'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        # Koristimo QUOTE_ALL da spriječimo probleme sa zarezima u imenima
        df_save.to_csv(DB_FILE, mode='a', header=not os.path.exists(DB_FILE), index=False, quoting=csv.QUOTE_ALL)
        return True
    return False

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
                        delivery_specs = v.get("delivery_specs", {})
                        is_delivery_enabled = delivery_specs.get("delivery_enabled", False)
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

# --- 3. SIDEBAR ---
st.sidebar.title("🛵 Radar Kontrola")
grad_naziv = st.sidebar.selectbox("Grad:", list(CITIES.keys()))
filter_status = st.sidebar.radio("Filter:", ["Sve", "Samo Dostupna Dostava 🟢", "Zatvoreni/Nema Dostave 🔴"])

# --- 4. PODACI ---
df_raw = fetch_wolt_data(CITIES[grad_naziv]["coords"][0], CITIES[grad_naziv]["coords"][1], CITIES[grad_naziv]["slug"])
df_main = df_raw.copy()
if not df_raw.empty:
    if filter_status == "Samo Dostupna Dostava 🟢":
        df_main = df_raw[df_raw['Online'] == True]
    elif filter_status == "Zatvoreni/Nema Dostave 🔴":
        df_main = df_raw[df_raw['Online'] == False]

# --- 5. TABOVI ---
tab1, tab2, tab3, tab4 = st.tabs(["📍 Mapa Dostave", "📉 Analiza Ponude", "📈 Traffic Tracker", "☁️ Service Cloud"])

with tab1:
    st.subheader(f"📍 Radar: {grad_naziv}")
    if not df_main.empty:
        m1 = folium.Map(location=CITIES[grad_naziv]["coords"], zoom_start=14)
        for _, r in df_main.iterrows():
            boja = "green" if r['Online'] else "red"
            folium.CircleMarker([r['Lat'], r['Lon']], radius=7, color=boja, fill=True, tooltip=r['Ime']).add_to(m1)
        st_folium(m1, width="100%", height=500, key="map_v25_7")
        
        st.dataframe(
            df_main[["Wolt_Link", "Status", "Ocena", "Kuhinja_Detalji"]],
            use_container_width=True, hide_index=True,
            column_config={"Wolt_Link": st.column_config.LinkColumn("Restoran (Wolt Link)")}
        )

with tab2:
    st.subheader("🔎 Analiza i Snimanje Podataka")
    col_btn, col_info = st.columns([1, 3])
    
    with col_btn:
        if st.button("💾 SNIMI TRENUTNO STANJE", use_container_width=True):
            if save_snapshot(df_raw):
                st.success("Podaci uspješno snimljeni!")
            else:
                st.error("Greška pri snimanju.")
    
    with col_info:
        st.info("Klikni na dugme lijevo da postaviš 'nultu tačku' ili snimiš trenutni broj ocena za Traffic Tracker.")

    if not df_main.empty:
        all_cats = sorted(list(set([it for sub in df_main['Kuhinja_Raw'] for it in sub])))
        izbor = st.selectbox("Filtriraj po kuhinji:", ["Sve"] + all_cats)
        df_f = df_main[df_main['Kuhinja_Raw'].apply(lambda x: izbor in x)] if izbor != "Sve" else df_main
        
        st.write(f"Prikazujem **{len(df_f)}** restorana:")
        st.dataframe(
            df_f[["Wolt_Link", "Broj_Ocena", "Status", "Ocena"]],
            use_container_width=True, hide_index=True,
            column_config={"Wolt_Link": st.column_config.LinkColumn("Restoran")}
        )

with tab3:
    st.subheader("📈 Traffic Tracker (Rast prodaje)")
    if os.path.exists(DB_FILE):
        h = pd.read_csv(DB_FILE, on_bad_lines='skip')
        h['timestamp'] = pd.to_datetime(h['timestamp'], errors='coerce')
        h = h.dropna(subset=['timestamp'])
        ts = sorted(h['timestamp'].unique())
        
        if len(ts) >= 2:
            t_now, t_pre = ts[-1], ts[-2]
            df_now = h[h['timestamp'] == t_now].copy()
            df_pre = h[h['timestamp'] == t_pre].copy()
            
            # Osiguravamo brojeve
            df_now['Broj_Ocena'] = pd.to_numeric(df_now['Broj_Ocena'], errors='coerce').fillna(0)
            df_pre['Broj_Ocena'] = pd.to_numeric(df_pre['Broj_Ocena'], errors='coerce').fillna(0)
            
            m = pd.merge(df_now, df_pre, on="Ime", suffixes=('_sad', '_pre'))
            m['Nove_Ocene'] = m['Broj_Ocena_sad'] - m['Broj_Ocena_pre']
            m['Procjena_Porudžbina'] = m['Nove_Ocene'] * 10
            
            st.write(f"📊 Poređenje: **{t_pre.strftime('%H:%M')}** vs **{t_now.strftime('%H:%M')}**")
            
            res = m[m['Nove_Ocene'] > 0].sort_values(by='Nove_Ocene', ascending=False)
            if not res.empty:
                st.dataframe(res[["Ime", "Nove_Ocene", "Procjena_Porudžbina"]], use_container_width=True, hide_index=True)
            else:
                st.warning("Nema promjena u broju ocena između posljednja dva snimanja.")
        else:
            st.info("U bazi postoji samo jedan snimak. Klikni na 'Snimi' u tabu Analiza da dobiješ poređenje.")
    else:
        st.warning("Baza podataka je prazna. Idi na tab 'Analiza Ponude' i klikni na snimanje.")

with tab4:
    st.subheader("☁️ Service Cloud")
    m3 = folium.Map(location=CITIES[grad_naziv]["coords"], zoom_start=13, tiles="cartodbpositron")
    df_active = df_main[df_main['Online'] == True]
    if not df_active.empty:
        pts = [[r['Lat'], r['Lon'], 1.0] for _, r in df_active.iterrows()]
        HeatMap(pts, radius=45, blur=30, gradient={0.2: 'blue', 0.5: 'cyan', 1.0: 'green'}).add_to(m3)
    folium_static(m3, width=1400, height=800)
