import json
import time
from datetime import datetime, timedelta
import pandas as pd
import razorpay
from sqlalchemy import text
import streamlit as st
from twilio.rest import Client

# --- 1. PAGE CONFIGURATION ---
st.set_page_config(page_title="Check N Mate - Fee Portal", page_icon="♟️", layout="wide")

# --- 2. AUTHENTICATION & ROLE MANAGEMENT ---
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
    st.session_state["username"] = ""
    st.session_state["role"] = ""

def login_screen():
    st.title("🔒 Check N Mate - Secure Login")
    st.markdown("Please log in with your assigned Admin, Company, or Franchise credentials.")
    
    with st.form("login_form"):
        username_input = st.text_input("Username")
        password_input = st.text_input("Password", type="password")
        submit_login = st.form_submit_button("Login")
        
        if submit_login:
            # 1. Check if Super Admin
            if username_input.lower() == "superadmin" and password_input == st.secrets["admin_password"]:
                st.session_state["logged_in"] = True
                st.session_state["username"] = "superadmin"
                st.session_state["role"] = "Admin"
                st.rerun()
            # 2. Check if Company Admin
            elif username_input.lower() == "company" and password_input == st.secrets["company_password"]:
                st.session_state["logged_in"] = True
                st.session_state["username"] = "company"
                st.session_state["role"] = "Company"
                st.rerun()
            # 3. Check if Franchise User
            elif username_input.lower() == "franchise" and password_input == st.secrets["franchise_password"]:
                st.session_state["logged_in"] = True
                st.session_state["username"] = "franchise"
                st.session_state["role"] = "Franchise"
                st.rerun()
            else:
                st.error("😕 Invalid username or password.")

if not st.session_state["logged_in"]:
    login_screen()
    st.stop() # Halt execution if not logged in

# --- SIDEBAR: USER INFO & LOGOUT ---
with st.sidebar:
    st.markdown("### 👤 User Session")
    st.info(f"**User:** {st.session_state['username'].capitalize()}\n\n**Role:** {st.session_state['role']}")
    if st.button("🚪 Logout"):
        st.session_state["logged_in"] = False
        st.session_state["username"] = ""
        st.session_state["role"] = ""
        st.rerun()

# --- 3. DATABASE CONNECTION ---
@st.cache_resource
def init_connection():
    return st.connection("postgresql", type="sql")

conn = init_connection()

# --- 4. PAYMENT & MESSAGING ENGINE ---
def dispatch_whatsapp_payload(student_name: str, parent_phone: str, amount: float, message_type: str):
    rzp_client = razorpay.Client(auth=(st.secrets["razorpay"]["key_id"], st.secrets["razorpay"]["key_secret"]))
    twilio_client = Client(st.secrets["twilio"]["account_sid"], st.secrets["twilio"]["auth_token"])

    expiry_timestamp = int(time.time()) + (3 * 24 * 60 * 60)

    payment_link = rzp_client.payment_link.create({
        "amount": int(amount * 100),
        "currency": "INR",
        "expire_by": expiry_timestamp,
        "description": f"Fee payment for {student_name}",
        "customer": {"name": student_name, "contact": parent_phone},
        "notify": {"sms": False, "email": False}
    })
    short_url = payment_link["short_url"]

    if message_type == "upcoming":
        custom_body = f"Hi from Check N Mate! ♟️\n\nThis is a reminder that the fee of ₹{int(amount)} for {student_name} is due in 3 days.\n\nPay securely here: {short_url}\n\nThank you!"
    else:
        custom_body = f"URGENT: Hi from Check N Mate! ♟️\n\nThe fee of ₹{int(amount)} for {student_name} is currently OVERDUE.\n\nPlease complete the payment using this link: {short_url}\n\nThank you!"

    try:
        message = twilio_client.messages.create(
            body=custom_body,
            from_=st.secrets["twilio"]["sandbox_number"],
            to=f"whatsapp:{parent_phone}"
        )
        return short_url, message.sid, "Custom Message"
    except Exception as e:
        if "ContentSid Required" in str(e) or "400" in str(e):
            status_label = f"{student_name} [FEE {message_type.upper()}]"
            message = twilio_client.messages.create(
                content_sid="HXfe5ab5f00277942d4d4200328b4d403c",
                content_variables=json.dumps({"1": status_label, "2": short_url}),
                from_=st.secrets["twilio"]["sandbox_number"],
                to=f"whatsapp:{parent_phone}"
            )
            return short_url, message.sid, "Approved Template (Fallback)"
        else:
            raise e

