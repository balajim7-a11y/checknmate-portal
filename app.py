import json
import time
from datetime import datetime, timedelta
import pandas as pd
import razorpay
from sqlalchemy import text
import streamlit as st
from twilio.rest import Client

# --- 1. PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Check N Mate - Fee Portal",
    page_icon="♟️",
    layout="wide"
)

# --- 2. ADMIN AUTHENTICATION ---
def check_password():
    """Returns True if the admin enters the correct credentials."""
    def password_entered():
        if st.session_state["password"] == st.secrets["admin_password"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.text_input("🔒 Enter Admin Password", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.text_input("🔒 Enter Admin Password", type="password", on_change=password_entered, key="password")
        st.error("😕 Incorrect Password")
        return False
    
    return True

if not check_password():
    st.stop()

# --- 3. DATABASE CONNECTION ---
@st.cache_resource
def init_connection():
    return st.connection("postgresql", type="sql")

conn = init_connection()

# --- 4. PAYMENT & MESSAGING ENGINE ---
def dispatch_whatsapp_payload(student_name: str, parent_phone: str, amount: float, message_type: str):
    """
    Creates an auto-expiring Razorpay Payment Link and dispatches a WhatsApp notification.
    Uses custom text if the 24h conversation window is active; otherwise falls back to the template.
    """
    rzp_client = razorpay.Client(auth=(st.secrets["razorpay"]["key_id"], st.secrets["razorpay"]["key_secret"]))
    twilio_client = Client(st.secrets["twilio"]["account_sid"], st.secrets["twilio"]["auth_token"])

    # Set payment link to self-destruct after 3 days
    expiry_timestamp = int(time.time()) + (3 * 24 * 60 * 60)

    # 1. Create Razorpay Payment Link
    payment_link = rzp_client.payment_link.create({
        "amount": int(amount * 100),  # Convert INR to paise
        "currency": "INR",
        "expire_by": expiry_timestamp,
        "description": f"Fee payment for {student_name}",
        "customer": {
            "name": student_name,
            "contact": parent_phone
        },
        "notify": {"sms": False, "email": False}
    })
    short_url = payment_link["short_url"]

    # 2. Construct Custom Message
    if message_type == "upcoming":
        custom_body = (
            f"Hi from Check N Mate! ♟️\n\n"
            f"This is a reminder that the fee of ₹{int(amount)} for {student_name} is due in 3 days.\n\n"
            f"Pay securely here: {short_url}\n\n"
            f"Thank you!"
        )
    else:
        custom_body = (
            f"URGENT: Hi from Check N Mate! ♟️\n\n"
            f"The fee of ₹{int(amount)} for {student_name} is currently OVERDUE.\n\n"
            f"Please complete the payment using this link: {short_url}\n\n"
            f"Thank you!"
        )

    # 3. Attempt Delivery with Template Fallback
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
                content_variables=json.dumps({
                    "1": status_label,
                    "2": short_url
                }),
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
    "➕ Enroll Student"
])

# --- TAB 1: ACTIVE ROSTER ---
with tab1:
    st.header("Student Fee Roster")
    st.caption("Live synchronization with Neon PostgreSQL database.")
    
    col_a, _ = st.columns([1, 5])
    with col_a:
        if st.button("🔄 Refresh Data", use_container_width=True):
            st.cache_data.clear()
        
    try:
        df = conn.query("SELECT id, student_name, parent_phone, fee_amount, due_date, payment_status FROM Students ORDER BY due_date ASC;", ttl="0m")
        st.dataframe(df, use_container_width=True, hide_index=True)
    except Exception as e:
        st.error(f"Error fetching data: {e}")

# --- TAB 2: BATCH AUTOMATIONS ---
with tab2:
    st.header("Automated Messaging Engine")
    st.caption("Executes notification rules against current student due dates.")
    
    if st.button("🚀 Execute Daily Notification Batch", type="primary"):
        with st.spinner("Processing pending payments..."):
            try:
                df = conn.query("SELECT * FROM Students WHERE payment_status = 'Pending';", ttl="0m")
                
                if df.empty:
                    st.info("No pending payments found in the database.")
                else:
                    df['due_date'] = pd.to_datetime(df['due_date']).dt.date
                    today = datetime.now().date()
                    three_days_from_now = today + timedelta(days=3)

                    upcoming_students = df[df['due_date'] == three_days_from_now]
                    overdue_students = df[df['due_date'] < today]

                    st.markdown("### Execution Summary")

                    # 1. Upcoming Reminders
                    if not upcoming_students.empty:
                        st.subheader(f"Upcoming Reminders ({len(upcoming_students)})")
                        for _, row in upcoming_students.iterrows():
                            try:
                                link, sid, delivery_type = dispatch_whatsapp_payload(
                                    row['student_name'], row['parent_phone'], row['fee_amount'], "upcoming"
                                )
                                st.success(f"✅ Sent to **{row['student_name']}** ({row['parent_phone']}) via {delivery_type} | [Link]({link})")
                            except Exception as err:
                                st.error(f"❌ Failed for {row['student_name']}: {err}")
                    else:
                        st.info("ℹ️ No payments due in exactly 3 days.")

                    # 2. Overdue Reminders
                    if not overdue_students.empty:
                        st.subheader(f"Overdue Notices ({len(overdue_students)})")
                        for _, row in overdue_students.iterrows():
                            try:
                                link, sid, delivery_type = dispatch_whatsapp_payload(
                                    row['student_name'], row['parent_phone'], row['fee_amount'], "overdue"
                                )
                                st.warning(f"⚠️ Sent to **{row['student_name']}** ({row['parent_phone']}) via {delivery_type} | [Link]({link})")
                            except Exception as err:
                                st.error(f"❌ Failed for {row['student_name']}: {err}")
                    else:
                        st.info("ℹ️ No overdue payments found.")

            except Exception as e:
                st.error(f"Database batch operation failed: {e}")

