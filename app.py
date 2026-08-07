import streamlit as st
import pandas as pd
import streamlit_authenticator as stauth
from datetime import date

st.set_page_config(page_title="Check N Mate Portal", layout="centered")

# --- 1. Load All Required Data ---
@st.cache_data
def load_data():
    # We now need to load THREE tabs instead of just one
    xls = pd.ExcelFile("CheckNMate_DB_final.xlsx")
    users_df = pd.read_excel(xls, sheet_name="Users")
    franchises_df = pd.read_excel(xls, sheet_name="Franchises")
    students_df = pd.read_excel(xls, sheet_name="Students")
    return users_df, franchises_df, students_df

users_df, franchises_df, students_df = load_data()

# --- 2. Format Credentials ---
credentials = {"usernames": {}}
for index, row in users_df.iterrows():
    credentials["usernames"][row["Username"]] = {
        "name": row["Full_Name"],
        "password": str(row["Hashed_Password"]), 
        "email": f"{row['Username']}@example.com",
    }

# --- 3. Initialize Authenticator ---
authenticator = stauth.Authenticate(
    credentials,
    "checknmate_cookie",      
    "random_signature_key",   
    cookie_expiry_days=30
)

# --- 4. Render Login Widget ---
st.title("♟️ Check N Mate Portal")
authenticator.login()

# --- 5. Secure Instructor Dashboard ---
if st.session_state.get("authentication_status"):
    authenticator.logout("Logout", "sidebar")
    
    # 5a. Identify the logged-in user
    username = st.session_state["username"]
    active_user = users_df[users_df["Username"] == username].iloc[0]
    assigned_franchise_id = active_user["Assigned_Franchise_ID"]
    
    st.write(f"Welcome back, **{st.session_state['name']}** ({active_user['Role']})")
    st.divider()
    
    # 5b. Match the Franchise ID to its actual Name
    franchise_name_match = franchises_df.loc[franchises_df["Franchise_ID"] == assigned_franchise_id, "Franchise_Name"].values
    display_name = franchise_name_match[0] if len(franchise_name_match) > 0 else assigned_franchise_id
    
    st.subheader("📝 Daily Class Log & Attendance")
    st.info(f"📍 **Location:** {display_name}")
    
    # 5c. Filter the student roster for this specific location
    local_students = students_df[students_df["Franchise_ID"] == assigned_franchise_id]
    
    if local_students.empty:
        st.warning("No students found for this franchise.")
    else:
        # 5d. Build the Submission Form
        with st.form("class_log_form"):
            class_date = st.date_input("Class Date", date.today())
            topics = st.text_area("Topics Covered Today", placeholder="e.g., Opening Principles...")
            
            st.markdown("### ✅ Student Roster")
            
            # Generate a checkbox for every student at this location
            attendance_status = {}
            for index, row in local_students.iterrows():
                attendance_status[row['Student_ID']] = st.checkbox(
                    f"{row['Full_Name']} ({row['Student_ID']})", 
                    value=True # Default is checked (Present)
                )
                
            submitted = st.form_submit_button("Submit Class Log")
            
            if submitted:
                if not topics:
                    st.error("Please enter the topics covered before submitting.")
                else:
                    st.success("✅ Form processed! (The code to actually save this to the database will go here in Step 4).")
                    st.write("Data captured:")
                    st.write(attendance_status)

elif st.session_state.get("authentication_status") is False:
    st.error("Username/password is incorrect.")
elif st.session_state.get("authentication_status") is None:
    st.info("Please enter your username and password.")

# --- TEMPORARY UTILITY: HASH GENERATOR ---
st.divider()
st.subheader("🛠️ Admin Utility: Password Hasher")
raw_password = st.text_input("Enter a test password (e.g., chess123):")
if raw_password:
    hashed_password = stauth.Hasher.hash(raw_password)
    st.code(hashed_password)
