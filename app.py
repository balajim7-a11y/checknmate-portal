import streamlit as st
import pandas as pd

st.set_page_config(page_title="Check N Mate Portal", layout="centered")
st.title("♟️ Check N Mate Portal - System Test")

st.write("Testing the connection to the database...")

# Try to read the Excel file
try:
    # We are specifically looking for the 'Users' tab
    users_df = pd.read_excel("CheckNMate_DB_V2.xlsx", sheet_name="Users")
    
    st.success("✅ Success! The cloud server can read the Excel file.")
    
    # Display the data to prove it works
    st.write("Here is the data found in the Users tab:")
    st.dataframe(users_df)
    
except Exception as e:
    st.error(f"❌ Failed to read the Excel file. Please check that the file is named exactly 'CheckNMate_DB_V2.xlsx'.")
    st.write(f"Error details: {e}")
