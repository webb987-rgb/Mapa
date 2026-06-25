import streamlit as st
from curl_cffi import requests
import pandas as pd
import folium
from folium.plugins import HeatMap
from streamlit_folium import st_folium, folium_static 
from geopy.geocoders import Nominatim
from streamlit_autorefresh import st_autorefresh
import numpy as np
import datetime
import os
import csv
import pytz
import streamlit.components.v1 as components

# --- 1. CONFIGURATION & TIMEZONE ---
st.set_page_config(page_title="Wolt BI Radar PRO v28.3", layout="wide", page_icon="📡")

# Postavljanje vremenske zone
local_tz = pytz.timezone("Europe/Belgrade")

CITIES = {
    "Nis": {"coords": (43.3209, 21.8958), "slug": "nis"},
    "Belgrade": {"coords": (44.7866, 20.4489), "slug": "beograd"},
    "Novi Sad": {"coords": (45.2671, 19.8335), "slug": "novi-sad"},
    "Kragujevac": {"coords": (44.0128, 20.9114), "slug": "kragujevac"}
}

DB_FILE = "radar_history.csv"

# --- 2. SESSION STATE ---
if 'lat' not in st.session_state:
    st.session_state.lat, st.session_state.lon = CITIES["Nis"]["coords"]
if 'current_city' not in st.session_state:
    st.session_state.current_city = "Nis"
if 'timer_active' not in st.session_state:
    st.session_state.timer_active = False

