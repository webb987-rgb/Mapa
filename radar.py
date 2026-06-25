import streamlit as st
from curl_cffi import requests
import pandas as pd
import folium
from folium.plugins import HeatMap
from streamlit_folium import st_folium, folium_static
from streamlit_autorefresh import st_autorefresh
import ast
import datetime
import os
import csv
import pytz
import streamlit.components.v1 as components
import hashlib
import plotly.express as px
import plotly.graph_objects as go

# --- Google Sheets ---
import gspread
from google.oauth2.service_account import Credentials
import json

# --- 1. CONFIGURATION & TIMEZONE ---
st.set_page_config(page_title="Wolt BI Radar PRO v29.0", layout="wide", page_icon="📡")

# DEBUG - obrisati nakon testiranja
try:
    st.sidebar.write("Secrets keys:", list(st.secrets.keys()))
except Exception as e:
    st.sidebar.error(f"Nema secrets: {e}")

local_tz = pytz.timezone("Europe/Belgrade")

CITIES = {
    "Nis": {"coords": (43.3209, 21.8958), "slug": "nis"},
    "Belgrade": {"coords": (44.7866, 20.4489), "slug": "beograd"},
    "Novi Sad": {"coords": (45.2671, 19.8335), "slug": "novi-sad"},
    "Kragujevac": {"coords": (44.0128, 20.9114), "slug": "kragujevac"}
}

DB_FILE = "radar_history.csv"

# Google Sheets worksheet name (tab u spreadsheetu)
GS_WORKSHEET = "radar_snapshots"

# --- 2. SESSION STATE ---
if 'lat' not in st.session_state:
    st.session_state.lat, st.session_state.lon = CITIES["Nis"]["coords"]
if 'current_city' not in st.session_state:
    st.session_state.current_city = "Nis"
if 'timer_active' not in st.session_state:
    st.session_state.timer_active = False
if 'map_data_hash' not in st.session_state:
    st.session_state.map_data_hash = ""

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

