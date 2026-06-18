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

# --- 4. DATA SCRAPER ---
@st.cache_data(ttl=60)
def fetch_wolt_data(lat, lon, city_slug):
    cols = ["Name", "Wolt Link", "Cuisine_Raw", "Cuisine_Details", "Lat", "Lon", "Status", "Online", "Rating", "Rating_Count"]
    empty_df = pd.DataFrame(columns=cols)
    
    url = "https://consumer-api.wolt.com/v1/pages/category/restaurants"
    
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
    
    payload = {
        "lat": float(lat),
        "lon": float(lon)
    }
    
    try:
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
            
            for item in section.get("items", []):
                if isinstance(item, dict) and item.get("venue"):
                    venues_in_section.append(item.get("venue"))
            
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

def save_snapshot(df):
    if not df.empty:
        df_save = df.copy()
        if 'Cuisine_Raw' in df_save.columns: df_save = df_save.drop(columns=['Cuisine_Raw'])
        df_save['timestamp'] = datetime.datetime.now(local_tz).strftime('%Y-%m-%d %H:%M:%S')
        df_save.to_csv(DB_FILE, mode='a', header=not os.path.exists(DB_FILE), index=False, quoting=csv.QUOTE_ALL)
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
df_main = df_raw.copy()

if not df_raw.empty:
    if filter_status == "Open 🟢": df_main = df_raw[df_raw['Online'] == True]
    elif filter_status == "Closed 🔴": df_main = df_raw[df_raw['Online'] == False]

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
    if not df_main.empty:
        flat_cats = [item for sublist in df_main['Cuisine_Raw'] for item in sublist]
        unique_cats = sorted(list(set(flat_cats)))
        selection = st.selectbox("Filter by Cuisine:", ["All"] + unique_cats)
        df_f = df_main[df_main['Cuisine_Raw'].apply(lambda x: selection in x)] if selection != "All" else df_main
        
        m2 = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=14)
        for _, r in df_f.iterrows():
            color = "green" if r['Online'] else "red"
            folium.CircleMarker([r['Lat'], r['Lon']], radius=8, color=color, fill=True, tooltip=r['Name']).add_to(m2)
        st_folium(m2, width="100%", height=500, key="m2")

# --- TAB 3: TRAFFIC TRACKER ---
with tab3:
    st.title("📈 Traffic Tracker")
    if st.button("💾 SAVE CURRENT STATE TO ARCHIVE"):
        save_snapshot(df_raw)
        st.success("Snapshot saved successfully!")
        st.rerun()

    if os.path.exists(DB_FILE):
        h = pd.read_csv(DB_FILE)
        h = h.rename(columns={"Ime": "Name", "Broj_Ocena": "Rating_Count", "Ocena": "Rating"})
        h['timestamp'] = pd.to_datetime(h['timestamp'])

        st.divider()

        all_timestamps = sorted(h['timestamp'].unique())

        # Ako postoji samo jedan snapshot, prikaži ga odmah
        if len(all_timestamps) == 1:
            st.subheader("📋 First Snapshot — All Restaurants")
            df_first = h[h['timestamp'] == all_timestamps[0]].copy()
            df_first['Rating_Count'] = pd.to_numeric(df_first['Rating_Count'], errors='coerce').fillna(0).astype(int)
            df_first['Rating'] = pd.to_numeric(df_first['Rating'], errors='coerce').fillna(0).round(2)
            df_first = df_first.sort_values(by='Rating_Count', ascending=False)

            st.metric("Total Restaurants", len(df_first))
            st.dataframe(
                df_first[["Name", "Rating", "Rating_Count", "Status"]],
                use_container_width=True,
                hide_index=True
            )
        else:
            st.subheader("📅 Compare with History")

            available_dates = sorted(h['timestamp'].dt.date.unique(), reverse=True)
            sel_date = st.date_input("1. Select Baseline Date:", value=available_dates[-1])

            day_snaps = h[h['timestamp'].dt.date == sel_date]
            times = sorted(day_snaps['timestamp'].dt.time.unique())

            if len(times) > 0:
                sel_time = st.selectbox("2. Select Baseline Time:", times)
                baseline_ts = pd.to_datetime(f"{sel_date} {sel_time}")
                latest_ts = h['timestamp'].max()

                # Ako je izabrani baseline == latest, prikaži snapshot direktno
                if baseline_ts == latest_ts:
                    st.info("Only one unique timestamp selected. Showing full snapshot:")
                    df_snap = h[h['timestamp'] == baseline_ts].copy()
                    df_snap['Rating_Count'] = pd.to_numeric(df_snap['Rating_Count'], errors='coerce').fillna(0).astype(int)
                    df_snap['Rating'] = pd.to_numeric(df_snap['Rating'], errors='coerce').fillna(0).round(2)
                    df_snap = df_snap.sort_values(by='Rating_Count', ascending=False)
                    st.metric("Total Restaurants", len(df_snap))
                    st.dataframe(df_snap[["Name", "Rating", "Rating_Count", "Status"]], use_container_width=True, hide_index=True)

                elif baseline_ts < latest_ts:
                    st.info(f"Analyzing from {baseline_ts.strftime('%H:%M')} to {latest_ts.strftime('%H:%M')}")

                    df_pre = h[h['timestamp'] == baseline_ts].copy()
                    df_now = h[h['timestamp'] == latest_ts].copy()

                    m = pd.merge(df_now, df_pre, on="Name", suffixes=('_now', '_pre'))
                    m['Rating_Count_now'] = pd.to_numeric(m['Rating_Count_now'], errors='coerce').fillna(0)
                    m['Rating_Count_pre'] = pd.to_numeric(m['Rating_Count_pre'], errors='coerce').fillna(0)

                    m['Growth'] = m['Rating_Count_now'] - m['Rating_Count_pre']
                    m['Est_Orders'] = m['Growth'] * 10

                    res = m[m['Growth'] > 0].sort_values(by='Growth', ascending=False)
                    if not res.empty:
                        st.metric("Total Estimated New Orders", int(res['Est_Orders'].sum()))
                        st.dataframe(res[["Name", "Growth", "Est_Orders", "Rating_now"]], use_container_width=True, hide_index=True)
                    else:
                        st.warning("No change in ratings detected.")
    else:
        st.info("Archive is empty. Save a snapshot first.")

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
