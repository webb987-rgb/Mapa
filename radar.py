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
import pytz  # Corrected import
import streamlit.components.v1 as components

# --- 1. CONFIGURATION & TIMEZONE ---
st.set_page_config(page_title="Wolt BI Radar PRO v28.0", layout="wide", page_icon="📡")

# Define Belgrade Timezone
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
    url = "https://restaurant-api.wolt.com/v1/pages/restaurants"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": f"https://wolt.com/en/srb/{city_slug}",
    }
    try:
        r = requests.get(url, params={"lat": lat, "lon": lon}, headers=headers, impersonate="chrome120", timeout=15)
        if r.status_code == 200:
            restaurants = []
            data = r.json()
            for section in data.get("sections", []):
                for item in section.get("items", []):
                    v = item.get("venue")
                    if v:
                        cats = v.get("categories", [])
                        cuisines = [c.get("name") for c in cats] or v.get("tags", [])
                        restaurants.append({
                            "Name": v.get("name"),
                            "Wolt Link": f"https://wolt.com/en/srb/{city_slug}/restaurant/{v.get('slug')}",
                            "Cuisine_Raw": cuisines,
                            "Cuisine_Details": ", ".join(cuisines) if cuisines else "Other",
                            "Lat": float(v.get("location", [0, 0])[1]),
                            "Lon": float(v.get("location", [0, 0])[0]),
                            "Status": "Open 🟢" if v.get("online") else "Closed 🔴",
                            "Online": v.get("online", False),
                            "Rating": v.get("rating", {}).get("score", 0),
                            "Rating_Count": int(v.get("rating", {}).get("volume", 0))
                        })
            if restaurants:
                return pd.DataFrame(restaurants).drop_duplicates(subset=['Name'])
    except: pass
    return pd.DataFrame(columns=cols)

def save_snapshot(df):
    if not df.empty:
        df_save = df.copy()
        if 'Cuisine_Raw' in df_save.columns: df_save = df_save.drop(columns=['Cuisine_Raw'])
        # Save with Belgrade time
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
refresh_min = st.sidebar.number_input("Refresh (min):", 1, 60, 5)
st.session_state.timer_active = st.sidebar.toggle("▶️ Start Auto-Refresh", value=st.session_state.timer_active)

if st.session_state.timer_active:
    countdown_timer(refresh_min)
    st_autorefresh(interval=refresh_min * 60000, key="global_refresh")

# --- 6. MAIN APP LOGIC ---
df_raw = fetch_wolt_data(st.session_state.lat, st.session_state.lon, CITIES[city_name]["slug"])
df_main = df_raw.copy()

if not df_raw.empty:
    if filter_status == "Open 🟢": df_main = df_raw[df_raw['Online'] == True]
    elif filter_status == "Closed 🔴": df_main = df_raw[df_raw['Online'] == False]

tab1, tab2, tab3, tab4 = st.tabs(["🟢 Radar", "📉 Market Analysis", "📈 Traffic Tracker", "☁️ Service Cloud"])

with tab1:
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
    st.dataframe(df_main[["Wolt Link", "Status", "Rating", "Cuisine_Details"]], use_container_width=True, hide_index=True, column_config={"Wolt Link": st.column_config.LinkColumn("Restaurant")})

with tab3:
    st.title("📈 Traffic Tracker")
    if st.button("💾 SAVE SNAPSHOT"):
        save_snapshot(df_raw)
        st.success("Data archived successfully!")
        st.rerun()

    if os.path.exists(DB_FILE):
        h = pd.read_csv(DB_FILE)
        h['timestamp'] = pd.to_datetime(h['timestamp'])
        
        st.subheader("Compare with Historical Data")
        dates = h['timestamp'].dt.date.unique()
        selected_date = st.date_input("Select Date:", value=dates[-1])
        
        # Filter times for that date
        times = h[h['timestamp'].dt.date == selected_date]['timestamp'].dt.time.unique()
        selected_time = st.selectbox("Select Baseline Time:", times)
        
        baseline_ts = pd.to_datetime(f"{selected_date} {selected_time}")
        latest_ts = h['timestamp'].max()
        
        if baseline_ts < latest_ts:
            df_pre = h[h['timestamp'] == baseline_ts]
            df_now = h[h['timestamp'] == latest_ts]
            
            m = pd.merge(df_now, df_pre, on="Name", suffixes=('_now', '_pre'))
            m['Growth'] = m['Rating_Count_now'] - m['Rating_Count_pre']
            m['Est_Orders'] = m['Growth'] * 10
            
            growth_df = m[m['Growth'] > 0].sort_values(by='Growth', ascending=False)
            st.metric("Total Estimated New Orders", int(growth_df['Est_Orders'].sum()))
            st.dataframe(growth_df[["Name", "Growth", "Est_Orders"]], use_container_width=True, hide_index=True)
