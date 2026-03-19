import streamlit as st
import pandas as pd
import networkx as nx
import re
from datetime import datetime, timedelta

st.set_page_config(page_title='Royal Repeats', layout='centered', page_icon='🔄')

st.image(st.secrets['images']['rr_logo'], width=100)

st.title('🔄 Royal Repeats')

st.info('An analysis on repeat guests to Royal Destinations and specific homes.')

uploaded_file = st.file_uploader('Booking Summary Report', type='xlsx')

if uploaded_file:

    # =========================
    # LOAD FULL DATASET
    # =========================
    df_full = pd.read_excel(uploaded_file)

    df_full['First_Night'] = pd.to_datetime(df_full['First_Night'])
    df_full['Last_Night'] = pd.to_datetime(df_full['Last_Night'])

    # Normalize columns
    df_full['Reservation_Number'] = df_full['Reservation_Number'].astype(str).str.strip()
    df_full['ReservationTypeDescription'] = df_full['ReservationTypeDescription'].astype(str).str.strip()

    # Remove unwanted rows
    df_full = df_full[
        (~df_full['ReservationTypeDescription'].str.lower().isin(['owner','guest of owner'])) &
        (df_full['Reservation_Number'] != '') &
        (~df_full['Booking_Number'].str.upper().str.startswith('HLD'))
    ]

    # =========================
    # NORMALIZATION
    # =========================
    def normalize_phone(x):
        if pd.isna(x):
            return None

        digits = re.sub(r'\D', '', str(x))

        if len(digits) < 7:
            return None

        # Normalize to last 10 digits if longer
        if len(digits) > 10:
            digits = digits[-10:]

        return digits

    def normalize_email(x):
        if pd.isna(x):
            return None
        return str(x).strip().lower()

    df_full['guest_name'] = (
        df_full['First_Name'].str.strip().str.lower()
        + "_"
        + df_full['Last_Name'].str.strip().str.lower()
    )

    phone_cols = ['Phone_1','Phone_2','Phone_3','Phone_4']
    email_cols = ['Email','Email_2']

    for c in phone_cols:
        df_full[c] = df_full[c].apply(normalize_phone)

    for c in email_cols:
        df_full[c] = df_full[c].apply(normalize_email)

    def get_ids(row):
        ids = [row['guest_name']]
        for c in phone_cols + email_cols:
            if pd.notna(row[c]):
                ids.append(row[c])
        return ids

    df_full['ids'] = df_full.apply(get_ids, axis=1)

    # =========================
    # BUILD GRAPH ON FULL DATA
    # =========================
    G = nx.Graph()

    for r in df_full['Reservation_Number']:
        G.add_node(r)

    id_map = {}

    for _, row in df_full.iterrows():
        res = row['Reservation_Number']
        for i in row['ids']:
            id_map.setdefault(i, []).append(res)

    for ids in id_map.values():
        for i in range(len(ids) - 1):
            G.add_edge(ids[i], ids[i+1])

    clusters = list(nx.connected_components(G))

    guest_map = {}
    for i, c in enumerate(clusters):
        for r in c:
            guest_map[r] = i

    df_full['guest_id'] = df_full['Reservation_Number'].map(guest_map)

    # =========================
    # GLOBAL REPEAT LOGIC
    # =========================
    guest_counts = df_full.groupby('guest_id')['Reservation_Number'].count()
    repeat_ids = guest_counts[guest_counts > 1].index

    # =========================
    # DATE FILTER (REPORTING ONLY)
    # =========================
    start, end = st.date_input(
        "Date Range",
        [df_full['First_Night'].min(), df_full['Last_Night'].max()]
    )

    df_filtered = df_full[
        (df_full['First_Night'] >= pd.to_datetime(start)) &
        (df_full['First_Night'] <= pd.to_datetime(end))
    ]

    repeat_df = df_filtered[df_filtered['guest_id'].isin(repeat_ids)]

    # =========================
    # PORTFOLIO METRICS
    # =========================
    total_res = len(df_filtered)
    repeat_res = len(repeat_df)

    repeat_pct = repeat_res / total_res * 100 if total_res else 0
    repeat_guests = repeat_df['guest_id'].nunique()

    st.header("🏘️ Portfolio Metrics")

    c1,c2,c3 = st.columns(3)

    c1.metric("Total Reservations", total_res)
    c2.metric("Repeat Reservations", repeat_res)
    c3.metric("Repeat Reservation %", f"{repeat_pct:.2f}%")

    # =========================
    # UNIT METRICS
    # =========================
    st.header("🏠 Unit-specific Metrics")

    unit_rows = []

    for unit, g in df_filtered.groupby("Unit_Code"):

        total = len(g)
        repeat_g = g[g['guest_id'].isin(repeat_ids)]

        repeat_count = len(repeat_g)
        pct = repeat_count / total * 100 if total else 0

        unit_rows.append({
            "Unit_Code": unit,
            "Total Reservations": total,
            "Repeat Reservations": repeat_count,
            "Repeat %": pct,
        })

    unit_df = pd.DataFrame(unit_rows).sort_values('Unit_Code', ascending=True)

    st.dataframe(unit_df, hide_index=True)

    # =========================
    # UPCOMING REPEAT GUESTS
    # =========================
    st.header("🗓️ Upcoming Repeat Guests")

    next_days = st.slider("Look ahead days", 7, 120, 14)

    today = datetime.today()
    future = today + timedelta(days=next_days)

    upcoming = repeat_df[
        (repeat_df['First_Night'] >= today) &
        (repeat_df['First_Night'] <= future)
    ].copy()

    upcoming['First_Night'] = upcoming['First_Night'].dt.date
    upcoming['Last_Night'] = upcoming['Last_Night'].dt.date
    upcoming['Name'] = upcoming['First_Name'] + " " + upcoming['Last_Name']
    upcoming['Stays'] = upcoming['guest_id'].map(guest_counts)

    upcoming = upcoming.sort_values(
        ['Stays','BookingRentTotal'],
        ascending=[False, False]
    )

    st.dataframe(
        upcoming[
            [
                'Name',
                'Unit_Code',
                'Reservation_Number',
                'First_Night',
                'Last_Night',
                'BookingRentTotal',
                'Stays',
            ]
        ],
        hide_index=True
    )

    # =========================
    # VIP GUESTS (SORTED BY SPEND)
    # =========================
    st.header("👑 Hall of Royal Repeats")

    vip_threshold = st.slider("Minimum stays", 3, 15, 5)

    guest_spend = df_full.groupby('guest_id')['BookingRentTotal'].sum()

    vip_summary = pd.DataFrame({
        "guest_id": guest_counts[guest_counts >= vip_threshold].index
    })

    vip_summary["stays"] = vip_summary['guest_id'].map(guest_counts)
    vip_summary["total_spend"] = vip_summary['guest_id'].map(guest_spend)

    vip_summary = vip_summary.sort_values("total_spend", ascending=False)

    for _, row in vip_summary.iterrows():

        gid = row['guest_id']

        g = df_full[df_full['guest_id'] == gid].sort_values("First_Night")

        g['First_Night'] = g['First_Night'].dt.date
        g['Last_Night'] = g['Last_Night'].dt.date

        name = g.iloc[0]['First_Name'] + " " + g.iloc[0]['Last_Name']
        units = g['Unit_Code'].unique()

        st.subheader(f"{name} — {int(row['stays'])} stays — {len(units)} units — ${row['total_spend']:,.0f}")

        st.dataframe(
            g[
                [
                    'Reservation_Number',
                    'Unit_Code',
                    'First_Night',
                    'Last_Night',
                    'BookingRentTotal',
                    ]
            ],
            hide_index=True
        )