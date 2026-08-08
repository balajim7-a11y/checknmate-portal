import streamlit as st
from sqlalchemy import text

st.title("Check N Mate - Fee Dashboard")

# Establish connection
conn = st.connection("postgresql", type="sql")

try:
    # 1. Fetch the data (disabled cache for real-time updates)
    students_df = conn.query("SELECT student_id, full_name, parent_phone, fee_status, due_date FROM Students ORDER BY student_id;", ttl=0)
    
    st.write("Modify the **Fee Status** below and click Save.")

    # 2. Render the interactive data editor
    edited_df = st.data_editor(
        students_df,
        column_config={
            "student_id": st.column_config.NumberColumn("ID", disabled=True),
            "full_name": st.column_config.TextColumn("Student Name", disabled=True),
            "parent_phone": st.column_config.TextColumn("Phone", disabled=True),
            "due_date": st.column_config.DateColumn("Due Date", disabled=True),
            "fee_status": st.column_config.SelectboxColumn(
                "Fee Status",
                help="Select the current payment status",
                options=["Paid", "Unpaid", "Overdue"],
                required=True
            )
        },
        hide_index=True,
        use_container_width=True
    )

    # 3. Save button to write changes back to Neon Postgres
    if st.button("Save Changes", type="primary"):
        with conn.session as s:
            # Loop through the dataframe and update the database
            for index, row in edited_df.iterrows():
                s.execute(
                    text("UPDATE Students SET fee_status = :status WHERE student_id = :id;"),
                    {"status": row['fee_status'], "id": row['student_id']}
                )
            s.commit() # Lock in the transaction
            
        st.success("Database successfully updated!")
        st.rerun() # Refresh the page to show new state

except Exception as e:
    st.error(f"System Error: {e}")