# --- 3.5 WOLT API HEADERS ---
WOLT_HEADERS = {
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

# --- 4. GOOGLE SHEETS HELPERS ---

@st.cache_resource
def get_gspread_client():
    """
    Ucitava Google service account credentials iz Streamlit secrets.
    U secrets.toml dodaj:
    
    [gcp_service_account]
    type = "service_account"
    project_id = "..."
    private_key_id = "..."
    private_key = "-----BEGIN RSA PRIVATE KEY-----\n..."
    client_email = "..."
    client_id = "..."
    auth_uri = "..."
    token_uri = "..."
    
    [google_sheets]
    spreadsheet_id = "1AbCdEfGhIjKlMnOpQrStUvWxYz..."
    """
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        st.sidebar.error(f"gspread auth greška: {e}")
        return None


def get_or_create_worksheet(client, spreadsheet_id, worksheet_name):
    """Otvara ili kreira worksheet u spreadsheetu."""
    try:
        sh = client.open_by_key(spreadsheet_id)
        try:
            ws = sh.worksheet(worksheet_name)
        except gspread.WorksheetNotFound:
            ws = sh.add_worksheet(title=worksheet_name, rows=10000, cols=10)
            # Header row
            ws.append_row(["timestamp", "city", "Name", "Rating_Count", "Rating", "Online", "Cuisine_Details"])
        return ws
    except Exception as e:
        return None


def save_to_gsheets(df, city):
    """Snima snapshot u Google Sheets. Vraca True ako uspje."""
    try:
        client = get_gspread_client()
        if client is None:
            return False, "Google Sheets nije konfigurisan (nedostaju secrets)."

        spreadsheet_id = st.secrets["google_sheets"]["spreadsheet_id"]
        ws = get_or_create_worksheet(client, spreadsheet_id, GS_WORKSHEET)
        if ws is None:
            return False, "Ne mogu da otvorim/kreiram worksheet."

        ts = datetime.datetime.now(local_tz).strftime('%Y-%m-%d %H:%M:%S')
        rows = []
        for _, row in df.iterrows():
            rows.append([
                ts,
                city,
                str(row.get("Name", "")),
                int(row.get("Rating_Count", 0)),
                float(row.get("Rating", 0)),
                bool(row.get("Online", False)),
                str(row.get("Cuisine_Details", "")),
            ])
        ws.append_rows(rows, value_input_option="RAW")
        return True, f"✅ Snimljeno {len(rows)} restorana u Google Sheets ({ts})"
    except Exception as e:
        return False, f"Greška pri snimanju u GSheets: {e}"


@st.cache_data(ttl=300)
def load_from_gsheets(city):
    """Ucitava historiju iz Google Sheets za dati grad."""
    try:
        client = get_gspread_client()
        if client is None:
            return pd.DataFrame()

        spreadsheet_id = st.secrets["google_sheets"]["spreadsheet_id"]
        sh = client.open_by_key(spreadsheet_id)
        ws = sh.worksheet(GS_WORKSHEET)

        records = ws.get_all_records()
        if not records:
            return pd.DataFrame()

        df = pd.DataFrame(records)
        df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
        df = df.dropna(subset=['timestamp'])
        df['Rating_Count'] = pd.to_numeric(df['Rating_Count'], errors='coerce').fillna(0).astype(int)
        df['Rating'] = pd.to_numeric(df['Rating'], errors='coerce').fillna(0.0)

        if 'city' in df.columns:
            df = df[df['city'] == city]

        return df
    except Exception:
        return pd.DataFrame()


def gsheets_configured():
    try:
        _ = st.secrets["gcp_service_account"]
        _ = st.secrets["google_sheets"]["spreadsheet_id"]
        return True
    except Exception as e:
        st.sidebar.error(f"Secrets greška: {e}")
        return False


# --- 5. DATA SCRAPER ---

@st.cache_data(ttl=60)
def fetch_venue_list(lat, lon, city_slug):
    cols = ["Name", "Wolt Link", "Cuisine_Raw", "Cuisine_Details",
            "Lat", "Lon", "Status", "Online", "Rating", "Rating_Count"]
    empty_df = pd.DataFrame(columns=cols)

    url = "https://consumer-api.wolt.com/v1/pages/restaurants"
    params = {"lat": float(lat), "lon": float(lon)}

    try:
        r = requests.get(url, params=params, headers=WOLT_HEADERS, impersonate="chrome120", timeout=15)

        st.session_state['raw_api_debug'] = {
            "Endpoint": url,
            "HTTP Status": r.status_code,
            "Prvih 300 karaktera": r.text[:300]
        }

        if r.status_code != 200:
            return empty_df

        data = r.json()
        sections = data.get("sections", [])
        venue_map = {}

        for section in sections:
            for item in section.get("items", []):
                v = item.get("venue")
                if not v or not isinstance(v, dict):
                    continue

                v_slug = v.get("slug", "")
                if not v_slug or v_slug in venue_map:
                    continue

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

                online = bool(v.get("online", False))

                raw_tags = []
                for field in ("tags", "categories", "food_categories", "cuisine_tags"):
                    val = v.get(field)
                    if isinstance(val, list):
                        for c in val:
                            if isinstance(c, dict):
                                name = c.get("name") or c.get("title") or c.get("slug", "")
                                if name:
                                    raw_tags.append(str(name))
                            elif isinstance(c, str) and c:
                                raw_tags.append(c)

                venue_map[v_slug] = {
                    "Name": v.get("name", "Unknown"),
                    "Wolt Link": f"https://wolt.com/en/srb/{city_slug}/restaurant/{v_slug}",
                    "Cuisine_Raw": sorted(set(raw_tags)),
                    "Cuisine_Details": ", ".join(sorted(set(raw_tags))) if raw_tags else "Other",
                    "Lat": v_lat,
                    "Lon": v_lon,
                    "Status": "Open 🟢" if online else "Closed 🔴",
                    "Online": online,
                    "Rating": score,
                    "Rating_Count": int(volume),
                }

        st.session_state['debug_sections'] = {
            "endpoint": url,
            "broj_sekcija": len(sections),
            "restorana_pronadjeno": len(venue_map),
            "online": sum(1 for v in venue_map.values() if v["Online"]),
            "offline": sum(1 for v in venue_map.values() if not v["Online"]),
        }

        if venue_map:
            df_result = pd.DataFrame(list(venue_map.values())).drop_duplicates(subset=['Name'])
            return df_result

    except Exception as e:
        st.session_state['raw_api_debug'] = {"Fatalna greška": str(e)}

    return empty_df


@st.cache_data(ttl=60)
def fetch_wolt_data(lat, lon, city_slug):
    cols = ["Name", "Wolt Link", "Cuisine_Raw", "Cuisine_Details",
            "Lat", "Lon", "Status", "Online", "Rating", "Rating_Count"]
    empty_df = pd.DataFrame(columns=cols)

    df_venue = fetch_venue_list(lat, lon, city_slug)
    if not df_venue.empty:
        return df_venue

    url = "https://consumer-api.wolt.com/v1/pages/category/restaurants"
    payload = {"lat": float(lat), "lon": float(lon)}

    try:
        r = requests.post(url, json=payload, headers=WOLT_HEADERS, impersonate="chrome120", timeout=15)

        if r.status_code != 200:
            return empty_df

        data = r.json()
        sections = data.get("sections", [])
        venue_map = {}

        for section in sections:
            for item in section.get("items", []):
                details = item.get("link", {}).get("menu_item_details", {})
                v_slug = details.get("venue_slug", "")
                if not v_slug or v_slug in venue_map:
                    continue

                rating_dict = details.get("venue_rating", {})
                score = rating_dict.get("score", 0) if isinstance(rating_dict, dict) else 0
                volume = rating_dict.get("volume", 0) if isinstance(rating_dict, dict) else 0

                estimate = details.get("estimate_range", "")
                online = bool(estimate and estimate != "")

                venue_map[v_slug] = {
                    "Name": details.get("venue_name", "Unknown"),
                    "Wolt Link": f"https://wolt.com/en/srb/{city_slug}/restaurant/{v_slug}",
                    "Cuisine_Raw": [],
                    "Cuisine_Details": "Other",
                    "Lat": 0.0,
                    "Lon": 0.0,
                    "Status": "Open 🟢" if online else "Closed 🔴",
                    "Online": online,
                    "Rating": score,
                    "Rating_Count": int(volume),
                }

        if venue_map:
            return pd.DataFrame(list(venue_map.values())).drop_duplicates(subset=['Name'])

    except Exception as e:
        st.session_state['raw_api_debug'] = {"Fatalna greška (fallback)": str(e)}

    return empty_df


def save_snapshot(df, city):
    if not df.empty:
        df_save = df[["Name", "Rating_Count", "Rating", "Online", "Cuisine_Details"]].copy()
        df_save['timestamp'] = datetime.datetime.now(local_tz).strftime('%Y-%m-%d %H:%M:%S')
        df_save['city'] = city
        file_exists = os.path.exists(DB_FILE)
        df_save.to_csv(DB_FILE, mode='a', header=not file_exists, index=False, quoting=csv.QUOTE_ALL)
        return True
    return False


def load_history(city):
    if not os.path.exists(DB_FILE):
        return pd.DataFrame()
    try:
        h = pd.read_csv(DB_FILE)
        h['timestamp'] = pd.to_datetime(h['timestamp'], errors='coerce')
        h = h.dropna(subset=['timestamp'])
        h['Rating_Count'] = pd.to_numeric(h['Rating_Count'], errors='coerce').fillna(0).astype(int)
        if 'city' in h.columns:
            h = h[h['city'] == city]
        return h
    except Exception:
        return pd.DataFrame()


def auto_save_if_needed(df, city):
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


def df_hash(df):
    """Pravi hash od DataFrame-a da bi izbjegao nepotreban re-render mape."""
    if df.empty:
        return "empty"
    return hashlib.md5(pd.util.hash_pandas_object(df[["Name", "Online"]]).to_json().encode()).hexdigest()[:12]


# --- 6. SIDEBAR ---
st.sidebar.title("🛠️ Control Panel")
city_name = st.sidebar.selectbox("City:", list(CITIES.keys()))
if city_name != st.session_state.current_city:
    st.session_state.current_city = city_name
    st.session_state.lat, st.session_state.lon = CITIES[city_name]["coords"]
    st.cache_data.clear()
    st.rerun()

st.sidebar.markdown("---")
if st.sidebar.button("🔄 Force Refresh (Clear Cache)"):
    st.cache_data.clear()
    st.session_state.pop('debug_sections', None)
    st.rerun()

filter_status = st.sidebar.radio("Show only:", ["All", "Open 🟢", "Closed 🔴"])

st.sidebar.markdown("---")
refresh_min = st.sidebar.number_input("Refresh Interval (min):", 1, 60, 5)
st.session_state.timer_active = st.sidebar.toggle("▶️ Activate Timer", value=st.session_state.timer_active)

if st.session_state.timer_active:
    countdown_timer(refresh_min)
    st_autorefresh(interval=refresh_min * 60000, key="global_refresh")

# Google Sheets status u sidebaru
st.sidebar.markdown("---")
if gsheets_configured():
    st.sidebar.success("🔗 Google Sheets: Aktivan")
else:
    st.sidebar.warning("⚠️ Google Sheets: Nije konfigurisan\n\nDodaj secrets u `.streamlit/secrets.toml`")

# --- 7. DATA PROCESSING ---
df_raw = fetch_wolt_data(st.session_state.lat, st.session_state.lon, CITIES[city_name]["slug"])

if not df_raw.empty and 'Cuisine_Raw' in df_raw.columns:
    df_raw['Cuisine_Raw'] = df_raw['Cuisine_Raw'].apply(parse_cuisine_raw)

df_main = df_raw.copy()

if not df_raw.empty:
    if filter_status == "Open 🟢":
        df_main = df_raw[df_raw['Online'] == True]
    elif filter_status == "Closed 🔴":
        df_main = df_raw[df_raw['Online'] == False]
    auto_save_if_needed(df_raw, city_name)

    # Auto-save u Google Sheets (samo jednom po sesiji, ne na svaki rerun)
    if gsheets_configured():
        gs_key = f"gs_saved_{city_name}_{datetime.datetime.now(local_tz).strftime('%Y-%m-%d_%H')}"
        if gs_key not in st.session_state:
            ok, msg = save_to_gsheets(df_raw, city_name)
            st.session_state[gs_key] = msg

tab1, tab2, tab3, tab4, tab5 = st.tabs(["🟢 Radar", "📉 Market Analysis", "📈 Traffic Tracker", "📊 Rating History", "☁️ Service Cloud"])

# --- TAB 1: RADAR ---
with tab1:
    if df_main.empty:
        st.error("❌ Podaci nisu učitani.")
        if 'raw_api_debug' in st.session_state:
            st.json(st.session_state['raw_api_debug'])
    else:
        col_m1, col_m2 = st.columns(2)
        col_m1.metric("Open 🟢", len(df_main[df_main['Online'] == True]))
        col_m2.metric("Closed 🔴", len(df_main[df_main['Online'] == False]))

        # --- FIX TREPERENJA: render mape samo ako su se podaci promijenili ---
        current_hash = df_hash(df_main)
        render_key = f"m1_{current_hash}_{st.session_state.lat:.4f}_{st.session_state.lon:.4f}"

        m1 = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=14)
        folium.Marker(
            [st.session_state.lat, st.session_state.lon],
            icon=folium.Icon(color='blue', icon='home')
        ).add_to(m1)
        for _, row in df_main.iterrows():
            color = "green" if row['Online'] else "red"
            folium.CircleMarker(
                [row['Lat'], row['Lon']], radius=7, color=color, fill=True,
                tooltip=f"{row['Name']} | {row['Status']}"
            ).add_to(m1)

        map_resp = st_folium(m1, width="100%", height=500, key=render_key, returned_objects=["last_clicked"])
        if map_resp and map_resp.get("last_clicked"):
            st.session_state.lat = map_resp["last_clicked"]["lat"]
            st.session_state.lon = map_resp["last_clicked"]["lng"]
            st.cache_data.clear()
            st.rerun()

        st.dataframe(
            df_main[["Name", "Status", "Rating", "Rating_Count", "Cuisine_Details", "Wolt Link"]],
            use_container_width=True,
            hide_index=True,
            column_config={"Wolt Link": st.column_config.LinkColumn("Link")}
        )

        with st.expander("🗂️ Debug — API info"):
            if 'debug_sections' in st.session_state:
                st.json(st.session_state['debug_sections'])
            if 'raw_api_debug' in st.session_state:
                st.json(st.session_state['raw_api_debug'])

