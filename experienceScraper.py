# Dumb script to scrape sailing data from MIT Sailing website
# Lucas Ehinger 12-Sep-24
# Known issues that I probably won't get around to fixing:
#       -- Counts trips that are not sails (bluewater work days)
#       -- Multi-day trips must be multi-day in the date (not description)

# There are better ways to organize this code, but I'm lazy and it runs quickly enough

import pandas as pd
import re
from urllib.request import urlopen
from datetime import datetime


def get_trip_urls(year,month):
    url = f"http://sailing.mit.edu/calendar/index.php?cal=month&year={year}&month={month}&type=13"
    page = urlopen(url)

    html_bytes = page.read()
    html = html_bytes.decode("utf-8", errors='ignore')

    pattern = r"(/calendar/events/event[^']*')"
    matches = re.findall(pattern, html)

    base_url = "http://sailing.mit.edu"
    updated_matches = [base_url + match[:-1] for match in matches]

    # Replace event.php with entries.php
    updated_matches = [match.replace("event.php", "entries.php") for match in updated_matches]

    unique_matches = list(set(updated_matches))
    return unique_matches

def get_title(html):
    title = re.search(r'<title>(.*?)</title>', html)
    title = title.group(1)
    if title.endswith(" Entries"):
        title = title[:-8]
    return title

def is_cancelled(html):
    title = get_title(html)
    return "cancel" in title.lower()

def get_time_data(html):
    times = re.findall(r'<tr><td style=\'text-align:right\'>(.*?)</td></tr>', html)
    times = [time for time in times if "Registration" not in time]
    start = times[0].split("</td><td>")
    start_day=start[0].split(' ')[1]
    start_time=start[1].split('-')[0]
    end = times[-1].split("</td><td>")
    end_day=end[0].split(' ')[1]
    end_time=end[1].split('-')[1]

    date_format = "%d-%b-%Y %H:%M"
    start_datetime = datetime.strptime(f"{start_day} {start_time}", date_format)
    end_datetime = datetime.strptime(f"{end_day} {end_time}", date_format)

    time_difference = end_datetime - start_datetime
    hours_elapsed = time_difference.total_seconds() / 3600

    return start_datetime, end_datetime, hours_elapsed

def is_racing(html):
    url = re.search(r'/calendar/events/event.php([^"]*)\'>Description', html)
    if not url:
        return False
    url = base_url = "http://sailing.mit.edu/calendar/events/event.php"+ url.group(1)
    page = urlopen(url)
    html_bytes = page.read()
    html = html_bytes.decode("utf-8", errors='ignore')

    description = re.search(r'<h2>Description</h2>(.*?)<h2>Organizers</h2>', html, re.DOTALL)
    if not description:
        return False
    description=description.group(1).strip()

    keywords = ["race", "regatta", "cup"]
    text = description + get_title(html)
    lower_text = text.lower()
    return any(keyword in lower_text for keyword in keywords)

def get_participant_status(html):
    pattern = r'<h2>Entries</h2><table>(.*?)</table>'
    entries_table = re.search(pattern, html, re.DOTALL)
    if not entries_table:
        return []
    entries_table = entries_table.group(1)
    entries_array = entries_table.split('\n')
    entries_array = [entry for entry in entries_array if entry.startswith("<tr class") and entry.endswith("</td></tr>")]
    details = []
    for entry in entries_array:
        last_name = re.search(r'>([^<]+)</a>', entry).group(1)
        first_name = re.search(r'</a></td><td>([^<]+)</td><td>', entry).group(1)
        status = "Confirmed" if "Confirmed" in entry else "Pending" if "Pending" in entry else "Unknown"
        if is_cancelled(html) and status == "Confirmed":
            status = "Cancelled"
        details.append((last_name, first_name, status))
    return details

def get_skippers(html):
    pattern = r'Questions about this event should be directed to the organizer.*?>(.*?)</a>'
    skippers = re.search(pattern, html, re.DOTALL)
    if not skippers:
        return []
    skippers= skippers.group(1).strip().split(', ')

    details=[]
    for skipper in skippers:
        last_name = skipper.split(' ')[-1]
        first_name = " ".join(skipper.split(' ')[:-1])
        if is_cancelled(html):
            details.append((last_name, first_name, "Cancelled"))
        else:
            details.append((last_name, first_name, "Skipper"))
    return details

