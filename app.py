import streamlit as st
import streamlit_authenticator as stauth
import yaml
from yaml.loader import SafeLoader
import requests
import pandas as pd
import os
import bcrypt
from datetime import date

# ---------------------------------------------------------
# Configuration & Constants
# ---------------------------------------------------------
CSV_FILE = "mileage_log.csv"
CONFIG_FILE = "config.yaml"
MILEAGE_RATE = 0.45

PURPOSE_OPTIONS = [
    "Statutory Home Visit",
    "School Visit",
    "Family Time",
    "Multi-Agency Meeting",
    "Child / Family Review",
    "Office / Administrative Travel",
    "Training / CPD",
    "Group work commute",
    "Other"
]

# ---------------------------------------------------------
# Authentication Setup
# ---------------------------------------------------------
with open(CONFIG_FILE) as f:
    config = yaml.load(f, Loader=SafeLoader)

authenticator = stauth.Authenticate(
    config["credentials"],
    config["cookie"]["name"],
    config["cookie"]["key"],
    config["cookie"]["expiry_days"],
)

st.set_page_config(page_title="Outreach Mileage Tracker", page_icon="🚗", layout="centered")

authenticator.login(location="main")

auth_status = st.session_state.get("authentication_status")

if auth_status is False:
    st.error("Username or password is incorrect.")
    st.stop()
elif auth_status is None:
    st.warning("Please log in to continue.")
    st.stop()

# Authenticated Session Variables
username = st.session_state["username"]
display_name = st.session_state["name"]
user_role = config["credentials"]["usernames"].get(username, {}).get("role", "staff")
is_admin = user_role == "admin"

# ---------------------------------------------------------
# Sidebar: User Profile, Password Reset & Admin Panel
# ---------------------------------------------------------
with st.sidebar:
    st.write(f"Logged in as **{display_name}**")
    st.caption(f"Role: {user_role}")
    authenticator.logout("Log out", location="sidebar")

    st.markdown("---")

    # 1. Password Reset (Available to all logged-in staff)
    with st.expander("🔒 Change My Password"):
        try:
            if authenticator.reset_password(username):
                with open(CONFIG_FILE, "w") as f:
                    yaml.dump(config, f, default_flow_style=False)
                st.success("Password updated successfully!")
        except Exception as e:
            st.error(f"Error: {e}")

    # 2. Admin User Management (Add new staff accounts directly from UI)
    if is_admin:
        with st.expander("👥 Admin: Add Staff User"):
            with st.form("admin_create_user_form", clear_on_submit=True):
                new_user = st.text_input("Username (e.g. jsmith)").strip().lower()
                new_name = st.text_input("Full Name (e.g. Jane Smith)").strip()
                new_mail = st.text_input("Work Email").strip()
                new_role = st.selectbox("Role", options=["staff", "admin"])
                temp_pw = st.text_input("Temporary Password", type="password")
                add_clicked = st.form_submit_button("Create Account")

                if add_clicked:
                    if not new_user or not new_name or not temp_pw:
                        st.error("Please fill in username, name, and temporary password.")
                    elif new_user in config["credentials"]["usernames"]:
                        st.error(f"User '{new_user}' already exists.")
                    else:
                        # Direct bcrypt hash generation
                        hashed = bcrypt.hashpw(temp_pw.encode(), bcrypt.gensalt()).decode()
                        config["credentials"]["usernames"][new_user] = {
                            "name": new_name,
                            "email": new_mail,
                            "password": hashed,
                            "role": new_role
                        }
                        with open(CONFIG_FILE, "w") as f:
                            yaml.dump(config, f, default_flow_style=False)
                        st.success(f"Account for **{new_name}** (`{new_user}`) created!")

# ---------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------
def get_coords(postcode):
    try:
        clean_pc = postcode.replace(" ", "").upper()
        res = requests.get(f"https://api.postcodes.io/postcodes/{clean_pc}", timeout=5).json()
        if res.get("status") == 200:
            return res["result"]["latitude"], res["result"]["longitude"]
    except Exception:
        pass
    return None

def get_driving_miles(start_coords, end_coords):
    url = (
        f"https://router.project-osrm.org/route/v1/driving/"
        f"{start_coords[1]},{start_coords[0]};{end_coords[1]},{end_coords[0]}"
        f"?overview=false"
    )
    try:
        res = requests.get(url, timeout=5).json()
        if res.get("routes"):
            meters = res["routes"][0]["distance"]
            return round(meters * 0.000621371, 2)
    except Exception:
        pass
    return None

# ---------------------------------------------------------
# Page Setup & Input Form
# ---------------------------------------------------------
st.title("🚗 Outreach Mileage Tracker")