# --- TAB 2: MARKET ANALYSIS ---
with tab2:
    if df_main.empty:
        st.error("❌ Podaci nisu učitani.")
    else:
        flat_cats = [item for sublist in df_main['Cuisine_Raw'] for item in sublist if item]
        unique_cats = sorted(list(set(flat_cats)))

        if not unique_cats:
            st.warning("⚠️ Nema podataka o kuhinjama.")
            st.dataframe(df_main[["Name", "Cuisine_Raw", "Cuisine_Details"]].head(10), use_container_width=True)
        else:
            selection = st.selectbox("🍽️ Filter by Cuisine:", ["All"] + unique_cats)

            df_f = df_main
            if selection != "All":
                df_f = df_main[df_main['Cuisine_Raw'].apply(
                    lambda x: selection in x if isinstance(x, list) else False
                )]

            col1, col2, col3 = st.columns(3)
            col1.metric("🏪 Ukupno restorana", len(df_f))
            col2.metric("🟢 Otvoreni", len(df_f[df_f['Online'] == True]))
            col3.metric("🔴 Zatvoreni", len(df_f[df_f['Online'] == False]))

            map2_hash = df_hash(df_f)
            m2 = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=14)
            for _, row in df_f.iterrows():
                color = "green" if row['Online'] else "red"
                folium.CircleMarker(
                    [row['Lat'], row['Lon']], radius=8, color=color, fill=True,
                    tooltip=f"{row['Name']} | {row['Cuisine_Details']}"
                ).add_to(m2)
            st_folium(m2, width="100%", height=500, key=f"m2_{map2_hash}_{selection}", returned_objects=[])

            st.subheader(f"📋 Restorani ({len(df_f)})")
            st.dataframe(
                df_f[["Name", "Status", "Rating", "Rating_Count", "Cuisine_Details", "Wolt Link"]],
                use_container_width=True,
                hide_index=True,
                column_config={"Wolt Link": st.column_config.LinkColumn("Link")}
            )

            if selection == "All" and flat_cats:
                st.subheader("📊 Distribucija kuhinja")
                from collections import Counter
                cuisine_counts = Counter(flat_cats)
                cuisine_df = pd.DataFrame(
                    cuisine_counts.items(), columns=["Kuhinja", "Broj restorana"]
                ).sort_values("Broj restorana", ascending=False).head(20)
                fig = px.bar(cuisine_df, x="Kuhinja", y="Broj restorana",
                             color="Broj restorana", color_continuous_scale="Blues")
                fig.update_layout(showlegend=False, height=400)
                st.plotly_chart(fig, use_container_width=True)

