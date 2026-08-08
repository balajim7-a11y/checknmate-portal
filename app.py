import streamlit as st
from sqlalchemy import text
import datetime

st.set_page_config(page_title="Check N Mate - Operations", layout="wide")
st.title("Check N Mate - Operations & Fee Dashboard")

# Establish Neon PostgreSQL Connection
conn = st.connection("postgresql", type="sql")

# Operational Navigation Tabs
tab1, tab2, tab3, tab4 = st.tabs([
    "📋 Roster & Real-Time Status", 
    "➕ Onboard Student", 
    "💳 Log Payment", 
    "⚙️ SuperAdmin Center"
])

# ==============================================================================
# TAB 1: ROSTER & REAL-TIME STATUS
# ==============================================================================
with tab1:
    st.header("Active Student Roster")
    try:
        roster_query = """
        SELECT 
            s.student_id AS "ID",
            s.full_name AS "Student Name",
            s.parent_phone AS "Parent Phone",
            b.batch_name AS "Batch",
            sb.agreed_fee AS "Agreed Fee (₹)",
            sb.next_due_date AS "Next Due Date",
            CASE 
                WHEN CURRENT_DATE > sb.next_due_date THEN 'Overdue'
                WHEN CURRENT_DATE >= (sb.next_due_date - INTERVAL '7 days') THEN 'Due Soon'
                ELSE 'Paid'
            END AS "Real-Time Status"
        FROM Students s
        JOIN Student_Batches sb ON s.student_id = sb.student_id
        JOIN Batches b ON sb.batch_id = b.batch_id
        WHERE s.status = 'Active'
        ORDER BY s.student_id;
        """
        roster_df = conn.query(roster_query, ttl=0)
        
        if not roster_df.empty:
            st.dataframe(roster_df, use_container_width=True, hide_index=True)
        else:
            st.info("No active students found in the roster.")
            
        st.markdown("---")
        st.subheader("🔍 Student Payment History Ledger")
        student_list = conn.query("SELECT student_id, full_name FROM Students WHERE status = 'Active';", ttl=0)
        
        if not student_list.empty:
            st_dict = {row['student_id']: row['full_name'] for _, row in student_list.iterrows()}
            selected_s_id = st.selectbox("Select Student", options=st_dict.keys(), format_func=lambda x: st_dict[x])
            
            history_df = conn.query("""
                SELECT 
                    ft.payment_date AS "Date", 
                    ft.amount_paid AS "Amount (₹)", 
                    ft.payment_mode AS "Mode", 
                    ft.transaction_status AS "Status",
                    u.full_name AS "Logged By"
                FROM Fee_Transactions ft
                LEFT JOIN Users u ON ft.logged_by = u.user_id
                WHERE ft.student_id = :s_id
                ORDER BY ft.payment_date DESC;
            """, params={"s_id": selected_s_id}, ttl=0)
            
            if not history_df.empty:
                st.dataframe(history_df, use_container_width=True, hide_index=True)
            else:
                st.caption("No payment records found for this student.")
                
    except Exception as e:
        st.error(f"System Error in Roster: {e}")

# ==============================================================================
# TAB 2: ONBOARD STUDENT
# ==============================================================================
with tab2:
    st.header("Onboard New Student")
    try:
        batches_df = conn.query("""
            SELECT b.batch_id, b.batch_name, c.default_fee, f.franchise_id, f.franchise_name 
            FROM Batches b 
            JOIN Classes c ON b.class_id = c.class_id 
            JOIN Franchises f ON c.franchise_id = f.franchise_id;
        """, ttl=0)
        
        if not batches_df.empty:
            batch_options = {
                row['batch_id']: f"{row['batch_name']} - {row['franchise_name']} (Default: ₹{row['default_fee']})" 
                for _, row in batches_df.iterrows()
            }
            
            with st.form("onboard_form", clear_on_submit=True):
                full_name = st.text_input("Student Full Name")
                parent_name = st.text_input("Parent Name")
                parent_phone = st.text_input("Parent Phone Number")
                selected_batch_id = st.selectbox("Assign Batch", options=batch_options.keys(), format_func=lambda x: batch_options[x])
                
                default_fee_val = float(batches_df[batches_df['batch_id'] == selected_batch_id]['default_fee'].values[0])
                agreed_fee = st.number_input("Agreed Monthly Fee (₹)", min_value=0.0, value=default_fee_val, step=100.0)
                due_date = st.date_input("First Due Date", datetime.date.today())
                
                submit_onboard = st.form_submit_button("Onboard Student", type="primary")
                
                if submit_onboard:
                    if full_name and parent_phone:
                        franchise_id = int(batches_df[batches_df['batch_id'] == selected_batch_id]['franchise_id'].values[0])
                        
                        with conn.session as s:
                            # 1. Create Student Record
                            res = s.execute(text("""
                                INSERT INTO Students (full_name, franchise_id, parent_name, parent_phone, account_fee_status, status)
                                VALUES (:name, :f_id, :p_name, :phone, 'Unpaid', 'Active')
                                RETURNING student_id;
                            """), {
                                "name": full_name, "f_id": franchise_id, 
                                "p_name": parent_name, "phone": parent_phone
                            })
                            new_student_id = res.fetchone()[0]
                            
                            # 2. Assign to Batch
                            s.execute(text("""
                                INSERT INTO Student_Batches (student_id, batch_id, enrollment_date, agreed_fee, next_due_date, enrollment_status)
                                VALUES (:s_id, :b_id, CURRENT_DATE, :fee, :due, 'Active');
                            """), {
                                "s_id": new_student_id, "b_id": selected_batch_id,
                                "fee": agreed_fee, "due": due_date
                            })
                            s.commit()
                            
                        st.success(f"Successfully onboarded {full_name}!")
                        st.rerun()
                    else:
                        st.warning("Please fill in required fields (Name and Parent Phone).")
        else:
            st.warning("No active Batches found. Please set up your database first.")
    except Exception as e:
        st.error(f"Onboarding Error: {e}")

