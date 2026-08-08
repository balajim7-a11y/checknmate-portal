import streamlit as st

st.title("Check N Mate - Fee Dashboard")

# Streamlit will securely grab the database credentials from the cloud
conn = st.connection("postgresql", type="sql")

try:
    # Query the active roster with a 10-minute cache Time-To-Live
    students_df = conn.query("SELECT * FROM Students;", ttl="10m")
    st.dataframe(students_df)
except Exception as e:
    st.warning("Database connected, but no data found. Please run the table creation scripts in Neon.")