# --- TAB 3: TRAFFIC TRACKER ---
with tab3:
    st.title("📈 Traffic Tracker")

    if df_raw.empty:
        st.error("❌ Nema podataka za prikaz.")
    else:
        h = load_history(city_name)
        unique_timestamps = sorted(h['timestamp'].unique()) if not h.empty else []
        num_scans = len(unique_timestamps)

        if num_scans <= 1:
            ts_label = unique_timestamps[0].strftime('%d.%m.%Y u %H:%M:%S') if num_scans == 1 else "upravo sada"
            st.info(f"📋 **Ovo je prvi scan** — {ts_label}.")

            display_df = df_raw[["Name", "Rating_Count", "Rating", "Online", "Cuisine_Details"]].copy()
            display_df = display_df.rename(columns={
                "Name": "Restoran", "Rating_Count": "Broj ocena",
                "Rating": "Ocena", "Online": "Status", "Cuisine_Details": "Kuhinja"
            })
            display_df["Status"] = display_df["Status"].apply(lambda x: "🟢 Otvoren" if x else "🔴 Zatvoren")
            display_df = display_df.sort_values("Broj ocena", ascending=False)
            st.dataframe(display_df, use_container_width=True, hide_index=True)

        else:
            prev_ts = unique_timestamps[-1]
            curr_ts = datetime.datetime.now(local_tz)

            df_prev = h[h['timestamp'] == prev_ts][["Name", "Rating_Count"]].copy()
            df_prev = df_prev.rename(columns={"Rating_Count": "Ocene_pre"})

            df_curr = df_raw[["Name", "Rating_Count", "Rating", "Online", "Cuisine_Details"]].copy()
            df_curr = df_curr.rename(columns={"Rating_Count": "Ocene_sada"})

            merged = pd.merge(df_curr, df_prev, on="Name", how="left")
            merged["Ocene_pre"] = merged["Ocene_pre"].fillna(0).astype(int)
            merged["Ocene_sada"] = merged["Ocene_sada"].fillna(0).astype(int)
            merged["Δ Ocena"] = merged["Ocene_sada"] - merged["Ocene_pre"]
            merged["Est. narudžbi"] = merged["Δ Ocena"] * 10

            new_restaurants = merged[merged["Ocene_pre"] == 0]["Name"].tolist()
            total_new_orders = int(merged[merged["Δ Ocena"] > 0]["Est. narudžbi"].sum())
            active_count = int((merged["Δ Ocena"] > 0).sum())

            col1, col2, col3, col4 = st.columns(4)
            col1.metric("🕐 Prethodni scan", prev_ts.strftime('%d.%m. %H:%M'))
            col2.metric("🕐 Trenutni scan", curr_ts.strftime('%d.%m. %H:%M'))
            col3.metric("📦 Est. novih narudžbi", total_new_orders)
            col4.metric("🔥 Aktivnih restorana", active_count)

            st.divider()

            display = merged[[
                "Name", "Online", "Cuisine_Details",
                "Ocene_pre", "Ocene_sada", "Δ Ocena", "Est. narudžbi"
            ]].copy()
            display = display.rename(columns={
                "Name": "Restoran", "Online": "Status", "Cuisine_Details": "Kuhinja",
                "Ocene_pre": f"Ocene ({prev_ts.strftime('%H:%M')})",
                "Ocene_sada": f"Ocene ({curr_ts.strftime('%H:%M')})",
            })
            display["Status"] = display["Status"].apply(lambda x: "🟢" if x else "🔴")

            st.dataframe(
                display.sort_values("Δ Ocena", ascending=False),
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Δ Ocena": st.column_config.NumberColumn("Δ Ocena", format="%+d"),
                    "Est. narudžbi": st.column_config.NumberColumn("Est. narudžbi", format="%+d"),
                }
            )

            if new_restaurants:
                st.info(
                    f"🆕 **Novi restorani od poslednjeg scana:** {', '.join(new_restaurants[:10])}" +
                    (f" i još {len(new_restaurants)-10}" if len(new_restaurants) > 10 else "")
                )

            st.divider()
            if st.button("💾 Preuzmi istoriju kao CSV"):
                full_h = load_history(city_name)
                csv_data = full_h.to_csv(index=False).encode('utf-8')
                st.download_button("⬇️ Preuzmi radar_history.csv", csv_data, "radar_history.csv", "text/csv")

