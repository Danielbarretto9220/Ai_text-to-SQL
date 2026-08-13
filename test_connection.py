import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

try:
    connection = psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        database=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )

    print("✅ PostgreSQL connection successful!")

    cursor = connection.cursor()
    cursor.execute("SELECT current_database(), current_user;")

    database, user = cursor.fetchone()

    print(f"Database: {database}")
    print(f"User: {user}")

    cursor.close()
    connection.close()

except Exception as e:
    print("❌ PostgreSQL connection failed.")
    print("Error:", e)