import sqlite3

# Connect to SQLite database (creates file if it doesn't exist)
conn = sqlite3.connect("data/myFirstBusiness.db")

# Create a cursor object to execute SQL commands
cursor = conn.cursor()

# Create main business table
cursor.execute("""
CREATE TABLE IF NOT EXISTS myFirstBusiness (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    address TEXT NOT NULL,
    description TEXT,
    deals TEXT,
    deals_code TEXT,
    deal_expiry DATE
    )
""")

# Create users table with unique constraints
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    phone_number INTEGER NOT NULL UNIQUE,
    email TEXT NOT NULL UNIQUE,
    favorites TEXT   -- store user favorites as serialized list/string
    )
""")

# Create deals table linked to businesses
cursor.execute("""
CREATE TABLE IF NOT EXISTS deals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    business_id INTEGER NOT NULL,
    business_name TEXT NOT NULL,
    deal_description TEXT,
    deal_code TEXT,
    deal_expiration DATE,
    FOREIGN KEY (business_id) REFERENCES myFirstBusiness (id),
    FOREIGN KEY (deal_description) REFERENCES myFirstBusiness (deals),
    FOREIGN KEY (business_name) REFERENCES myFirstBusiness (name),
    FOREIGN KEY (deal_code) REFERENCES myFirstBusiness (deals_code),
    FOREIGN KEY (deal_expiration) REFERENCES myFirstBusiness (deal_expiry)
    )
""")

# Favorites table for many-to-many relationship between users and businesses
cursor.execute("""
CREATE TABLE IF NOT EXISTS favorites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    business_id INTEGER NOT NULL,
    business_name TEXT NOT NULL,
    category TEXT,
    address TEXT,
    description TEXT,
    FOREIGN KEY (user_id) REFERENCES users (id),
    FOREIGN KEY (business_id) REFERENCES myFirstBusiness (id),
    FOREIGN KEY (business_name) REFERENCES myFirstBusiness (name),
    FOREIGN KEY (category) REFERENCES myFirstBusiness (category),
    FOREIGN KEY (address) REFERENCES myFirstBusiness (address),
    FOREIGN KEY (description) REFERENCES myFirstBusiness (description)
    )
""")

# Reviews table linking users and businesses, with rating validation
cursor.execute("""
CREATE TABLE IF NOT EXISTS reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    business_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    rating INTEGER CHECK(rating >= 1 AND rating <= 5),
    comment TEXT,
    FOREIGN KEY (business_id) REFERENCES myFirstBusiness (id),
    FOREIGN KEY (user_id) REFERENCES users (id)
    )
""")

# Analytics table to track views and review counts per user/business
cursor.execute("""
CREATE TABLE IF NOT EXISTS analytics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    business_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    views INTEGER DEFAULT 0,
    review_count INTEGER DEFAULT 0,
    FOREIGN KEY (business_id) REFERENCES myFirstBusiness (id),
    FOREIGN KEY (user_id) REFERENCES users (id)
    )
""")

# Recommendations table storing personalized suggestions for users
cursor.execute("""
CREATE TABLE IF NOT EXISTS recommendations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    recommended_business_id INTEGER NOT NULL,
    reason TEXT,
    FOREIGN KEY (user_id) REFERENCES users (id),
    FOREIGN KEY (recommended_business_id) REFERENCES myFirstBusiness (id)
    )           
""")

# Sample businesses to pre-populate the database
sample_data = [
    ("Sunrise Coffee", "Food & Beverage", "123 Main St", "Cozy local coffee shop with fresh pastries.", "10% off lattes", "LATTE10", "12/5/2026"),
    ("TechFix Repair", "Retail", "45 Oak Ave", "Phone and laptop repair specialists.", "Free diagnostics", "DIAGFREE", "12/5/2026"),
    ("GreenLeaf Boutique", "Retail", "78 Pine Rd", "Eco-friendly clothing and accessories.", "Buy 1 Get 1 50% Off", "B1G150", "12/5/2026"),
    ("Bella’s Bakery", "Food & Beverage", "22 Maple St", "Fresh breads, cakes, and cookies daily.", "Free cookie with any purchase", "COOKIEFREE", "12/5/2026"),
    ("Hometown Auto", "Services", "90 Elm Blvd", "Trusted local auto repair shop.", "15% off oil changes", "OIL15", "12/5/2026")
]

# Insert sample businesses into main business table
cursor.executemany("""
INSERT INTO myFirstBusiness (name, category, address, description, deals, deals_code, deal_expiry)
VALUES (?, ?, ?, ?, ?, ?, ?)
""", sample_data)

# Commit changes so far
conn.commit()

# Populate deals table using data from businesses that have deals
cursor.execute("""
INSERT INTO deals (business_id, business_name, deal_description, deal_code, deal_expiration)
SELECT id, name, deals, deals_code, deal_expiry 
FROM myFirstBusiness
WHERE deals IS NOT NULL AND TRIM(deals) <> ''          
""")

# Commit final changes
conn.commit()

# Close the database connection
conn.close()
