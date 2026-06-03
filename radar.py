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
import pytz
import streamlit.components.v1 as components

# --- 1. CONFIGURATION & TIMEZONE ---
st.set_page_config(page_title="Wolt BI Radar PRO v28.3", layout="wide", page_icon="📡")

local_tz = pytz.timezone("Europe/Belgrade")

CITIES = {
    "Nis":        {"coords": (43.3209, 21.8958), "slug": "nis"},
    "Belgrade":   {"coords": (44.7866, 20.4489), "slug": "beograd"},
    "Novi Sad":   {"coords": (45.2671, 19.8335), "slug": "novi-sad"},
    "Kragujevac": {"coords": (44.0128, 20.9114), "slug": "kragujevac"},
}

DB_FILE = "radar_history.csv"

# --- 2. SESSION STATE ---
if "lat" not in st.session_state:
    st.session_state.lat, st.session_state.lon = CITIES["Nis"]["coords"]
if "current_city" not in st.session_state:
    st.session_state.current_city = "Nis"
if "timer_active" not in st.session_state:
    st.session_state.timer_active = False

# --- 3. UI COMPONENTS ---
def countdown_timer(minutes):
    seconds = minutes * 60
    html_code = f"""
    <div id="timer-container" style="padding:15px; border-radius:10px; background-color:#f8f9fa;
         text-align:center; border:1px solid #e9ecef; margin-bottom:20px;">
        <p style="margin:0; font-size:0.85rem; color:#6c757d; font-family:sans-serif;
           text-transform:uppercase; letter-spacing:1px;">Next Refresh In:</p>
        <span id="timer" style="font-size:2rem; font-weight:bold; color:#00c2e8;
              font-family:'Courier New',monospace;">--:--</span>
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
    components.html(html_code, height=120)

# --- 4. DATA SCRAPER ---
@st.cache_data(ttl=60)
def fetch_wolt_data(lat, lon, city_slug):
    cols = ["Name", "Wolt Link", "Cuisine_Raw", "Cuisine_Details",
            "Lat", "Lon", "Status", "Online", "Rating", "Rating_Count"]
    empty_df = pd.DataFrame(columns=cols)

    # ✅ ISPRAVLJENO: consumer-api.wolt.com umesto restaurant-api.wolt.com
    url = "https://consumer-api.wolt.com/v1/pages/restaurants"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Origin": "https://wolt.com",
        "Referer": f"https://wolt.com/en/srb/{city_slug}",
    }

    try:
        r = requests.get(
            url,
            params={"lat": lat, "lon": lon},
            headers=headers,
            impersonate="chrome124",  # ✅ noviji Chrome fingerprint
            timeout=15,
        )

        if r.status_code != 200:
            st.error(f"API greška: HTTP {r.status_code}")
            return empty_df

        data = r.json()
        sections = data.get("sections", [])
        restaurants = []

        for section in sections:
            for item in section.get("items", []):
                # Wolt može da pakuje venue direktno ili pod "venue" ključem
                v = item.get("venue")
                if not v:
                    # Novi format: venue polja su direktno na item-u
                    if item.get("slug") and item.get("name"):
                        v = item
                    else:
                        continue

                # ── Kategorije / kuhinje ──────────────────────────────────
                cats = v.get("categories", [])
                if cats and isinstance(cats[0], dict):
                    cuisines = [c.get("name", "") for c in cats]
                else:
                    cuisines = v.get("tags", []) or []

                # ── Lokacija ─────────────────────────────────────────────
                location = v.get("location", {})
                if isinstance(location, dict):
                    # {"coordinates": [lon, lat], "type": "Point"}
                    coords = location.get("coordinates", [0, 0])
                    lon_r, lat_r = float(coords[0]), float(coords[1])
                elif isinstance(location, list) and len(location) >= 2:
                    lon_r, lat_r = float(location[0]), float(location[1])
                else:
                    lon_r, lat_r = 0.0, 0.0

                # ── Rating ───────────────────────────────────────────────
                rating_obj = v.get("rating") or {}
                if isinstance(rating_obj, dict):
                    rating_score = rating_obj.get("score", 0) or 0
                    rating_vol   = int(rating_obj.get("volume", 0) or 0)
                else:
                    rating_score, rating_vol = 0, 0

                restaurants.append({
                    "Name":            v.get("name", ""),
                    "Wolt Link":       f"https://wolt.com/en/srb/{city_slug}/restaurant/{v.get('slug', '')}",
                    "Cuisine_Raw":     cuisines,
                    "Cuisine_Details": ", ".join(cuisines) if cuisines else "Other",
                    "Lat":             lat_r,
                    "Lon":             lon_r,
                    "Status":          "Open 🟢" if v.get("online") else "Closed 🔴",
                    "Online":          bool(v.get("online", False)),
                    "Rating":          rating_score,
                    "Rating_Count":    rating_vol,
                })

        if restaurants:
            return pd.DataFrame(restaurants).drop_duplicates(subset=["Name"])

        # ── Debug: pokaži strukturu ako nema restorana ───────────────────
        st.warning(
            f"API odgovorio OK ali nema restorana. "
            f"Broj sekcija: {len(sections)}. "
            f"Proveri strukturu u konzoli."
        )
        # Odkomentariši sledeće za debug:
        # st.json(data)

    except Exception as e:
        st.error(f"Greška pri učitavanju podataka: {e}")

    return empty_df


def save_snapshot(df):
    if not df.empty:
        df_save = df.copy()
        if "Cuisine_Raw" in df_save.columns:
            df_save = df_save.drop(columns=["Cuisine_Raw"])
        df_save["timestamp"] = datetime.datetime.now(local_tz).strftime("%Y-%m-%d %H:%M:%S")
        df_save.to_csv(
            DB_FILE, mode="a",
            header=not os.path.exists(DB_FILE),
            index=False,
            quoting=csv.QUOTE_ALL,
        )
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
st.session_state.timer_active = st.sidebar.toggle(
    "▶️ Activate Timer", value=st.session_state.timer_active
)

if st.session_state.timer_active:
    countdown_timer(refresh_min)
    st_autorefresh(interval=refresh_min * 60000, key="global_refresh")

# --- 6. DATA PROCESSING ---
df_raw  = fetch_wolt_data(st.session_state.lat, st.session_state.lon, CITIES[city_name]["slug"])
df_main = df_raw.copy()

if not df_raw.empty:
    if filter_status == "Open 🟢":
        df_main = df_raw[df_raw["Online"] == True]
    elif filter_status == "Closed 🔴":
        df_main = df_raw[df_raw["Online"] == False]

tab1, tab2, tab3, tab4 = st.tabs(
    ["🟢 Radar", "📉 Market Analysis", "📈 Traffic Tracker", "☁️ Service Cloud"]
)

# --- TAB 1: RADAR ---
with tab1:
    col_m1, col_m2 = st.columns(2)
    col_m1.metric("Open 🟢",   len(df_main[df_main["Online"] == True]))
    col_m2.metric("Closed 🔴", len(df_main[df_main["Online"] == False]))

    m1 = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=14)
    folium.Marker(
        [st.session_state.lat, st.session_state.lon],
        icon=folium.Icon(color="blue", icon="home"),
    ).add_to(m1)

    for _, row in df_main.iterrows():
        color = "green" if row["Online"] else "red"
        folium.CircleMarker(
            [row["Lat"], row["Lon"]],
            radius=7, color=color, fill=True,
            tooltip=row["Name"],
        ).add_to(m1)

    map_resp = st_folium(m1, width="100%", height=500, key="m1")
    if map_resp and map_resp.get("last_clicked"):
        st.session_state.lat = map_resp["last_clicked"]["lat"]
        st.session_state.lon = map_resp["last_clicked"]["lng"]
        st.cache_data.clear()
        st.rerun()

    if not df_main.empty:
        st.dataframe(
            df_main[["Wolt Link", "Status", "Rating", "Cuisine_Details"]],
            use_container_width=True,
            hide_index=True,
            column_config={"Wolt Link": st.column_config.LinkColumn("Restaurant")},
        )
    else:
        st.info("Nema podataka za prikaz. Proveri internet konekciju ili pokušaj ponovo.")

# --- TAB 2: MARKET ANALYSIS ---
with tab2:
    if not df_main.empty:
        flat_cats  = [item for sublist in df_main["Cuisine_Raw"] for item in sublist]
        unique_cats = sorted(set(flat_cats))
        selection  = st.selectbox("Filter by Cuisine:", ["All"] + unique_cats)

        df_f = (
            df_main[df_main["Cuisine_Raw"].apply(lambda x: selection in x)]
            if selection != "All"
            else df_main
        )

        m2 = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=14)
        for _, row in df_f.iterrows():
            color = "green" if row["Online"] else "red"
            folium.CircleMarker(
                [row["Lat"], row["Lon"]],
                radius=8, color=color, fill=True,
                tooltip=row["Name"],
            ).add_to(m2)
        st_folium(m2, width="100%", height=500, key="m2")
    else:
        st.info("Nema podataka za analizu.")

# --- TAB 3: TRAFFIC TRACKER ---
with tab3:
    st.title("📈 Traffic Tracker")

    if st.button("💾 SAVE CURRENT STATE TO ARCHIVE"):
        if save_snapshot(df_raw):
            st.success("Snapshot sačuvan!")
        else:
            st.warning("Nema podataka za čuvanje.")
        st.rerun()

    if os.path.exists(DB_FILE):
        h = pd.read_csv(DB_FILE)
        # Kompatibilnost sa starim srpskim kolonama
        h = h.rename(columns={"Ime": "Name", "Broj_Ocena": "Rating_Count", "Ocena": "Rating"})
        h["timestamp"] = pd.to_datetime(h["timestamp"])

        st.divider()
        st.subheader("📅 Compare with History")

        available_dates = sorted(h["timestamp"].dt.date.unique(), reverse=True)
        sel_date = st.date_input("1. Select Baseline Date:", value=available_dates[-1])

        day_snaps = h[h["timestamp"].dt.date == sel_date]
        times = sorted(day_snaps["timestamp"].dt.time.unique())

        if times:
            sel_time    = st.selectbox("2. Select Baseline Time:", times)
            baseline_ts = pd.to_datetime(f"{sel_date} {sel_time}")
            latest_ts   = h["timestamp"].max()

            if baseline_ts < latest_ts:
                st.info(
                    f"Analiza od {baseline_ts.strftime('%H:%M')} "
                    f"do {latest_ts.strftime('%H:%M')}"
                )
                df_pre = h[h["timestamp"] == baseline_ts].copy()
                df_now = h[h["timestamp"] == latest_ts].copy()

                m = pd.merge(df_now, df_pre, on="Name", suffixes=("_now", "_pre"))
                m["Rating_Count_now"] = pd.to_numeric(m["Rating_Count_now"], errors="coerce").fillna(0)
                m["Rating_Count_pre"] = pd.to_numeric(m["Rating_Count_pre"], errors="coerce").fillna(0)
                m["Growth"]    = m["Rating_Count_now"] - m["Rating_Count_pre"]
                m["Est_Orders"] = m["Growth"] * 10

                res = m[m["Growth"] > 0].sort_values("Growth", ascending=False)
                if not res.empty:
                    st.metric("Total Estimated New Orders", int(res["Est_Orders"].sum()))
                    st.dataframe(
                        res[["Name", "Growth", "Est_Orders", "Rating_now"]],
                        use_container_width=True,
                        hide_index=True,
                    )
                else:
                    st.warning("Nema promene u ocenama.")
    else:
        st.info("Arhiva je prazna. Sačuvaj snapshot da počneš praćenje.")

# --- TAB 4: SERVICE CLOUD ---
with tab4:
    m4 = folium.Map(
        location=[st.session_state.lat, st.session_state.lon],
        zoom_start=13,
        tiles="cartodbpositron",
    )

    df_a = df_main[df_main["Online"] == True] if not df_main.empty else pd.DataFrame()

    if not df_a.empty:
        pts = [[row["Lat"], row["Lon"], 1.0] for _, row in df_a.iterrows()]

        inverted_gradient = {
            0.2: "#FF0000",
            0.4: "#FF8C00",
            0.6: "#FFFF00",
            0.8: "#00FF00",
            1.0: "#0000FF",
        }
        HeatMap(pts, radius=45, blur=30, gradient=inverted_gradient).add_to(m4)
        folium_static(m4, width=1400, height=800)
    else:
        st.info("Nema aktivnih restorana za heatmap.")