# --- 3. UI COMPONENTS ---
def countdown_timer(minutes):
    seconds = minutes * 60
    html_code = f"""
    <div id="timer-container" style="padding:15px; border-radius:10px; background-color:#f8f9fa; text-align:center; border: 1px solid #e9ecef; margin-bottom: 20px;">
        <p style="margin:0; font-size:0.85rem; color:#6c757d; font-family:sans-serif; text-transform: uppercase; letter-spacing: 1px;">Next Refresh In:</p>
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

# --- 4. DATA SCRAPER (CURL-MATCHED POST REQUEST) ---
@st.cache_data(ttl=60)
def fetch_wolt_data(lat, lon, city_slug):
    cols = ["Name", "Wolt Link", "Cuisine_Raw", "Cuisine_Details", "Lat", "Lon", "Status", "Online", "Rating", "Rating_Count"]
    empty_df = pd.DataFrame(columns=cols)
    
    # Novi endpoint identifikovan iz tvog cURL-a
    url = "https://consumer-api.wolt.com/v1/pages/category/restaurants"
    
    # Autentična zaglavlja i kolačići preslikani direktno iz tvog pretraživača
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "en-US,en;q=0.9,sr-RS;q=0.8,sr;q=0.7",
        "app-currency-format": "wqQxLDIzNC41Ng==",
        "app-language": "en",
        "client-version": "1.16.109",
        "clientversionnumber": "1.16.109",
        "content-type": "application/json",
        "origin": "https://wolt.com",
        "platform": "Web",
        "priority": "u=1, i",
        "referer": "https://wolt.com/",
        "sec-ch-ua": '"Chromium";v="148", "Google Chrome";v="148", "Not/A)Brand";v="99"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
        "w-wolt-session-id": "322cf981-a30b-460e-a2ad-9e2f2367718f",
        "x-wolt-web-clientid": "6020ea5f-e8b8-428c-9dac-990e6762f56f",
        "cookie": "ravelinDeviceId=rjs-e2022c3e-07d3-4c6a-910d-973b4273ee0d; rskxRunCookie=0; rCookie=df93ypr9eeqeubs3uxtx1emfgklyxr; cwc-consents={%22analytics%22:true%2C%22functional%22:true%2C%22interaction%22:{%22bundle%22:%22allow%22}%2C%22marketing%22:true%2C%22updatedAt%22:{%22bundle%22:%222025-09-12T08:23:42.245Z%22}%2C%22versions%22:{%22bundle%22:[%226f6e0a18-e3dd-43e8-9e57-7e09f6d90239%22%2C%224900fd93-1d29-4f54-b165-82d98b47c9ce%22]}}; _ga=GA1.1.827517620.1757665421; __woltUid=6020ea5f-e8b8-428c-9dac-990e6762f56f; _yjsu_yjad=1757665423.89251f19-e392-4f9e-94be-d7cff326a0c8; telemetryDeviceId=6020ea5f-e8b8-428c-9dac-990e6762f56f; cwc-language=en; telemetryDeviceId_=6020ea5f-e8b8-428c-9dac-990e6762f56f; __woltUid_=6020ea5f-e8b8-428c-9dac-990e6762f56f; _gcl_au=1.1.1458055390.1773648206.1177876118.1774621016.1774621016; AwinChannelCookie=other; lantern=939b559d-7f23-4458-a2b1-d2601b19309f; telemetrySessionId=322cf981-a30b-460e-a2ad-9e2f2367718f; telemetrySessionId_=322cf981-a30b-460e-a2ad-9e2f2367718f; ravelinSessionId=rjs-e2022c3e-07d3-4c6a-910d-973b4273ee0d:06d1f5f9-6e7a-4264-a4f9-99b8cd114c0a; _gcl_gs=2.1.k1$i1779963260$u76688403; _gcl_aw=GCL.1779963265.Cj0KCQjwz9_QBhD_ARIsADnSCfDeqxKXB1Xh9RUGVRwf7mnE4LxtVzbthvyJMJSSSM68xyX2uMVi284aAqGQEALw_wcB; lastRskxRun=1780321818344; __woltAnalyticsId=322cf981-a30b-460e-a2ad-9e2f2367718f; _clck=16dc31a%5E2%5Eg6l%5E1%5E2081; __woltAnalyticsId_=322cf981-a30b-460e-a2ad-9e2f2367718f; _uetsid=14770a105f4c11f1aeea8d5d251cb0b5; _uetvid=cb244d408fb111f09fee47d7a0c43d54; _clsk=1u3utsu%5E1780491736196%5E6%5E1%5Er.clarity.ms%2Fcollect; _ga_CP7Z2F7NFM=GS2.1.s1780491578$o207$g1$t1780491739$j42$l0$h0$dOez4uWLiHxGYv2sVVpAgv3oKDuyOb-XwGg"
    }
    
    # JSON telo zahteva (Payload) umesto URL parametara
    payload = {
        "lat": float(lat),
        "lon": float(lon)
    }
    
    try:
        # Prebacivanje na .post() metodu sa prosleđivanjem json payload-a
        r = requests.post(url, json=payload, headers=headers, impersonate="chrome120", timeout=15)
        
        st.session_state['raw_api_debug'] = {
            "HTTP Status Kod": r.status_code,
            "Headers sa servera": dict(r.headers),
            "Sirov tekst odgovora (Prvih 300 karaktera)": r.text[:300]
        }
        
        if r.status_code != 200:
            return empty_df
            
        data = r.json()
        restaurants = []
        
        for section in data.get("sections", []):
            venues_in_section = []
            
            # Putanja A: Klasična struktura (items -> venue)
            for item in section.get("items", []):
                if isinstance(item, dict) and item.get("venue"):
                    venues_in_section.append(item.get("venue"))
            
            # Putanja B: Struktura za pretragu po kategorijama (section -> venue -> venue)
            if "venue" in section and isinstance(section["venue"], dict):
                sec_venue = section["venue"]
                if "venue" in sec_venue and isinstance(sec_venue["venue"], dict):
                    venues_in_section.append(sec_venue["venue"])
                elif "slug" in sec_venue or "id" in sec_venue:
                    venues_in_section.append(sec_venue)
            
            for v in venues_in_section:
                try:
                    loc = v.get("location")
                    v_lat, v_lon = 0.0, 0.0
                    if isinstance(loc, list) and len(loc) >= 2:
                        v_lat, v_lon = float(loc[1]), float(loc[0])
                    elif isinstance(loc, dict):
                        v_lat = float(loc.get("latitude", loc.get("lat", 0)))
                        v_lon = float(loc.get("longitude", loc.get("lon", 0)))
                    
                    rating_dict = v.get("rating") or {}
                    score = rating_dict.get("score", 0) if isinstance(rating_dict, dict) else 0
                    volume = rating_dict.get("volume", 0) if isinstance(rating_dict, dict) else 0
                    
                    cats = v.get("categories", []) or []
                    cuisines = [str(c.get("name")) for c in cats if isinstance(c, dict) and c.get("name")]
                    
                    restaurants.append({
                        "Name": v.get("name", "Unknown"),
                        "Wolt Link": f"https://wolt.com/en/srb/{city_slug}/restaurant/{v.get('slug', '')}",
                        "Cuisine_Raw": cuisines,
                        "Cuisine_Details": ", ".join(cuisines) if cuisines else "Other",
                        "Lat": v_lat,
                        "Lon": v_lon,
                        "Status": "Open 🟢" if v.get("online") else "Closed 🔴",
                        "Online": bool(v.get("online", False)),
                        "Rating": score,
                        "Rating_Count": int(volume)
                    })
                except:
                    continue
                    
        if restaurants:
            return pd.DataFrame(restaurants).drop_duplicates(subset=['Name'])
            
    except Exception as e:
        st.session_state['raw_api_debug'] = {"Fatalna greška": str(e)}
        
    return empty_df

def save_snapshot(df, city):
    """Sačuvaj snapshot u fajl specifičan za grad."""
    if not df.empty:
        df_save = df[["Name", "Rating_Count", "Rating", "Online", "Cuisine_Details"]].copy()
        df_save['timestamp'] = datetime.datetime.now(local_tz).strftime('%Y-%m-%d %H:%M:%S')
        df_save['city'] = city
        file_exists = os.path.exists(DB_FILE)
        df_save.to_csv(DB_FILE, mode='a', header=not file_exists, index=False, quoting=csv.QUOTE_ALL)
        return True
    return False

def load_history(city):
    """Učitaj istoriju za određeni grad."""
    if not os.path.exists(DB_FILE):
        return pd.DataFrame()
    try:
        h = pd.read_csv(DB_FILE)
        h['timestamp'] = pd.to_datetime(h['timestamp'])
        h['Rating_Count'] = pd.to_numeric(h['Rating_Count'], errors='coerce').fillna(0).astype(int)
        if 'city' in h.columns:
            h = h[h['city'] == city]
        return h
    except Exception:
        return pd.DataFrame()

def auto_save_if_needed(df, city):
    """Automatski sačuvaj snapshot ako je prošlo dovoljno vremena od poslednjeg."""
    h = load_history(city)
    now = datetime.datetime.now(local_tz)
    if h.empty:
        save_snapshot(df, city)
        return True
    last_ts = h['timestamp'].max()
    if (now.replace(tzinfo=None) - last_ts.replace(tzinfo=None)) > datetime.timedelta(minutes=5):
        save_snapshot(df, city)
        return True
    return False

# --- 5. SIDEBAR ---
st.sidebar.title("🛠️ Control Panel")
city_name = st.sidebar.selectbox("City:", list(CITIES.keys()))
if city_name != st.session_state.current_city:
    st.session_state.current_city = city_name
    st.session_state.lat, st.session_state.lon = CITIES[city_name]["coords"]
    st.cache_data.clear()
    st.rerun()

filter_status = st.sidebar.radio("Show only:", ["All", "Open 🟢", "Closed 🔴"])

st.sidebar.markdown("---")
refresh_min = st.sidebar.number_input("Refresh Interval (min):", 1, 60, 5)
st.session_state.timer_active = st.sidebar.toggle("▶️ Activate Timer", value=st.session_state.timer_active)

if st.session_state.timer_active:
    countdown_timer(refresh_min)
    st_autorefresh(interval=refresh_min * 60000, key="global_refresh")

# --- 6. DATA PROCESSING ---
df_raw = fetch_wolt_data(st.session_state.lat, st.session_state.lon, CITIES[city_name]["slug"])

# st.cache_data serijalizuje liste u stringove — konvertuj nazad u liste
if not df_raw.empty and 'Cuisine_Raw' in df_raw.columns:
    import ast
    def parse_cuisine_raw(val):
        if isinstance(val, list):
            return val
        if isinstance(val, str):
            try:
                parsed = ast.literal_eval(val)
                return parsed if isinstance(parsed, list) else []
            except Exception:
                return [v.strip() for v in val.split(",") if v.strip()] if val else []
        return []
    df_raw['Cuisine_Raw'] = df_raw['Cuisine_Raw'].apply(parse_cuisine_raw)

df_main = df_raw.copy()

if not df_raw.empty:
    if filter_status == "Open 🟢": df_main = df_raw[df_raw['Online'] == True]
    elif filter_status == "Closed 🔴": df_main = df_raw[df_raw['Online'] == False]
    # Automatski sačuvaj snapshot pri svakom učitavanju (max jednom na 5 min)
    auto_save_if_needed(df_raw, city_name)

tab1, tab2, tab3, tab4 = st.tabs(["🟢 Radar", "📉 Market Analysis", "📈 Traffic Tracker", "☁️ Service Cloud"])

# --- TAB 1: RADAR ---
with tab1:
    if df_main.empty:
        st.error("❌ Podaci nisu učitani.")
        st.subheader("🔍 BI Radar - Live Debug Inspector")
        if 'raw_api_debug' in st.session_state:
            st.json(st.session_state['raw_api_debug'])
    else:
        col_m1, col_m2 = st.columns(2)
        col_m1.metric("Open 🟢", len(df_main[df_main['Online'] == True]))
        col_m2.metric("Closed 🔴", len(df_main[df_main['Online'] == False]))
        
        m1 = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=14)
        folium.Marker([st.session_state.lat, st.session_state.lon], icon=folium.Icon(color='blue', icon='home')).add_to(m1)
        for _, r in df_main.iterrows():
            color = "green" if r['Online'] else "red"
            folium.CircleMarker([r['Lat'], r['Lon']], radius=7, color=color, fill=True, tooltip=r['Name']).add_to(m1)
        
        map_resp = st_folium(m1, width="100%", height=500, key="m1")
        if map_resp and map_resp.get("last_clicked"):
            st.session_state.lat, st.session_state.lon = map_resp["last_clicked"]["lat"], map_resp["last_clicked"]["lng"]
            st.cache_data.clear()
            st.rerun()

        st.dataframe(df_main[["Name", "Status", "Rating", "Cuisine_Details", "Wolt Link"]], use_container_width=True, hide_index=True, column_config={"Wolt Link": st.column_config.LinkColumn("Link")})

# --- TAB 2: MARKET ANALYSIS ---
with tab2:
    if df_main.empty:
        st.error("❌ Podaci nisu učitani.")
    else:
        # Flatten cuisine lists, skip empty
        flat_cats = [item for sublist in df_main['Cuisine_Raw'] for item in sublist if item]
        unique_cats = sorted(list(set(flat_cats)))

        if not unique_cats:
            st.warning("⚠️ Nema podataka o kuhinjama za trenutni skup restorana.")
        else:
            selection = st.selectbox("🍽️ Filter by Cuisine:", ["All"] + unique_cats)

            if selection != "All":
                df_f = df_main[df_main['Cuisine_Raw'].apply(lambda x: selection in x if isinstance(x, list) else False)]
            else:
                df_f = df_main

            # Metrics row
            col1, col2, col3 = st.columns(3)
            col1.metric("🏪 Ukupno restorana", len(df_f))
            col2.metric("🟢 Otvoreni", len(df_f[df_f['Online'] == True]))
            col3.metric("🔴 Zatvoreni", len(df_f[df_f['Online'] == False]))

            # Map
            m2 = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=14)
            for _, r in df_f.iterrows():
                color = "green" if r['Online'] else "red"
                folium.CircleMarker(
                    [r['Lat'], r['Lon']], radius=8, color=color, fill=True,
                    tooltip=f"{r['Name']} | {r['Cuisine_Details']}"
                ).add_to(m2)
            st_folium(m2, width="100%", height=500, key="m2")

            # Table of filtered restaurants
            st.subheader(f"📋 Restorani ({len(df_f)})")
            st.dataframe(
                df_f[["Name", "Status", "Rating", "Rating_Count", "Cuisine_Details", "Wolt Link"]],
                use_container_width=True,
                hide_index=True,
                column_config={"Wolt Link": st.column_config.LinkColumn("Link")}
            )

            # Cuisine distribution chart (only when "All" selected)
            if selection == "All" and flat_cats:
                st.subheader("📊 Distribucija kuhinja")
                from collections import Counter
                cuisine_counts = Counter(flat_cats)
                cuisine_df = pd.DataFrame(cuisine_counts.items(), columns=["Kuhinja", "Broj restorana"]).sort_values("Broj restorana", ascending=False).head(20)
                st.bar_chart(cuisine_df.set_index("Kuhinja"))

# --- TAB 3: TRAFFIC TRACKER ---
with tab3:
    st.title("📈 Traffic Tracker")

    if df_raw.empty:
        st.error("❌ Nema podataka za prikaz.")
    else:
        h = load_history(city_name)
        unique_timestamps = sorted(h['timestamp'].unique()) if not h.empty else []
        num_scans = len(unique_timestamps)

        # ── PRVI SCAN: samo prikaži tabelu ──────────────────────────────────────
        if num_scans <= 1:
            ts_label = unique_timestamps[0].strftime('%d.%m.%Y u %H:%M:%S') if num_scans == 1 else "upravo sada"
            st.info(f"📋 **Ovo je prvi scan** — {ts_label}. Sledeći put kad se aplikacija učita ili osvježi, prikazaće se poređenje.")

            display_df = df_raw[["Name", "Rating_Count", "Rating", "Online", "Cuisine_Details"]].copy()
            display_df = display_df.rename(columns={
                "Name": "Restoran",
                "Rating_Count": "Broj ocena",
                "Rating": "Ocena",
                "Online": "Status",
                "Cuisine_Details": "Kuhinja"
            })
            display_df["Status"] = display_df["Status"].apply(lambda x: "🟢 Otvoren" if x else "🔴 Zatvoren")
            display_df = display_df.sort_values("Broj ocena", ascending=False)

            st.subheader(f"📋 Svi restorani — {len(display_df)} ukupno")
            st.dataframe(display_df, use_container_width=True, hide_index=True)

        # ── SLEDEĆI SCANOVI: poređenje prethodni vs trenutni ────────────────────
        else:
            prev_ts = unique_timestamps[-2]
            curr_ts = unique_timestamps[-1]

            df_prev = h[h['timestamp'] == prev_ts][["Name", "Rating_Count"]].copy()
            df_prev = df_prev.rename(columns={"Rating_Count": "Ocene_pre"})

            df_curr = df_raw[["Name", "Rating_Count", "Rating", "Online", "Cuisine_Details"]].copy()
            df_curr = df_curr.rename(columns={"Rating_Count": "Ocene_sada"})

            merged = pd.merge(df_curr, df_prev, on="Name", how="left")
            merged["Ocene_pre"] = merged["Ocene_pre"].fillna(0).astype(int)
            merged["Ocene_sada"] = merged["Ocene_sada"].fillna(0).astype(int)
            merged["Δ Ocena"] = merged["Ocene_sada"] - merged["Ocene_pre"]
            merged["Est. narudžbi"] = merged["Δ Ocena"] * 10

            # Novi restorani (nisu bili u prethodnom scanu)
            new_restaurants = merged[merged["Ocene_pre"] == 0]["Name"].tolist()

            # Metrike
            total_new_orders = int(merged[merged["Δ Ocena"] > 0]["Est. narudžbi"].sum())
            active_count = int((merged["Δ Ocena"] > 0).sum())

            col1, col2, col3, col4 = st.columns(4)
            col1.metric("🕐 Prethodni scan", prev_ts.strftime('%d.%m. %H:%M'))
            col2.metric("🕐 Trenutni scan", curr_ts.strftime('%d.%m. %H:%M'))
            col3.metric("📦 Est. novih narudžbi", total_new_orders)
            col4.metric("🔥 Aktivnih restorana", active_count)

            st.divider()

            # Pripremi tabelu za prikaz
            display = merged[[
                "Name", "Online", "Cuisine_Details",
                "Ocene_pre", "Ocene_sada", "Δ Ocena", "Est. narudžbi"
            ]].copy()
            display = display.rename(columns={
                "Name": "Restoran",
                "Online": "Status",
                "Cuisine_Details": "Kuhinja",
                "Ocene_pre": f"Ocene ({prev_ts.strftime('%H:%M')})",
                "Ocene_sada": f"Ocene ({curr_ts.strftime('%H:%M')})",
            })
            display["Status"] = display["Status"].apply(lambda x: "🟢" if x else "🔴")

            # Tabela sa svim restoranima, sortirano po rastu
            st.subheader("📊 Poređenje svih restorana")
            display_sorted = display.sort_values("Δ Ocena", ascending=False)

            # Kolorna oznaka rasta
            def highlight_growth(val):
                if isinstance(val, (int, float)):
                    if val > 0: return 'background-color: #d4edda; color: #155724'
                    elif val < 0: return 'background-color: #f8d7da; color: #721c24'
                return ''

            st.dataframe(
                display_sorted,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Δ Ocena": st.column_config.NumberColumn("Δ Ocena", format="%+d"),
                    "Est. narudžbi": st.column_config.NumberColumn("Est. narudžbi", format="%+d"),
                }
            )

            if new_restaurants:
                st.info(f"🆕 **Novi restorani od poslednjeg scana:** {', '.join(new_restaurants[:10])}" +
                        (f" i još {len(new_restaurants)-10}" if len(new_restaurants) > 10 else ""))

            # Dugme za ručni export
            st.divider()
            if st.button("💾 Preuzmi istoriju kao CSV"):
                full_h = load_history(city_name)
                csv_data = full_h.to_csv(index=False).encode('utf-8')
                st.download_button("⬇️ Preuzmi radar_history.csv", csv_data, "radar_history.csv", "text/csv")

# --- TAB 4: SERVICE CLOUD ---
with tab4:
    m4 = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=13, tiles="cartodbpositron")
    df_a = df_main[df_main['Online'] == True] if not df_main.empty else pd.DataFrame()
    
    if not df_a.empty:
        pts = [[r['Lat'], r['Lon'], 1.0] for _, r in df_a.iterrows()]
        
        inverted_gradient = {
            0.2: '#FF0000', 
            0.4: '#FF8C00', 
            0.6: '#FFFF00', 
            0.8: '#00FF00', 
            1.0: '#0000FF'
        }
        
        HeatMap(pts, radius=45, blur=30, gradient=inverted_gradient).add_to(m4)
        folium_static(m4, width=1400, height=800)
