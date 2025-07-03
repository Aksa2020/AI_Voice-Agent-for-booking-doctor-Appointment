import os
import yaml
import pandas as pd
import csv
from dateutil import parser
from typing import List, Optional

FIELDNAMES = ['date', 'time', 'is_booked', 'purpose', 'name']

def load_prompt(filename: str) -> str:
    """
    Load prompt instructions from a YAML file located in 'prompts' directory.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    prompt_path = os.path.join(script_dir, 'prompts', filename)
    try:
        with open(prompt_path, 'r') as file:
            prompt_data = yaml.safe_load(file)
            return prompt_data.get('instructions', '')
    except (FileNotFoundError, yaml.YAMLError) as e:
        print(f"Error loading prompt file {filename}: {e}")
        return ""

def get_free_slots(appointment_csv: str, date: str) -> List[str]:
    """
    Returns a list of available time slots for a given date from the CSV file.
    Accepts flexible date formats.
    """
    try:
        formatted_date = parser.parse(date, dayfirst=True).strftime("%Y-%m-%d")
    except (ValueError, TypeError) as e:
        raise ValueError(f"Unable to parse the date: {date}") from e

    try:
        df = pd.read_csv(appointment_csv)
    except FileNotFoundError:
        print(f"CSV file not found: {appointment_csv}")
        return []

    # Normalize 'date' column for comparison
    df['date'] = pd.to_datetime(df['date']).dt.strftime("%Y-%m-%d")

    # Filter rows where date matches and is_booked is False
    slots = df[(df['date'] == formatted_date) & (df['is_booked'].astype(str).str.lower() == 'false')]

    return slots['time'].tolist()

def store_appointment(appointment_csv: str, date: str, time: str, purpose: str, name: str) -> bool:
    """
    Book an appointment by updating the CSV if the slot is available.
    Returns True if booking succeeded, False otherwise.
    """
    rows = []
    updated = False

    try:
        formatted_date = parser.parse(date, dayfirst=True).strftime("%Y-%m-%d")
    except (ValueError, TypeError) as e:
        raise ValueError(f"Unable to parse the date: {date}") from e

    try:
        with open(appointment_csv, mode='r', newline='') as file:
            reader = csv.DictReader(file)
            for row in reader:
                if row['date'] == formatted_date and row['time'] == time:
                    if row['is_booked'].lower() == 'false':
                        row['is_booked'] = 'True'
                        row['purpose'] = purpose
                        row['name'] = name
                        updated = True
                rows.append(row)
    except FileNotFoundError:
        print(f"CSV file not found: {appointment_csv}")
        return False

    if updated:
        with open(appointment_csv, mode='w', newline='') as file:
            writer = csv.DictWriter(file, fieldnames=FIELDNAMES)
            writer.writeheader()
            writer.writerows(rows)

    return updated
    
def cancel_appointment(appointment_csv: str, date: str, name: str) -> bool:
    """
    Cancel an appointment by name and date.

    Accepts flexible date formats (e.g., '30-05-2025', 'May 30, 2025').
    Sets is_booked to False and clears the name and purpose fields.

    Args:
        appointment_csv: Path to the CSV file containing appointments.
        date: The date of the appointment (flexible format supported).
        name: The name under which the appointment was booked.

    Returns:
        True if the cancellation was successful, False otherwise.
    """
    updated = False
    rows = []

    try:
        # Flexible date parsing using dateutil.parser
        formatted_date = parser.parse(date, dayfirst=True).strftime("%Y-%m-%d")
    except (ValueError, TypeError) as e:
        raise ValueError(f"Unable to parse the date: {date}") from e

    try:
        with open(appointment_csv, mode='r', newline='') as file:
            reader = csv.DictReader(file)
            for row in reader:
                if row['date'] == formatted_date and row['name'].strip().lower() == name.strip().lower() and row['is_booked'].strip().lower() == 'true':
                    row['is_booked'] = 'False'
                    row['name'] = ''
                    row['purpose'] = ''
                    updated = True
                rows.append(row)
    except FileNotFoundError:
        print(f"CSV file not found: {appointment_csv}")
        return False

    if updated:
        with open(appointment_csv, mode='w', newline='') as file:
            writer = csv.DictWriter(file, fieldnames=FIELDNAMES)
            writer.writeheader()
            writer.writerows(rows)

    return updated


# def cancel_appointment(appointment_csv: str, date: str, name: str) -> bool:
#     """
#     Cancel an appointment by name and date.
#     Sets is_booked to False and clears the name and purpose fields.
#     """
#     updated = False
#     rows = []

#     try:
#         formatted_date = parser.parse(date, dayfirst=True).strftime("%Y-%m-%d")
#     except (ValueError, TypeError) as e:
#         raise ValueError(f"Unable to parse the date: {date}") from e

#     try:
#         with open(appointment_csv, mode='r', newline='') as file:
#             reader = csv.DictReader(file)
#             for row in reader:
#                 if row['date'] == formatted_date and row['name'].strip().lower() == name.strip().lower() and row['is_booked'].lower() == 'true':
#                     row['is_booked'] = 'False'
#                     row['name'] = ''
#                     row['purpose'] = ''
#                     updated = True
#                 rows.append(row)
#     except FileNotFoundError:
#         print(f"CSV file not found: {appointment_csv}")
#         return False

#     if updated:
#         with open(appointment_csv, mode='w', newline='') as file:
#             writer = csv.DictWriter(file, fieldnames=FIELDNAMES)
#             writer.writeheader()
#             writer.writerows(rows)

#     return updated
