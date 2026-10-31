"""Generate a synthetic 'Google Sheet' export of lead records."""
import random

import pandas as pd

import config

FIRST_NAMES = ["aarav", "diya", "kabir", "meera", "rohan", "sneha", "vikram", "anita"]
LAST_NAMES = ["sharma", "patel", "das", "nair", "singh", "mishra", "roy", "iyer"]
COMPANIES = ["Acme Corp", "Globex", "Initech", "Umbrella Labs", "Stark Works", "Wayne Tech"]
LONG_COMPANY = "International Business Solutions and Consulting Pvt Ltd"  # over 30 chars


def generate(n: int = config.LEAD_COUNT, seed: int = 42) -> pd.DataFrame:
    random.seed(seed)
    rows = []
    for i in range(1, n + 1):
        first, last = random.choice(FIRST_NAMES), random.choice(LAST_NAMES)
        phone = f"+91{random.randint(7000000000, 9999999999)}"
        if i % 50 == 0:
            phone += " x123"  # phone with an extension
        rows.append({
            "lead_id": i,
            "first_name": first.title(),
            "last_name": last.title(),
            "email": f"{first}.{last}{i}@example.com",
            "company": LONG_COMPANY if i % 40 == 0 else random.choice(COMPANIES),
            "phone": phone,
        })
    df = pd.DataFrame(rows)
    df.to_csv(config.LEADS_CSV, index=False)
    print(f"Wrote {len(df)} leads -> {config.LEADS_CSV}")
    return df


if __name__ == "__main__":
    generate()