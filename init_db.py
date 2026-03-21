import sqlite3
from pathlib import Path


ROOT = Path(__file__).parent
DATABASE_PATH = ROOT / "database.db"
SCHEMA_PATH = ROOT / "schema.sql"


def main():
    connection = sqlite3.connect(DATABASE_PATH)

    try:
        schema = SCHEMA_PATH.read_text(encoding="utf-8")
        connection.executescript(schema)
        connection.commit()
        print("База данных создана.")
    finally:
        connection.close()


if __name__ == "__main__":
    main()
