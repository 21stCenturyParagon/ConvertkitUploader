import streamlit as st
import asyncio
import csv
import os
import aiohttp
import time
from collections import deque

# Initialize session state variables
if 'subscription_started' not in st.session_state:
    st.session_state.subscription_started = False
if 'form_ids' not in st.session_state:
    st.session_state.form_ids = {}


async def fetch_forms(api_key):
    url = f"https://api.convertkit.com/v3/forms?api_key={api_key}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            return await response.json()


async def get_form_ids(api_key, form_names):
    forms_data = await fetch_forms(api_key)
    form_ids = {}
    for form_name in form_names:
        for form in forms_data['forms']:
            if form['name'] == form_name:
                form_ids[form_name] = form['id']
                break
    return form_ids


async def subscribe_users(api_key, form_ids, uploaded_files):
    async with aiohttp.ClientSession() as session:
        tasks = []
        for form_name, form_id in form_ids.items():
            csv_file = next((file for file in uploaded_files if file.name == f"{form_name}.csv"), None)
            if csv_file:
                tasks.append(subscribe_users_to_form(session, api_key, form_id, csv_file))
        await asyncio.gather(*tasks)


async def subscribe_users_to_form(session, api_key, form_id, csv_file):
    url = f"https://api.convertkit.com/v3/forms/{form_id}/subscribe"
    headers = {"Content-Type": "application/json; charset=utf-8"}
    data = {"api_key": api_key}

    csv_content = csv_file.getvalue().decode('utf-8').splitlines()
    reader = csv.DictReader(csv_content)

    request_times = deque()
    max_requests = 120
    window_size = 60  # seconds

    for row in reader:
        email = row["Emails"]
        data["email"] = email

        # Implement rate limiting
        current_time = time.time()
        request_times.append(current_time)

        if len(request_times) >= max_requests:
            oldest_request = request_times.popleft()
            time_diff = current_time - oldest_request
            if time_diff < window_size:
                sleep_time = window_size - time_diff
                await asyncio.sleep(sleep_time)

        async with session.post(url, headers=headers, json=data) as response:
            if response.status == 429:
                await asyncio.sleep(5)  # Wait for 5 seconds before retrying


def start_subscription():
    st.session_state.subscription_started = True


async def main():
    st.title("ConvertKit Subscription App")

    api_key = st.text_input("Enter your ConvertKit API Key:", type="password")
    uploaded_files = st.file_uploader("Upload CSV files", accept_multiple_files=True, type="csv")

    if api_key and uploaded_files:
        form_names = [os.path.splitext(file.name)[0] for file in uploaded_files]

        if st.button("Check Forms") and not st.session_state.subscription_started:
            with st.spinner("Checking forms..."):
                st.session_state.form_ids = await get_form_ids(api_key, form_names)

            st.write("Forms found:")
            for form_name, form_id in st.session_state.form_ids.items():
                st.write(f"- {form_name}: {form_id}")

            missing_forms = set(form_names) - set(st.session_state.form_ids.keys())
            if missing_forms:
                st.warning(f"The following forms were not found: {', '.join(missing_forms)}")

        if st.session_state.form_ids and not st.session_state.subscription_started:
            if st.button("Continue with Subscription", on_click=start_subscription):
                st.session_state.subscription_started = True

        if st.session_state.subscription_started:
            with st.spinner("Subscribing users... This may take a while."):
                await subscribe_users(api_key, st.session_state.form_ids, uploaded_files)
            st.success("Subscription process completed!")
            st.session_state.subscription_started = False  # Reset for potential future runs


if __name__ == "__main__":
    asyncio.run(main())