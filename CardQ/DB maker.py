import sqlite3
import xml.etree.ElementTree as ET

# Parse the XML data
tree = ET.parse("data.xml")
root = tree.getroot()

# Connect to the database
conn = sqlite3.connect("cards.db")
cursor = conn.cursor()

# Create tables
cursor.execute(
    """
    CREATE TABLE IF NOT EXISTS cards (
        id INTEGER PRIMARY KEY ,
        name TEXT NOCASE,
        type TEXT NOCASE,
        motto TEXT NOCASE,
        category TEXT NOCASE,
        region TEXT NOCASE,
        flag TEXT NOCASE,
        card_category TEXT NOCASE,
        description TEXT NOCASE
    )
"""
)

cursor.execute(
    """
    CREATE TABLE IF NOT EXISTS badges (
        card_id INTEGER,
        badge TEXT,
        FOREIGN KEY (card_id) REFERENCES cards (id)
    )
"""
)

cursor.execute(
    """
    CREATE TABLE IF NOT EXISTS trophies (
        card_id INTEGER,
        type TEXT,
        value TEXT,
        FOREIGN KEY (card_id) REFERENCES cards (id)
    )
"""
)

# Insert data into tables
for set_element in root.findall("SET"):
    for card_element in set_element.findall("CARD"):
        card_id = card_element.find("ID").text
        name = card_element.find("NAME").text
        card_type = card_element.find("TYPE").text
        motto = card_element.find("MOTTO").text
        category = card_element.find("CATEGORY").text
        region = card_element.find("REGION").text
        flag = card_element.find("FLAG").text
        card_category = card_element.find("CARDCATEGORY").text
        description = card_element.find("DESCRIPTION").text

        # Insert card data
        cursor.execute(
            """
            INSERT INTO cards (id, name, type, motto, category, region, flag, card_category, description)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                card_id,
                name,
                card_type,
                motto,
                category,
                region,
                flag,
                card_category,
                description,
            ),
        )

        # Insert badge data
        badges = card_element.find("BADGES")
        if badges is not None:
            for badge_element in badges.findall("BADGE"):
                badge = badge_element.text
                cursor.execute(
                    """
                    INSERT INTO badges (card_id, badge)
                    VALUES (?, ?)
                """,
                    (card_id, badge),
                )

        # Insert trophy data
        trophies = card_element.find("TROPHIES")
        if trophies is not None:
            for trophy_element in trophies.findall("TROPHY"):
                trophy_type = trophy_element.get("type")
                trophy_value = trophy_element.text
                cursor.execute(
                    """
                    INSERT INTO trophies (card_id, type, value)
                    VALUES (?, ?, ?)
                """,
                    (card_id, trophy_type, trophy_value),
                )

# Commit the changes and close the connection
conn.commit()
conn.close()