# --- TAB 3: MANAGE DUE DATES ---
with tab3:
    st.header("🗓️ Manage Student Deadlines")
    st.caption("Update individual deadlines or use bulk update across all records for live testing.")
    
    col_single, col_bulk = st.columns(2)
    
    # Single Student Update
    with col_single:
        st.subheader("Single Student Update")
        try:
            df_students = conn.query("SELECT id, student_name, due_date FROM Students ORDER BY student_name;", ttl="0m")
            if not df_students.empty:
                with st.form("single_update_form"):
                    student_map = dict(zip(df_students['student_name'], df_students['id']))
                    selected_student = st.selectbox("Select Student", list(student_map.keys()))
                    
                    curr_date = df_students[df_students['student_name'] == selected_student]['due_date'].iloc[0]
                    st.write(f"Current due date: **{curr_date}**")
                    
                    new_due_date = st.date_input("New Due Date", key="single_date_input")
                    submit_single = st.form_submit_button("Update Student")
                    
                    if submit_single:
                        student_id = int(student_map[selected_student])
                        with conn.session as session:
                            session.execute(
                                text("UPDATE Students SET due_date = :due_date WHERE id = :id"),
                                {"due_date": new_due_date, "id": student_id}
                            )
                            session.commit()
                        st.success(f"Updated {selected_student}'s due date to {new_due_date}!")
                        st.cache_data.clear()
            else:
                st.warning("No records found.")
        except Exception as e:
            st.error(f"Error loading student list: {e}")

    # Bulk Update Across the Board
    with col_bulk:
        st.subheader("Bulk Update (Testing Engine)")
        st.info("💡 Set all records at once to test the automated rules in Tab 2.")
        
        with st.form("bulk_update_form"):
            bulk_date = st.date_input("Set Date for ALL Records", key="bulk_date_input")
            submit_bulk = st.form_submit_button("⚡ Apply to All Students")
            
            if submit_bulk:
                try:
                    with conn.session as session:
                        session.execute(
                            text("UPDATE Students SET due_date = :bulk_date"),
                            {"bulk_date": bulk_date}
                        )
                        session.commit()
                    st.success(f"Successfully updated ALL records to {bulk_date}!")
                    st.cache_data.clear()
                except Exception as e:
                    st.error(f"Bulk update failed: {e}")

# --- TAB 4: ENROLL NEW STUDENT ---
with tab4:
    st.header("➕ Enroll New Student")
    st.caption("Add a new student directly into the PostgreSQL database.")
    
    with st.form("add_student_form"):
        col_left, col_right = st.columns(2)
        
        with col_left:
            new_name = st.text_input("Student Name", placeholder="e.g., Rahul Sharma")
            new_phone = st.text_input("Parent Phone Number", placeholder="e.g., +919019011331")
            new_amount = st.number_input("Fee Amount (₹)", min_value=100.0, value=1200.0, step=100.0)
            
        with col_right:
            new_due_date = st.date_input("First Due Date")
            new_status = st.selectbox("Initial Payment Status", ["Pending", "Paid"])
            
        submit_new = st.form_submit_button("✅ Add Student to Database")
        
        if submit_new:
            if not new_name.strip() or not new_phone.strip():
                st.warning("⚠️ Student Name and Parent Phone are required.")
            elif not new_phone.startswith("+"):
                st.warning("⚠️ Phone number must include the international country code (e.g., +91...)")
            else:
                try:
                    with conn.session as session:
                        session.execute(
                            text("""
                                INSERT INTO Students 
                                (student_name, parent_phone, fee_amount, due_date, payment_status) 
                                VALUES (:name, :phone, :amount, :due_date, :status)
                            """),
                            {
                                "name": new_name.strip(), 
                                "phone": new_phone.strip(), 
                                "amount": new_amount, 
                                "due_date": new_due_date, 
                                "status": new_status
                            }
                        )
                        session.commit()
                    
                    st.success(f"🎉 Successfully enrolled **{new_name}**!")
                    st.cache_data.clear()
                except Exception as e:
                    st.error(f"Failed to add student to database: {e}")
