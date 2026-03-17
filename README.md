**Hometown Highlights**

_A Flask-based web platform for discovering and reviewing local businesses_

**Overview**

Hometown Highlights is a full-stack web application designed to help users discover local businesses through category-based filtering, ratings, and personalized features. The platform emphasizes usability, clean backend design, and secure user interaction.

**Features**

Category Filtering – Browse businesses by type for faster discovery

Ratings & Reviews – View and submit feedback on businesses

Bookmarking – Save favorite locations for quick access

Bot Verification – Basic protection to prevent spam submissions

Responsive UI – Built with Bootstrap for cross-device compatibility

**Tech Stack**

  **Backend:**

  Python

  Flask

  **Frontend:**

  HTML, CSS

  Bootstrap

  **Data & Tools:**

  SQLite

  Git (version control)

**Design & Architecture**

Implemented a modular Flask structure for maintainability

Designed REST-style routes for handling user interactions

Focused on clean separation of frontend and backend logic

Prioritized readability, documentation, and scalability

**Security Considerations**

Basic bot detection for form submissions

Input validation to reduce invalid or harmful data

Structured backend logic to prevent common errors

**Installation & Setup**
# Clone the repository
git clone https://github.com/yourusername/hometown-highlights.git

# Navigate into the project
cd hometown-highlights

# (Optional) Create virtual environment
python -m venv venv
source venv/bin/activate  # Mac/Linux
venv\Scripts\activate     # Windows

# Install dependencies
pip install -r requirements.txt

# Run the app
python app.py

Then open:

http://127.0.0.1:5000/

**📈 Future Improvements**

Improve bot detection with CAPTCHA or ML-based filtering

Deploy to cloud (AWS, GCP, or Azure)

Integrate real-time data APIs

