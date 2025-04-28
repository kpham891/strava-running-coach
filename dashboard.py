import requests
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import json
from datetime import datetime, timedelta

# --- CONFIGURATION ---

# Path to save and load your goal settings
GOAL_FILE = "goal.json"

# Default race distances in KM
RACE_DISTANCES = {
    "5K": 5,
    "10K": 10,
    "Half Marathon": 21.0975,
    "Marathon": 42.195
}

# --- HELPER FUNCTIONS ---

def save_goal(goal_data):
    with open(GOAL_FILE, "w") as f:
        json.dump(goal_data, f)

def load_goal():
    try:
        with open(GOAL_FILE, "r") as f:
            return json.load(f)
    except:
        return None

def fetch_activities(access_token):
    url = "https://www.strava.com/api/v3/athlete/activities"
    headers = {"Authorization": f"Bearer {access_token}"}
    params = {"per_page": 50}
    response = requests.get(url, headers=headers, params=params)
    if response.status_code != 200:
        st.error(f"Failed to fetch activities from Strava (status code {response.status_code})")
        st.stop()
    return response.json()

def calculate_pace(moving_time, distance_meters):
    if distance_meters == 0:
        return 0
    pace_sec = moving_time / (distance_meters / 1000)
    return pace_sec

def seconds_to_pace(sec_per_km):
    if sec_per_km == 0 or sec_per_km == float('inf'):
        return "-"
    minutes = int(sec_per_km // 60)
    seconds = int(sec_per_km % 60)
    return f"{minutes}:{seconds:02d} min/km"

def generate_training_plan(today, race_day, runs_per_week):
    weeks_left = (race_day - today).days // 7
    plan = []
    if weeks_left < 2:
        return ["⚠️ Not enough time to generate a full training plan."]
    for week in range(weeks_left):
        week_plan = []
        if week == weeks_left - 1:
            week_plan.append("Race Week: Taper, 2 short easy runs")
        else:
            week_plan.append(f"Long Run ({10 + week * 1} to {14 + week * 1} km)")
            if runs_per_week >= 4:
                week_plan.append("Tempo Run (4-8 km at goal pace)")
            if runs_per_week >= 5:
                week_plan.append("Intervals (e.g., 4x1km faster pace)")
            week_plan.append("1–2 Easy Runs (5–8 km)")
        plan.append(week_plan)
    return plan

def ai_analyst_response(question, goal_data, recent_runs_df):
    if "pace" in question.lower():
        avg_pace = recent_runs_df["pace_sec_per_km"].mean()
        avg_pace_formatted = seconds_to_pace(avg_pace)
        return f"Your average recent pace is {avg_pace_formatted}. Target pace for your goal is {goal_data['target_pace_formatted']}."
    if "ready" in question.lower() or "close" in question.lower():
        avg_pace = recent_runs_df["pace_sec_per_km"].mean()
        if avg_pace < goal_data["target_pace_sec"]:
            return "✅ You're currently pacing faster than your goal! Maintain consistency."
        else:
            return "⚡ You're slightly behind goal pace. Focus on tempo runs and sharpening your endurance."
    if "next run" in question.lower():
        return "Recommended next run: 6–8 km easy run, or a moderate tempo run based on your energy levels."
    return "I'm a data-driven analyst. Please ask about pace, readiness, or training advice."

# --- STREAMLIT DASHBOARD START ---

st.set_page_config(page_title="AI Running Coach", page_icon="🏃‍♂️", layout="wide")

# Load previous goal if exists
goal_data = load_goal()

# --- Sidebar: Set / Update Goal ---
st.sidebar.header("🏁 Set Your Goal")

race_type = st.sidebar.selectbox("Race Type:", ["5K", "10K", "Half Marathon", "Marathon"], 
                                 index=["5K", "10K", "Half Marathon", "Marathon"].index(goal_data["race_type"]) if goal_data else 2)

target_time_str = st.sidebar.text_input("Target Time (hh:mm:ss):", goal_data["target_time"] if goal_data else "1:45:00")

race_date = st.sidebar.date_input("Race Date:", 
                                  datetime.strptime(goal_data["race_date"], "%Y-%m-%d").date() if goal_data else datetime.today().date() + timedelta(days=30))

runs_per_week = st.sidebar.selectbox("Runs per Week:", [3, 4, 5, 6], 
                                     index=[3, 4, 5, 6].index(goal_data["runs_per_week"]) if goal_data else 1)

# Parse target pace
try:
    t = datetime.strptime(target_time_str, "%H:%M:%S")
    total_seconds = t.hour * 3600 + t.minute * 60 + t.second
    race_distance_km = RACE_DISTANCES[race_type]
    target_pace_sec = total_seconds / race_distance_km
    target_pace_formatted = seconds_to_pace(target_pace_sec)
except:
    target_pace_sec = None
    target_pace_formatted = "Invalid format!"

# Save updated goal
current_goal_data = {
    "race_type": race_type,
    "target_time": target_time_str,
    "race_date": str(race_date),
    "runs_per_week": runs_per_week,
    "target_pace_sec": target_pace_sec,
    "target_pace_formatted": target_pace_formatted
}
save_goal(current_goal_data)

# --- Main Section ---

st.title("🏃 AI Running Coach Dashboard")

# Read access token from Streamlit secrets
access_token = st.secrets["access_token"]


# Fetch and prepare runs
activities = fetch_activities(access_token)
runs = [act for act in activities if act.get("type") == "Run"]

if not runs:
    st.warning("No recent running activities found.")
    st.stop()

# Prepare dataframe
data = []
for act in runs:
    dist_km = act["distance"] / 1000
    pace_sec_per_km = calculate_pace(act["moving_time"], act["distance"])
    data.append({
        "name": act["name"],
        "date": act["start_date_local"][:10],
        "distance_km": dist_km,
        "moving_time_min": act["moving_time"] / 60,
        "pace_sec_per_km": pace_sec_per_km
    })

df = pd.DataFrame(data)

# --- Section: Recent Runs Table ---
st.subheader("📄 Recent Runs")
st.dataframe(df[["name", "date", "distance_km", "moving_time_min"]].rename(columns={
    "name": "Name",
    "date": "Date",
    "distance_km": "Distance (km)",
    "moving_time_min": "Time (min)"
}), hide_index=True)

# --- Section: Moving Average Pace Over Last 12 Weeks ---
st.subheader("📈 Pace Trend Over Last 12 Weeks")

# Prepare dates and weeks
df["date_obj"] = pd.to_datetime(df["date"])
df["week"] = df["date_obj"].dt.isocalendar().week
df["year"] = df["date_obj"].dt.isocalendar().year

# Group by week
weekly_pace = df.groupby(["year", "week"]).agg({"pace_sec_per_km": "mean"}).reset_index()

# Only keep last 12 weeks
today = datetime.today()
current_year = today.isocalendar().year
current_week = today.isocalendar().week

# Filter: within last 12 weeks
weekly_pace = weekly_pace[
    (weekly_pace["year"] == current_year) & 
    (weekly_pace["week"] >= current_week - 12)
]

# Convert seconds to min/km
weekly_pace["pace_min_per_km"] = weekly_pace["pace_sec_per_km"] / 60

# --- Plot ---
fig, ax = plt.subplots()
ax.plot(weekly_pace["week"], weekly_pace["pace_min_per_km"], marker='o', linestyle='-', label='Weekly Avg Pace')
ax.axhline(y=current_goal_data["target_pace_sec"]/60, color='red', linestyle='--', label=f'Target Pace ({current_goal_data["target_pace_formatted"]})')

ax.set_xlabel("Week Number")
ax.set_ylabel("Average Pace (min/km)")
ax.set_title("Weekly Average Pace vs Target Pace")
ax.grid(True)
ax.invert_yaxis()
ax.legend()

st.pyplot(fig)


# --- Section: Training Load Progress ---
long_runs = df[df["distance_km"] > 10]
completed_long_runs = long_runs.shape[0]
weeks_to_race = (datetime.strptime(current_goal_data["race_date"], "%Y-%m-%d").date() - datetime.today().date()).days // 7
expected_long_runs = max(1, weeks_to_race)
training_load = min(1.0, completed_long_runs / expected_long_runs)

st.subheader("📊 Training Load Progress")
st.progress(training_load)

# --- Section: Training Plan ---
st.subheader("🛠️ Training Plan")
today = datetime.today().date()
race_day = datetime.strptime(current_goal_data["race_date"], "%Y-%m-%d").date()
plan = generate_training_plan(today, race_day, current_goal_data["runs_per_week"])

for i, week in enumerate(plan):
    st.write(f"**Week {i+1}:**")
    for workout in week:
        st.write(f"- {workout}")

# --- Section: AI Analyst Assistant ---
st.subheader("🤖 Ask the AI Analyst")
user_question = st.text_input("Ask me about your training, pace, or readiness:")

if user_question:
    response = ai_analyst_response(user_question, current_goal_data, df)
    st.info(response)

