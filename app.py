import streamlit as st

st.title("Check N Mate - Fee Dashboard")

# Establish connection
conn = st.connection("postgresql", type="sql")

try:
    # ttl=0 completely disables the cache for testing
    students_df = conn.query("SELECT * FROM Students;", ttl=0)
    st.dataframe(students_df)
except Exception as e:
    # This will print the exact backend error to your screen
    st.error(f"System Error: {e}")