# --- TAB 4: RATING HISTORY (GOOGLE SHEETS) ---
with tab4:
    st.title("📊 Rating History — Google Sheets")

    if not gsheets_configured():
        st.error("❌ Google Sheets nije konfigurisan.")
        st.markdown("""
        ### Kako podesiti Google Sheets integraciju:

        **1. Kreiraj Google Service Account**
        - Idi na [Google Cloud Console](https://console.cloud.google.com/)
        - Kreiraj novi projekat (ili koristi postojeći)
        - Omogući **Google Sheets API** i **Google Drive API**
        - Idi na *IAM & Admin → Service Accounts → Create*
        - Preuzmi JSON ključ (Download JSON)

        **2. Kreiraj Google Sheet**
        - Napravi novi spreadsheet na [sheets.google.com](https://sheets.google.com)
        - Podijeli sheet sa email adresom service accounta (kao Editor)
        - Kopiraj Sheet ID iz URL-a (dio između `/d/` i `/edit`)

        **3. Dodaj secrets u `.streamlit/secrets.toml`**
        ```toml
        [gcp_service_account]
        type = "service_account"
        project_id = "tvoj-project-id"
        private_key_id = "abc123..."
        private_key = "-----BEGIN RSA PRIVATE KEY-----\\nMIIE...\\n-----END RSA PRIVATE KEY-----\\n"
        client_email = "ime@project.iam.gserviceaccount.com"
        client_id = "123456789"
        auth_uri = "https://accounts.google.com/o/oauth2/auth"
        token_uri = "https://oauth2.googleapis.com/token"

        [google_sheets]
        spreadsheet_id = "1AbCdEfGhIjKlMnOpQrStUvWxYz"
        ```

        **4. Restartuj app** — podaci će se automatski snimati svaki sat.
        """)
    else:
        # Ručno snimanje
        col_gs1, col_gs2 = st.columns([3, 1])
        with col_gs2:
            if st.button("💾 Snimi snapshot sada", use_container_width=True):
                if not df_raw.empty:
                    with st.spinner("Snimam u Google Sheets..."):
                        ok, msg = save_to_gsheets(df_raw, city_name)
                        if ok:
                            st.success(msg)
                            load_from_gsheets.clear()
                        else:
                            st.error(msg)
                else:
                    st.warning("Nema podataka za snimanje.")

            if st.button("🔄 Osvježi historiju", use_container_width=True):
                load_from_gsheets.clear()
                st.rerun()

        # Ucitaj historiju
        with st.spinner("Učitavam historiju iz Google Sheets..."):
            gs_history = load_from_gsheets(city_name)

        if gs_history.empty:
            st.info("📭 Nema podataka u Google Sheets za ovaj grad. Pritisni 'Snimi snapshot sada' da počneš prikupljati podatke.")
        else:
            # Agregacija po danu
            gs_history['date'] = gs_history['timestamp'].dt.date

            # --- Metrički pregled ---
            first_date = gs_history['date'].min()
            last_date = gs_history['date'].max()
            unique_days = gs_history['date'].nunique()
            total_records = len(gs_history)

            cm1, cm2, cm3, cm4 = st.columns(4)
            cm1.metric("📅 Praćenje od", str(first_date))
            cm2.metric("📅 Posljednji dan", str(last_date))
            cm3.metric("📆 Broj dana", unique_days)
            cm4.metric("📝 Ukupno zapisa", total_records)

            st.divider()

            # --- Filter restorana ---
            all_restaurants = sorted(gs_history['Name'].unique().tolist())
            
            col_f1, col_f2 = st.columns([3, 1])
            with col_f1:
                selected_restaurants = st.multiselect(
                    "🏪 Odaberi restorane za prikaz:",
                    options=all_restaurants,
                    default=all_restaurants[:10] if len(all_restaurants) >= 10 else all_restaurants,
                    help="Odaberi max 20 restorana za čitljiv graf"
                )
            with col_f2:
                metric_choice = st.selectbox("📊 Metrika:", ["Rating_Count (ocjene)", "Est. narudžbe (×10)"])

            if not selected_restaurants:
                st.warning("Odaberi bar jedan restoran.")
            else:
                # Filter podataka
                df_filtered = gs_history[gs_history['Name'].isin(selected_restaurants)].copy()

                # Dnevni prosjek po restoranu
                daily_avg = df_filtered.groupby(['date', 'Name'])['Rating_Count'].mean().reset_index()
                daily_avg.columns = ['Datum', 'Restoran', 'Ocjena_Count']
                daily_avg['Datum'] = pd.to_datetime(daily_avg['Datum'])
                daily_avg = daily_avg.sort_values('Datum')

                if metric_choice == "Est. narudžbe (×10)":
                    # Dnevni delta (rast) = est. narudžbe
                    daily_avg['Vrijednost'] = daily_avg.groupby('Restoran')['Ocjena_Count'].diff().fillna(0) * 10
                    y_label = "Procijenjene narudžbe"
                    chart_title = "📦 Procijenjene dnevne narudžbe po restoranu"
                else:
                    daily_avg['Vrijednost'] = daily_avg['Ocjena_Count']
                    y_label = "Ukupan broj ocjena"
                    chart_title = "⭐ Kumulativni broj ocjena po restoranu"

                # --- LINE CHART: Rast po danima ---
                st.subheader(chart_title)
                fig_line = px.line(
                    daily_avg,
                    x='Datum',
                    y='Vrijednost',
                    color='Restoran',
                    markers=True,
                    labels={'Vrijednost': y_label, 'Datum': 'Datum'},
                    height=500
                )
                fig_line.update_layout(
                    legend=dict(orientation="v", yanchor="top", y=1, xanchor="left", x=1.01),
                    hovermode="x unified"
                )
                st.plotly_chart(fig_line, use_container_width=True)

                st.divider()

                # --- BAR CHART: Top restorani po ukupnom rastu ---
                st.subheader("🏆 Top restorani — ukupni rast ocjena (cijeli period)")
                
                pivot = gs_history[gs_history['Name'].isin(selected_restaurants)].copy()
                pivot_agg = pivot.groupby('Name').agg(
                    min_count=('Rating_Count', 'min'),
                    max_count=('Rating_Count', 'max'),
                ).reset_index()
                pivot_agg['Rast_ocjena'] = pivot_agg['max_count'] - pivot_agg['min_count']
                pivot_agg['Est_narudzbi'] = pivot_agg['Rast_ocjena'] * 10
                pivot_agg = pivot_agg.sort_values('Est_narudzbi', ascending=False)

                fig_bar = px.bar(
                    pivot_agg,
                    x='Name',
                    y='Est_narudzbi',
                    color='Est_narudzbi',
                    color_continuous_scale='Viridis',
                    labels={'Name': 'Restoran', 'Est_narudzbi': 'Est. narudžbe'},
                    height=450,
                    text='Est_narudzbi'
                )
                fig_bar.update_traces(texttemplate='%{text:,}', textposition='outside')
                fig_bar.update_layout(showlegend=False, xaxis_tickangle=-35)
                st.plotly_chart(fig_bar, use_container_width=True)

                st.divider()

                # --- HEATMAP: Aktivnost po danu u tjednu i satu ---
                st.subheader("🗓️ Heatmap — aktivnost po danu i satu")
                
                df_heat = gs_history.copy()
                df_heat['hour'] = df_heat['timestamp'].dt.hour
                df_heat['weekday'] = df_heat['timestamp'].dt.day_name()
                weekday_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
                
                heat_data = df_heat.groupby(['weekday', 'hour'])['Rating_Count'].sum().reset_index()
                heat_pivot = heat_data.pivot(index='weekday', columns='hour', values='Rating_Count').fillna(0)
                heat_pivot = heat_pivot.reindex([d for d in weekday_order if d in heat_pivot.index])

                fig_heat = px.imshow(
                    heat_pivot,
                    labels=dict(x="Sat u danu", y="Dan u tjednu", color="Σ ocjena"),
                    color_continuous_scale="YlOrRd",
                    aspect="auto",
                    height=350
                )
                fig_heat.update_layout(xaxis=dict(tickmode='linear', tick0=0, dtick=1))
                st.plotly_chart(fig_heat, use_container_width=True)

                st.divider()

                # --- RAW DATA ---
                with st.expander("📋 Sirovi podaci iz Google Sheets"):
                    st.dataframe(
                        gs_history[gs_history['Name'].isin(selected_restaurants)]
                        .sort_values(['Name', 'timestamp'], ascending=[True, False]),
                        use_container_width=True,
                        hide_index=True
                    )

                    csv_export = gs_history.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        "⬇️ Export sve podatke kao CSV",
                        csv_export,
                        f"wolt_history_{city_name}_{datetime.date.today()}.csv",
                        "text/csv"
                    )

# --- TAB 5: SERVICE CLOUD ---
with tab5:
    m4 = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=13, tiles="cartodbpositron")
    df_a = df_main[df_main['Online'] == True] if not df_main.empty else pd.DataFrame()

    if not df_a.empty:
        pts = [[row['Lat'], row['Lon'], 1.0] for _, row in df_a.iterrows()]
        inverted_gradient = {
            0.2: '#FF0000',
            0.4: '#FF8C00',
            0.6: '#FFFF00',
            0.8: '#00FF00',
            1.0: '#0000FF'
        }
        HeatMap(pts, radius=45, blur=30, gradient=inverted_gradient).add_to(m4)

    heatmap_hash = df_hash(df_a) if not df_a.empty else "empty"
    folium_static(m4, width=1400, height=800)