with st.form("mileage_form"):
    col1, col2 = st.columns(2)
    with col1:
        trip_date = st.date_input("Date of Journey", value=date.today())
        start_pc = st.text_input("Start Postcode", placeholder="e.g. PR25 2DY")
    with col2:
        st.text_input("Staff", value=display_name, disabled=True)
        end_pc = st.text_input("Destination Postcode", placeholder="e.g. PR1 8XJ")

    col3, col4 = st.columns([2, 1])
    with col3:
        purpose_choice = st.selectbox("Trip Purpose", options=PURPOSE_OPTIONS)
    with col4:
        st.write("")
        is_return = st.checkbox("Return Journey (x2)", value=False)

    custom_notes = st.text_input("Optional Case Ref / Notes", placeholder="e.g. Review meeting")
    submitted = st.form_submit_button("Calculate & Log Trip")

# ---------------------------------------------------------
# Submission Logic
# ---------------------------------------------------------
if submitted:
    clean_start = start_pc.strip().upper()
    clean_end = end_pc.strip().upper()

    if not clean_start or not clean_end:
        st.error("Please provide both valid postcodes.")
    else:
        with st.spinner("Calculating driving route..."):
            start_ll = get_coords(clean_start)
            end_ll = get_coords(clean_end)

            if start_ll is None or end_ll is None:
                st.error("Could not find coordinates for one or both postcodes. Please verify the format.")
            else:
                base_miles = get_driving_miles(start_ll, end_ll)
                if base_miles is None:
                    st.error("Could not find a valid driving route between these two locations.")
                else:
                    total_miles = round(base_miles * 2, 2) if is_return else base_miles
                    claim_amount = round(total_miles * MILEAGE_RATE, 2)

                    full_purpose = f"{purpose_choice} - {custom_notes}".strip(" -")
                    journey_type = "Return" if is_return else "One-way"

                    st.success(f"Distance: **{total_miles} miles** ({journey_type}) — Claim: **£{claim_amount:.2f}**")

                    new_entry = pd.DataFrame([{
                        "Date": str(trip_date),
                        "Username": username,
                        "Staff": display_name,
                        "Start Postcode": clean_start,
                        "Destination Postcode": clean_end,
                        "Miles": total_miles,
                        "Claim Amount (£)": claim_amount,
                        "Purpose": full_purpose,
                        "Month": trip_date.strftime("%Y-%m"),
                        "Type": journey_type
                    }])

                    # Align with existing CSV header order
                    if os.path.isfile(CSV_FILE):
                        existing_cols = pd.read_csv(CSV_FILE, nrows=0).columns.tolist()
                        for col in existing_cols:
                            if col not in new_entry.columns:
                                new_entry[col] = ""
                        new_entry = new_entry[existing_cols]
                        new_entry.to_csv(CSV_FILE, mode="a", index=False, header=False)
                    else:
                        new_entry.to_csv(CSV_FILE, mode="w", index=False, header=True)

                    st.toast("Trip logged successfully!", icon="✅")
                    st.session_state.show_undo = True

# ---------------------------------------------------------
# Undo Last Submission — scoped to the logged-in user
# ---------------------------------------------------------
if st.session_state.get("show_undo", False):
    col_undo, _ = st.columns([2, 3])
    with col_undo:
        if st.button("↩️ Made a mistake? Undo my last logged trip"):
            if os.path.isfile(CSV_FILE):
                df_current = pd.read_csv(CSV_FILE)
                user_rows = df_current[df_current["Username"] == username]
                if not user_rows.empty:
                    last_idx = user_rows.index[-1]
                    df_current = df_current.drop(index=last_idx).reset_index(drop=True)
                    df_current.to_csv(CSV_FILE, index=False)

                    st.session_state.show_undo = False
                    st.warning("Your last entry was removed. You can now re-enter your trip.")
                    st.rerun()
                else:
                    st.info("No trips found to undo for your account.")

# ---------------------------------------------------------
# Log Viewer, Reconciliation & Downloads
# ---------------------------------------------------------
st.markdown("---")

