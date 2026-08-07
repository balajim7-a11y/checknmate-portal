import streamlit as st
import pandas as pd
import streamlit_authenticator as stauth

st.set_page_config(page_title="Check N Mate Portal", layout="centered")

# --- 1. Load User Data ---
@st.cache_data
def load_users():
    return pd.read_excel("CheckNMate_DB_final.xlsx", sheet_name="Users")

users_df = load_users()

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

# --- 5. Application Gateway Logic ---
if st.session_state.get("authentication_status"):
    authenticator.logout("Logout", "sidebar")
    st.write(f'Welcome to the portal, **{st.session_state["name"]}**!')
    st.success("✅ Login successful! The instructor dashboard will go here in Step 3.")
    
elif st.session_state.get("authentication_status") is False:
    st.error("Username/password is incorrect. (Make sure you updated your Excel file with real hashes!)")
elif st.session_state.get("authentication_status") is None:
    st.info("Please enter your username and password.")

# --- TEMPORARY UTILITY: HASH GENERATOR ---
st.divider()
st.subheader("🛠️ Admin Utility: Password Hasher")
st.write("Enter a plain-text password below to generate a secure hash. Copy the result and paste it into your Excel file.")
raw_password = st.text_input("Enter a test password (e.g., chess123):")
if raw_password:
    # Generate the secure hash for the inputted password
    hashed_password = stauth.Hasher([raw_password]).generate()[0]
    st.code(hashed_password)