# ==============================================================================
# TAB 3: LOG MANUAL PAYMENT
# ==============================================================================
with tab3:
    st.header("Log Manual Payment (Cash / Direct UPI)")
    try:
        active_students = conn.query("""
            SELECT s.student_id, s.full_name, s.parent_phone, sb.batch_id, sb.agreed_fee 
            FROM Students s
            JOIN Student_Batches sb ON s.student_id = sb.student_id
            WHERE s.status = 'Active';
        """, ttl=0)
        
        if not active_students.empty:
            student_map = {
                row['student_id']: f"{row['full_name']} ({row['parent_phone']}) - Monthly Fee: ₹{row['agreed_fee']}"
                for _, row in active_students.iterrows()
            }
            
            with st.form("manual_payment_form", clear_on_submit=True):
                pay_student_id = st.selectbox("Select Student", options=student_map.keys(), format_func=lambda x: student_map[x])
                amount_paid = st.number_input("Amount Paid (₹)", min_value=0.0, step=100.0)
                payment_mode = st.selectbox("Payment Mode", ["Cash", "UPI Direct", "Bank Transfer"])
                payment_date = st.date_input("Payment Date", datetime.date.today())
                
                submit_payment = st.form_submit_button("Confirm & Update Status", type="primary")
                
                if submit_payment and amount_paid > 0:
                    selected_row = active_students[active_students['student_id'] == pay_student_id].iloc[0]
                    b_id = int(selected_row['batch_id'])
                    next_due = payment_date + datetime.timedelta(days=30)
                    
                    with conn.session as s:
                        s.execute(text("""
                            INSERT INTO Fee_Transactions (student_id, amount_paid, payment_mode, payment_date, transaction_status, logged_by, for_batch_id)
                            VALUES (:s_id, :amt, :mode, :p_date, 'Success', 1, :b_id);
                        """), {
                            "s_id": pay_student_id, "amt": amount_paid, 
                            "mode": payment_mode, "p_date": payment_date, "b_id": b_id
                        })
                        
                        s.execute(text("""
                            UPDATE Student_Batches SET next_due_date = :next_due WHERE student_id = :s_id AND batch_id = :b_id;
                        """), {"next_due": next_due, "s_id": pay_student_id, "b_id": b_id})
                        
                        s.execute(text("""
                            UPDATE Students SET account_fee_status = 'Paid' WHERE student_id = :s_id;
                        """), {"s_id": pay_student_id})
                        
                        s.commit()
                    st.success("Payment recorded and student next due date extended!")
                    st.rerun()
        else:
            st.info("No active students available.")
    except Exception as e:
        st.error(f"Error processing payment form: {e}")

# ==============================================================================
# TAB 4: SUPERADMIN CENTER
# ==============================================================================
with tab4:
    st.header("SuperAdmin Resolution Center")
    st.subheader("⚠️ Unmatched Webhook Payments")
    
    try:
        unmatched_df = conn.query("""
            SELECT 
                transaction_id AS "Txn ID", 
                amount_paid AS "Amount (₹)", 
                payment_mode AS "Mode", 
                payment_date AS "Date", 
                gateway_reference AS "Gateway Ref" 
            FROM Fee_Transactions 
            WHERE transaction_status = 'Unmatched'
            ORDER BY payment_date ASC;
        """, ttl=0)
        
        if unmatched_df.empty:
            st.success("All clear! There are no unmatched webhook transactions.")
        else:
            st.dataframe(unmatched_df, use_container_width=True, hide_index=True)
            
            st.markdown("---")
            st.subheader("Link Payment to Student")
            
            active_s_query = conn.query("SELECT student_id, full_name, parent_phone FROM Students WHERE status = 'Active';", ttl=0)
            if not active_s_query.empty:
                s_options = {row['student_id']: f"{row['full_name']} ({row['parent_phone']})" for _, row in active_s_query.iterrows()}
                
                with st.form("resolve_form", clear_on_submit=True):
                    col1, col2 = st.columns(2)
                    with col1:
                        target_txn_id = st.number_input("Transaction ID to Resolve", min_value=1, step=1)
                    with col2:
                        target_student_id = st.selectbox("Select Student", options=s_options.keys(), format_func=lambda x: s_options[x])
                        
                    resolve_btn = st.form_submit_button("Assign & Resolve", type="primary")
                    
                    if resolve_btn:
                        with conn.session as s:
                            s.execute(text("""
                                UPDATE Fee_Transactions 
                                SET student_id = :s_id, transaction_status = 'Success' 
                                WHERE transaction_id = :t_id AND transaction_status = 'Unmatched';
                            """), {"s_id": target_student_id, "t_id": target_txn_id})
                            
                            new_due = datetime.date.today() + datetime.timedelta(days=30)
                            s.execute(text("""
                                UPDATE Student_Batches SET next_due_date = :next_due WHERE student_id = :s_id;
                            """), {"next_due": new_due, "s_id": target_student_id})
                            
                            s.execute(text("""
                                UPDATE Students SET account_fee_status = 'Paid' WHERE student_id = :s_id;
                            """), {"s_id": target_student_id})
                            s.commit()
                        st.success(f"Transaction #{target_txn_id} successfully assigned!")
                        st.rerun()
    except Exception as e:
        st.error(f"Error in SuperAdmin Panel: {e}")