if os.path.isfile(CSV_FILE):
    df = pd.read_csv(CSV_FILE)

    # Backfill Username for any legacy rows so old data doesn't vanish for admins
    if "Username" not in df.columns:
        df["Username"] = ""

    # 1. Clean and force numeric types
    if "Miles" in df.columns:
        df["Miles"] = pd.to_numeric(df["Miles"], errors="coerce").fillna(0.0)

    if "Claim Amount (£)" in df.columns:
        if df["Claim Amount (£)"].dtype == object:
            df["Claim Amount (£)"] = df["Claim Amount (£)"].astype(str).str.replace("£", "", regex=False)
        df["Claim Amount (£)"] = pd.to_numeric(df["Claim Amount (£)"], errors="coerce").fillna(0.0)

    # 2. Automatic Data Healing for legacy logs
    if "Month" not in df.columns and "Date" in df.columns:
        df["Month"] = pd.to_datetime(df["Date"]).dt.strftime("%Y-%m")
        df.to_csv(CSV_FILE, index=False)

    if "Claim Amount (£)" not in df.columns and "Miles" in df.columns:
        df["Claim Amount (£)"] = (df["Miles"] * MILEAGE_RATE).round(2)
        df.to_csv(CSV_FILE, index=False)

    if "Type" not in df.columns:
        df["Type"] = "One-way"
        df.to_csv(CSV_FILE, index=False)

    # Access control: staff only ever see their own rows
    if not is_admin:
        df = df[df["Username"] == username]

    tab1, tab2 = st.tabs(["Oracle Fusion Monthly Summary", "All Logged Trips"])

    # High-contrast CSS
    table_css = """
    <style>
      .custom-table {
        width: 100%;
        border-collapse: collapse;
        margin: 1rem 0;
        font-size: 0.95rem;
        font-family: inherit;
        border-radius: 8px;
        overflow: hidden;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
      }
      .custom-table thead tr {
        background-color: #f0f2f6;
        color: #1f2937 !important;
        text-align: left;
        font-weight: 600;
      }
      .custom-table th, .custom-table td {
        padding: 10px 14px;
        border-bottom: 1px solid #e6e9ef;
      }
      .custom-table tbody tr {
        color: inherit !important;
      }
      .custom-table tbody tr:nth-of-type(even) {
        background-color: rgba(240, 242, 246, 0.35);
      }
      .custom-table tbody tr:hover {
        background-color: rgba(99, 102, 241, 0.12) !important;
      }
      .custom-table tbody tr:hover td {
        color: inherit !important;
      }
    </style>
    """
    st.markdown(table_css, unsafe_allow_html=True)

    # TAB 1: Monthly Fusion Reconciliation
    with tab1:
        st.subheader("Monthly Claim Summary")
        if is_admin:
            st.caption("Filter trips across all staff to produce the exact figure for Oracle Fusion Expenses.")
        else:
            st.caption("Your trips, ready for Oracle Fusion Expenses.")

        month_list = sorted(df["Month"].dropna().unique().tolist(), reverse=True)

        if is_admin:
            staff_list = sorted(df["Staff"].dropna().unique().tolist())
            c1, c2 = st.columns(2)
            with c1:
                sel_staff = st.selectbox("Select Staff", options=["All"] + staff_list)
            with c2:
                sel_month = st.selectbox("Select Month", options=["All"] + month_list)
        else:
            sel_staff = display_name
            sel_month = st.selectbox("Select Month", options=["All"] + month_list)

        filtered_df = df.copy()
        if is_admin and sel_staff != "All":
            filtered_df = filtered_df[filtered_df["Staff"] == sel_staff]
        if sel_month != "All":
            filtered_df = filtered_df[filtered_df["Month"] == sel_month]

        f_miles = round(filtered_df["Miles"].sum(), 2)
        f_claim = round(filtered_df["Claim Amount (£)"].sum(), 2)
        f_trips = len(filtered_df)

        m1, m2, m3 = st.columns(3)
        m1.metric("Total Trips", f"{f_trips}")
        m2.metric("Total Miles", f"{f_miles} mi")
        m3.metric("Fusion Claim Total", f"£{f_claim:.2f}")

        # Aggregated table
        summary_df = filtered_df.groupby("Staff", as_index=False).agg(
            Trips=("Miles", "count"),
            Total_Miles=("Miles", "sum"),
            Total_Reimbursement_GBP=("Claim Amount (£)", "sum")
        )
        summary_df["Total_Miles"] = summary_df["Total_Miles"].round(2)
        summary_df["Total_Reimbursement_GBP"] = summary_df["Total_Reimbursement_GBP"].apply(lambda x: f"£{x:.2f}")
        summary_df = summary_df.rename(columns={
            "Total_Miles": "Total Miles",
            "Total_Reimbursement_GBP": "Total Reimbursement (£)"
        })

        st.markdown(summary_df.to_html(classes="custom-table", index=False, escape=True), unsafe_allow_html=True)

        st.download_button(
            label="📄 Download Fusion Evidence Schedule (CSV)",
            data=filtered_df.to_csv(index=False).encode("utf-8"),
            file_name=f"fusion_evidence_{sel_staff}_{sel_month}.csv",
            mime="text/csv"
        )

    # TAB 2: Itemised Log
    with tab2:
        st.subheader("All Logged Records" if is_admin else "My Logged Trips")
        display_raw = df.copy()
        display_raw["Claim Amount (£)"] = display_raw["Claim Amount (£)"].apply(lambda x: f"£{x:.2f}")
        st.markdown(display_raw.to_html(classes="custom-table", index=False, escape=True), unsafe_allow_html=True)

        st.download_button(
            label="Download Audit Log (CSV)",
            data=df.to_csv(index=False).encode("utf-8"),
            file_name="mileage_audit_log.csv",
            mime="text/csv"
        )
else:
    st.info("No trips logged yet. Fill out the form above to add your first journey.")