# --- 5. UI DASHBOARD ---
st.title("♟️ Check N Mate - Admin Portal")

tab1, tab2, tab3, tab4 = st.tabs([
    "📊 Active Roster", 
    "⚙️ Run Automations", 
    "🗓️ Manage Due Dates", 
    "🧑‍🎓 Manage Students"
])

# --- TAB 1: ACTIVE ROSTER ---
with tab1:
    st.header("Student Fee Roster")
    col_a, _ = st.columns([1, 5])
    with col_a:
        if st.button("🔄 Refresh Data", use_container_width=True):
            st.cache_data.clear()
        
    try:
        df = conn.query("SELECT id, student_name, parent_phone, fee_amount, due_date, payment_status, last_updated_by FROM Students ORDER BY due_date ASC;", ttl="0m")
        st.dataframe(df, use_container_width=True, hide_index=True)
    except Exception as e:
        st.error(f"Database Error: {e}. (Make sure you have run the ALTER TABLE command in Neon to add the 'last_updated_by' column).")

# --- TAB 2: BATCH AUTOMATIONS ---
with tab2:
    st.header("Automated Messaging Engine")
    if st.button("🚀 Execute Daily Notification Batch", type="primary"):
        with st.spinner("Processing pending payments..."):
            try:
                df = conn.query("SELECT * FROM Students WHERE payment_status = 'Pending';", ttl="0m")
                if df.empty:
                    st.info("No pending payments found.")
                else:
                    df['due_date'] = pd.to_datetime(df['due_date']).dt.date
                    today = datetime.now().date()
                    
                    upcoming_students = df[df['due_date'] == today + timedelta(days=3)]
                    overdue_students = df[df['due_date'] < today]

                    if not upcoming_students.empty:
                        st.subheader(f"Upcoming Reminders ({len(upcoming_students)})")
                        for _, row in upcoming_students.iterrows():
                            link, sid, delivery_type = dispatch_whatsapp_payload(row['student_name'], row['parent_phone'], row['fee_amount'], "upcoming")
                            st.success(f"✅ Sent to **{row['student_name']}** via {delivery_type} | [Link]({link})")
                            
                    if not overdue_students.empty:
                        st.subheader(f"Overdue Notices ({len(overdue_students)})")
                        for _, row in overdue_students.iterrows():
                            link, sid, delivery_type = dispatch_whatsapp_payload(row['student_name'], row['parent_phone'], row['fee_amount'], "overdue")
                            st.warning(f"⚠️ Sent to **{row['student_name']}** via {delivery_type} | [Link]({link})")
            except Exception as e:
                st.error(f"Database batch operation failed: {e}")

# --- TAB 3: MANAGE DUE DATES (Bulk Testing) ---
with tab3:
    st.header("🗓️ Bulk Update Due Dates")
    st.info("💡 Set all records at once to test the automated rules in Tab 2.")
    
    with st.form("bulk_update_form"):
        bulk_date = st.date_input("Set Date for ALL Records")
        submit_bulk = st.form_submit_button("⚡ Apply to All Students")
        
        if submit_bulk:
            try:
                with conn.session as session:
                    session.execute(
                        text("UPDATE Students SET due_date = :bulk_date, last_updated_by = :user"),
                        {"bulk_date": bulk_date, "user": st.session_state["username"]}
                    )
                    session.commit()
                st.success(f"Successfully updated ALL records to {bulk_date}!")
                st.cache_data.clear()
            except Exception as e:
                st.error(f"Bulk update failed: {e}")