def river_sail(title):
    return "river" in title.lower()

def get_all_participant_data(year, month):
    urls = get_trip_urls(year, month)
    data=[]
    for url in urls:
        page = urlopen(url)
        html_bytes = page.read()
        html = html_bytes.decode("utf-8", errors='ignore')

        title = get_title(html)
        start, end, hours = get_time_data(html)
        racing = is_racing(html)
        participants = get_participant_status(html)
        skippers=get_skippers(html)
        sailors = participants + skippers

        for last_name, first_name, status in sailors:
            data.append({
                "first name": first_name,
                "last name": last_name,
                "trip name": title,
                "start": start,
                "end": end,
                "duration": hours,
                "race": racing,
                "status": status
            })

    df = pd.DataFrame(data, columns=[
        "first name", "last name", "trip name", "start", "end", "duration", "race", "status"
    ])
    df = df[~df["trip name"].apply(river_sail)]
    df = df.drop_duplicates(subset=["first name", "last name", "trip name", "start", "end", "duration", "race", "status"], keep="first")
    df = df.reset_index(drop=True)
    return df



columns = [
    "first name", "last name", "number registrations", "number sails",
    "number races", "number pleasure", "number multi-day",
    "number full day (6+ hr)", "number as skipper", "total sail time (hrs)"
]
df_final = pd.DataFrame(columns=columns)

start_year = 2007
start_month = 1
end_year = 2024
end_month = 11 # December 2024 doesn't exist, and defaults to September 2024. https://sailing.mit.edu/calendar/index.php?cal=month&year=2024&month=12

for year in range(start_year, end_year+1):
    for month in range(1, 13):
        if year == start_year and month < start_month:
            continue
        if year == end_year and month > end_month:
            break
        df_all = get_all_participant_data(year, month)
        for index, row in df_all.iterrows():
            first_name = row["first name"]
            last_name = row["last name"]

            # Check if the participant exists in df_final
            participant_exists = df_final[(df_final["first name"] == first_name) & (df_final["last name"] == last_name)]

            if participant_exists.empty:
                # Add new participant to df_final
                if row["status"] == "Pending" or row["status"] == "Cancelled":
                    new_row = {
                        "first name": first_name,
                        "last name": last_name,
                        "number registrations": 1,
                        "number sails": 0,
                        "number races": 0,
                    "number pleasure": 0 ,
                    "number multi-day": 0,
                    "number full day (6+ hr)": 0,
                    "number as skipper": 0,
                    "total sail time (hrs)": 0
                }
                else:
                    new_row = {
                        "first name": first_name,
                        "last name": last_name,
                        "number registrations": 1,
                        "number sails": 1,
                        "number races": 1 if row["race"] else 0,
                        "number pleasure": 0 if row["race"] else 1,
                        "number multi-day": 1 if row["duration"] > 24 else 0,
                        "number full day (6+ hr)": 1 if row["duration"] > 6 else 0,
                        "number as skipper": 1 if row["status"] == "Skipper" else 0,
                        "total sail time (hrs)": row["duration"]
                    }
                df_final.loc[len(df_final)] = new_row

            else:
                # Update existing participant's entries
                idx = participant_exists.index[0]
                df_final.at[idx, "number registrations"] += 1
                if row["status"] == "Confirmed" or row["status"] == "Skipper":
                    df_final.at[idx, "number sails"] += 1
                    df_final.at[idx, "number races"] += 1 if row["race"] else 0
                    df_final.at[idx, "number pleasure"] += 0 if row["race"] else 1
                    df_final.at[idx, "number multi-day"] += 1 if row["duration"] > 24 else 0
                    df_final.at[idx, "number full day (6+ hr)"] += 1 if row["duration"] > 6 else 0
                    df_final.at[idx, "number as skipper"] += 1 if row["status"] == "Skipper" else 0
                    df_final.at[idx, "total sail time (hrs)"] += row["duration"]



df_final_sorted = df_final.sort_values(by="total sail time (hrs)", ascending=False)
# df_final_sorted = df_final.sort_values(by="number sails", ascending=False)
print(df_final_sorted)
df_final_sorted.to_csv("sailing_data_all_time.csv", index=False)
