import streamlit as st
from sqlalchemy import text
import datetime

st.set_page_config(page_title="Check N Mate Dashboard", layout="wide")
st.title("Check N Mate - Fee Dashboard")

# Establish connection
conn = st.connection("postgresql", type="sql")

# --- SIDEBAR: ADD NEW STUDENT FORM ---
with st.sidebar:
    st.header("Add New Student")
    with st.form("add_student_form", clear_on_submit=True):
        new_name = st.text_input("Student Full Name")
        new_phone = st.text_input("Parent Phone Number")
        new_due_date = st.date_input("Fee Due Date", datetime.date.today())
        
        # Submit button for the form
        submit_button = st.form_submit_button("Add Student", type="primary")
        
        if submit_button:
            if new_name and new_phone:
                try:
                    with conn.session as s:
                        s.execute(
                            text("""
                                INSERT INTO Students (full_name, franchise_id, parent_phone, fee_status, due_date) 
                                VALUES (:name, 1, :phone, 'Unpaid', :due_date);
                            """),
                            {"name": new_name, "phone": new_phone, "due_date": new_due_date}
                        )
                        s.commit()
                    st.success(f"Added {new_name} successfully!")
                except Exception as e:
                    st.error(f"Error adding student: {e}")
            else:
                st.warning("Please fill in both name and phone number.")

# --- MAIN PAGE: ROSTER & INLINE EDITING ---
try:
    # Fetch the data
    students_df = conn.query("SELECT student_id, full_name, parent_phone, fee_status, due_date FROM Students ORDER BY student_id;", ttl=0)
    
    st.write("Modify the **Fee Status** below and click Save.")

    # Render the interactive data editor
    edited_df = st.data_editor(
        students_df,
        column_config={
            "student_id": st.column_config.NumberColumn("ID", disabled=True),
            "full_name": st.column_config.TextColumn("Student Name", disabled=True),
            "parent_phone": st.column_config.TextColumn("Phone", disabled=True),
            "due_date": st.column_config.DateColumn("Due Date", disabled=True),
            "fee_status": st.column_config.SelectboxColumn(
                "Fee Status",
                options=["Paid", "Unpaid", "Overdue"],
                required=True
            )
        },
        hide_index=True,
        use_container_width=True
    )

    # Save button for status changes
    if st.button("Save Status Changes", type="primary"):
        with conn.session as s:
            for index, row in edited_df.iterrows():
                s.execute(
                    text("UPDATE Students SET fee_status = :status WHERE student_id = :id;"),
                    {"status": row['fee_status'], "id": row['student_id']}
                )
            s.commit()
            
        st.success("Database successfully updated!")
        st.rerun()

except Exception as e:
    st.error(f"System Error: {e}")