# --- TAB 4: MANAGE STUDENTS (CRUD + Audit) ---
with tab4:
    st.header("🧑‍🎓 Student Directory")
    
    action = st.radio("Select Action:", ["➕ Add New Student", "✏️ Update Existing Record", "❌ Remove Student"], horizontal=True)
    st.divider()

    # ACTION 1: ADD
    if action == "➕ Add New Student":
        st.subheader("Enroll New Student")
        with st.form("add_student_form"):
            c1, c2 = st.columns(2)
            with c1:
                new_name = st.text_input("Student Name")
                new_phone = st.text_input("Parent Phone (+91...)")
                new_amount = st.number_input("Fee (₹)", min_value=100.0, value=1200.0)
            with c2:
                new_due_date = st.date_input("First Due Date")
                new_status = st.selectbox("Status", ["Pending", "Paid"])
                
            if st.form_submit_button("Add Student"):
                if not new_name or not new_phone:
                    st.error("Name and Phone required.")
                else:
                    with conn.session as session:
                        session.execute(
                            text("INSERT INTO Students (student_name, parent_phone, fee_amount, due_date, payment_status, last_updated_by) VALUES (:name, :phone, :amt, :date, :status, :user)"),
                            {"name": new_name, "phone": new_phone, "amt": new_amount, "date": new_due_date, "status": new_status, "user": st.session_state["username"]}
                        )
                        session.commit()
                    st.success(f"Added {new_name}!")
                    st.cache_data.clear()

    # ACTION 2: UPDATE
    elif action == "✏️ Update Existing Record":
        st.subheader("Modify Student Details")
        df_students = conn.query("SELECT id, student_name, parent_phone, fee_amount, due_date, payment_status FROM Students ORDER BY student_name;", ttl="0m")
        if not df_students.empty:
            student_map = dict(zip(df_students['student_name'], df_students['id']))
            selected = st.selectbox("Select Student to Update", list(student_map.keys()))
            
            curr_data = df_students[df_students['student_name'] == selected].iloc[0]
            
            with st.form("update_student_form"):
                c1, c2 = st.columns(2)
                with c1:
                    upd_phone = st.text_input("Phone", value=curr_data['parent_phone'])
                    upd_amount = st.number_input("Fee (₹)", value=float(curr_data['fee_amount']))
                with c2:
                    upd_date = st.date_input("Due Date", value=pd.to_datetime(curr_data['due_date']))
                    upd_status = st.selectbox("Status", ["Pending", "Paid"], index=0 if curr_data['payment_status'] == "Pending" else 1)
                
                if st.form_submit_button("Save Changes"):
                    with conn.session as session:
                        session.execute(
                            text("UPDATE Students SET parent_phone=:phone, fee_amount=:amt, due_date=:date, payment_status=:status, last_updated_by=:user WHERE id=:id"),
                            {"phone": upd_phone, "amt": upd_amount, "date": upd_date, "status": upd_status, "user": st.session_state["username"], "id": int(student_map[selected])}
                        )
                        session.commit()
                    st.success(f"Updated {selected}'s profile!")
                    st.cache_data.clear()
        else:
            st.info("No students in database.")

    # ACTION 3: REMOVE (Restricted Role Access)
    elif action == "❌ Remove Student":
        st.subheader("Delete Student Record")
        if st.session_state["role"] == "Franchise":
            st.error("🚫 Access Denied: Franchise users cannot permanently delete records. Please contact Company Admin.")
        else:
            df_students = conn.query("SELECT id, student_name FROM Students ORDER BY student_name;", ttl="0m")
            if not df_students.empty:
                student_map = dict(zip(df_students['student_name'], df_students['id']))
                del_selected = st.selectbox("Select Student to Permanently Delete", list(student_map.keys()))
                
                if st.button("⚠️ Permanently Delete", type="primary"):
                    with conn.session as session:
                        session.execute(text("DELETE FROM Students WHERE id=:id"), {"id": int(student_map[del_selected])})
                        session.commit()
                    st.success(f"Deleted {del_selected} from the database.")
                    st.cache_data.clear()
