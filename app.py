# Core imports for database, web framework, and security
import sqlite3
from flask import Flask, render_template, request, session, url_for, redirect, g, jsonify, flash
from urllib.parse import urlparse
from flask_bcrypt import Bcrypt
from dotenv import load_dotenv
import os

# Custom validation utilities
from utils.input_validators import validate_business_form, validate_signup_form, sanitize_text
import random
import time

# Simple math captcha to prevent bot submissions
def generate_math_captcha():
    """Generate a simple math captcha, store the answer in session, and return question."""
    a = random.randint(1, 9)
    b = random.randint(1, 9)
    op = random.choice(['+', '-'])
    if op == '+':
        ans = a + b
    else:
        # Make sure we don't get negative results
        if a < b:
            a, b = b, a
        ans = a - b
    question = f"Solve: {a} {op} {b} = ?"
    # Store answer and timestamp in session for validation
    session['captcha_answer'] = str(ans)
    session['captcha_ts'] = int(time.time())
    return question


def check_math_captcha(user_input) -> bool:
    """Validate user input against stored captcha answer. Returns True if correct."""
    if not user_input:
        return False
    expected = session.get('captcha_answer')
    try:
        return str(int(user_input)) == str(expected)
    except Exception:
        return False

# Initialize Flask app with secret key for sessions
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret")
bcrypt = Bcrypt(app)

# Load environment variables from .env files
load_dotenv()
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), 'environment', '.env'))


def get_db_connection():
    """Open a SQLite connection to the local database file. Callers should close it."""
    conn = sqlite3.connect("data/myFirstBusiness.db")
    conn.row_factory = sqlite3.Row  # Access columns by name
    return conn


@app.route("/home", methods=["GET", "POST"])
def home():
    """Main home page showing business listings with filtering, sorting, search, and personalized recommendations."""
    conn = get_db_connection()

    # Handle favorite additions via POST
    if request.method == "POST" and "add_favorite" in request.form:
        user_id = session.get("user_id")
        if not user_id:
            conn.close()
            return render_template("login.html", error="Please log in to add favorites.", captcha_question=generate_math_captcha())
        try:
            business_id = int(request.form.get("business_id") or 0)
        except (TypeError, ValueError):
            conn.close()
            return render_template("home.html", items=[], items_count=0, error="Invalid business ID.")
        business = conn.execute("SELECT * FROM myFirstBusiness WHERE id = ?", (business_id,)).fetchone()
        if business:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO favorites (user_id, business_id, business_name, category, address, description)
                VALUES (?, ?, ?, ?, ?, ?)
                """, (user_id, business_id, business["name"], business["category"], business["address"], business["description"]))
            conn.commit()
        conn.close()
        return redirect(url_for("home"))

    # Route to add review form
    if request.method == "GET" and "add_review" in request.args:
        user_id = session.get("user_id")
        if not user_id:
            conn.close()
            return render_template("login.html", error="Please log in to add reviews.", captcha_question=generate_math_captcha())
        try:
            business_id = int(request.args.get("business_id") or 0)
            business = conn.execute("SELECT * FROM myFirstBusiness WHERE id = ?", (business_id,)).fetchone()
            conn.close()
            return render_template("add_review.html", business=business, business_id=business_id, captcha_question=generate_math_captcha())
        except (TypeError, ValueError):
            conn.close()
            return render_template("home.html", items=[], items_count=0, error="Invalid business ID.")

    # Route to view reviews for a business
    if request.method == "GET" and "view_review" in request.args:
        try:
            business_id = int(request.args.get("business_id") or 0)
            reviews = conn.execute("SELECT * FROM reviews WHERE business_id = ?", (business_id,)).fetchall()
            business = conn.execute("SELECT * FROM myFirstBusiness WHERE id = ?", (business_id,)).fetchone()
            conn.close()
            return render_template("reviews.html", reviews=reviews, business=business)
        except (TypeError, ValueError):
            conn.close()
            return render_template("home.html", items=[], items_count=0, error="Invalid business ID.")

    # Handle filtering by category
    items = None
    if request.method == "POST" and "category" in request.form:
        selected_category = request.form.get("category")
        if selected_category == "All":
            items = conn.execute("SELECT * FROM myFirstBusiness").fetchall()
        else:
            items = conn.execute("SELECT * FROM myFirstBusiness WHERE category = ?", (selected_category,)).fetchall()
    
    # Handle sorting options
    elif request.method == "POST" and "sort_by" in request.form:
        sort_by = request.form.get("sort_by")
        if sort_by == "Highest Rating":
            # Sort by average rating, putting unrated businesses last
            items = conn.execute("SELECT *, (SELECT AVG(rating) FROM reviews WHERE business_id = myFirstBusiness.id) as avg_rating FROM myFirstBusiness ORDER BY (avg_rating IS NULL), avg_rating DESC").fetchall()
        elif sort_by == "Most Reviewed":
            items = conn.execute(
                "SELECT * FROM myFirstBusiness ORDER BY (SELECT COUNT(*) FROM reviews WHERE reviews.business_id = myFirstBusiness.id) DESC"
            ).fetchall()
        elif sort_by == "Newest":
            items = conn.execute("SELECT * FROM myFirstBusiness ORDER BY id DESC").fetchall()
        elif sort_by == "Alphabetical":
            items = conn.execute("SELECT * FROM myFirstBusiness ORDER BY name ASC").fetchall()
        else:
            items = conn.execute("SELECT * FROM myFirstBusiness").fetchall()
    else:
        items = conn.execute("SELECT * FROM myFirstBusiness").fetchall()

    # Handle search queries
    if request.method == "GET" and "search" in request.args:
        search_query = request.args.get("search", "").strip()
        items = conn.execute("SELECT * FROM myFirstBusiness WHERE name LIKE ?", ('%' + search_query + '%',)).fetchall()

    # Generate personalized recommendations based on user preferences
    recommendations = []
    user_id = session.get("user_id")
    if user_id:
        # Get businesses user has already reviewed or viewed
        reviewed_rows = conn.execute("SELECT DISTINCT business_id FROM reviews WHERE user_id = ?", (user_id,)).fetchall()
        reviewed_ids = [r["business_id"] for r in reviewed_rows]

        viewed_rows = conn.execute("SELECT DISTINCT business_id FROM analytics WHERE user_id = ?", (user_id,)).fetchall()
        viewed_ids = [r["business_id"] for r in viewed_rows]

        exclude_ids = list(set(reviewed_ids + viewed_ids))

        # Recommendation algorithm: weighted score based on user preferences and ratings
        pref_weight = 0.6
        rating_weight = 0.4
        min_avg_rating = float(os.environ.get('MIN_RECOMMEND_RATING', '3.0'))
        base_query = """
        WITH user_pref AS (
            SELECT m.category, AVG(r.rating) AS pref
            FROM reviews r JOIN myFirstBusiness m ON r.business_id = m.id
            WHERE r.user_id = ?
            GROUP BY m.category
        )
        SELECT b.*, COALESCE(user_pref.pref, 0) * ? + COALESCE((SELECT AVG(rating) FROM reviews WHERE business_id = b.id), 0) * ? AS score
        FROM myFirstBusiness b
        LEFT JOIN user_pref ON b.category = user_pref.category
        """

        params = [user_id, pref_weight, rating_weight]
        # Exclude already interacted businesses and filter by minimum rating
        if exclude_ids:
            placeholders = ','.join('?' for _ in exclude_ids)
            base_query += f"WHERE b.id NOT IN ({placeholders})\n"
            params.extend(exclude_ids)
            base_query += "AND ((SELECT AVG(rating) FROM reviews WHERE business_id = b.id) IS NULL OR (SELECT AVG(rating) FROM reviews WHERE business_id = b.id) >= ?)\n"
            params.append(min_avg_rating)
        else:
            base_query += "WHERE ((SELECT AVG(rating) FROM reviews WHERE business_id = b.id) IS NULL OR (SELECT AVG(rating) FROM reviews WHERE business_id = b.id) >= ?)\n"
            params.append(min_avg_rating)

        # Use deterministic ordering (no RANDOM()) so results only change when
        # underlying ratings/analytics change. Tie-break by avg rating then id.
        base_query += "ORDER BY score DESC, (SELECT AVG(rating) FROM reviews WHERE business_id = b.id) DESC, b.id ASC LIMIT 5"
        recommendations = conn.execute(base_query, params).fetchall()
    else:
        # For non-logged-in users, show top-rated businesses
        # Deterministic top-rated selection for anonymous users; stable ordering
        # so recommendations don't change on every page render.
        recommendations = conn.execute(
            "SELECT *, (SELECT AVG(rating) FROM reviews WHERE business_id = myFirstBusiness.id) as avg_rating FROM myFirstBusiness "
            "WHERE (SELECT AVG(rating) FROM reviews WHERE business_id = myFirstBusiness.id) IS NULL OR (SELECT AVG(rating) FROM reviews WHERE business_id = myFirstBusiness.id) >= ? "
            "ORDER BY (avg_rating IS NULL), avg_rating DESC, id ASC LIMIT 5",
            (min_avg_rating,)
        ).fetchall()
        
    def attach_avg_ratings(conn, rows):
        """Efficiently attach average ratings and counts to business listings."""
        out = []
        if not rows:
            return out
        # Batch query for all ratings instead of individual queries
        ids = [r['id'] for r in rows]
        placeholders = ','.join('?' for _ in ids)
        query = f"SELECT business_id, AVG(rating) as avg_rating, COUNT(*) as cnt FROM reviews WHERE business_id IN ({placeholders}) GROUP BY business_id"
        stats = {}
        try:
            rows_stats = conn.execute(query, ids).fetchall()
            for s in rows_stats:
                stats[s['business_id']] = {'avg': s['avg_rating'], 'cnt': s['cnt']}
        except Exception:
            stats = {}
        # Attach rating data to each business
        for r in rows:
            d = dict(r)
            s = stats.get(d['id'], {'avg': None, 'cnt': 0})
            d['rating_avg'] = float(s['avg']) if s['avg'] is not None else None
            d['rating_count'] = int(s['cnt'] or 0)
            d['rating_pct'] = (d['rating_avg'] / 5.0 * 100) if d['rating_avg'] is not None else 0
            out.append(d)
        return out

    items = attach_avg_ratings(conn, items)
    recommendations = attach_avg_ratings(conn, recommendations)

    # Check if current user is an admin
    is_admin = False
    if user_id:
        try:
            user_row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        except Exception:
            user_row = None
        # Check database flag first
        try:
            if user_row and 'is_admin' in user_row.keys() and user_row['is_admin']:
                is_admin = True
        except Exception:
            is_admin = False
        # Fallback to environment variable list of admin usernames
        if not is_admin and user_row:
            admin_users = os.environ.get('ADMIN_USERS', '')
            admin_list = [u.strip() for u in admin_users.split(',') if u.strip()]
            try:
                if user_row['username'] in admin_list:
                    is_admin = True
            except Exception:
                pass

    # Get user's favorited businesses
    favorite_ids = set()
    if user_id:
        try:
            fav_rows = conn.execute("SELECT business_id FROM favorites WHERE user_id = ?", (user_id,)).fetchall()
            favorite_ids = set([r['business_id'] for r in fav_rows])
        except Exception:
            favorite_ids = set()

    items_count = len(items)
    conn.close()
    return render_template("home.html", items=items, items_count=items_count, recommendations=recommendations, is_admin=is_admin, favorite_ids=favorite_ids)


@app.route("/add_business", methods=["GET", "POST"])
def add_business():
    """Handle business submission form with captcha validation and duplicate checking."""
    print("Request method:", request.method)
    if request.method == "POST":
        app.logger.info("add_business POST received")
        # Verify captcha first
        user_captcha = request.form.get('captcha')
        if not check_math_captcha(user_captcha):
            return render_template("add_business.html", error="Incorrect captcha. Please try again.", captcha_question=generate_math_captcha())
        
        # Validate all form fields
        valid, err = validate_business_form(request.form)
        if not valid:
            return render_template("add_business.html", error=err, captcha_question=generate_math_captcha())

        # Sanitize inputs to prevent XSS
        name = sanitize_text(request.form.get('name'))
        category = sanitize_text(request.form.get('category'))
        address = sanitize_text(request.form.get('address'))
        description = sanitize_text(request.form.get('description'))
        deals = sanitize_text(request.form.get('deals'))
        deals_code = sanitize_text(request.form.get('deal_code'))
        deals_expiry = sanitize_text(request.form.get('deal_expiration'))
        
        conn = get_db_connection()
        # Check for duplicate business (same name and address)
        try:
            existing = conn.execute(
                "SELECT id FROM myFirstBusiness WHERE LOWER(TRIM(name)) = LOWER(TRIM(?)) AND LOWER(TRIM(address)) = LOWER(TRIM(?)) LIMIT 1",
                (name, address)
            ).fetchone()
        except Exception:
            existing = None
        if existing:
            conn.close()
            return render_template("add_business.html", error="A business with that name and address already exists.", captcha_question=generate_math_captcha())
        
        # Insert new business and associated deal
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO myFirstBusiness (name, category, address, description, deals, deals_code, deal_expiry)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (name, category, address, description, deals, deals_code, deals_expiry))
        conn.commit()
        business_id = cursor.lastrowid
        app.logger.info("Inserted business id=%s name=%s", business_id, name)
        cursor.execute("""
            INSERT INTO deals (business_id, business_name, deal_description, deal_code, deal_expiration)
            VALUES (?, ?, ?, ?, ?)
            """, (business_id, name, deals, deals_code, deals_expiry))
        conn.commit()
        conn.close()
        return redirect(url_for("home"))

    return render_template("add_business.html", captcha_question=generate_math_captcha())


@app.route('/validate_captcha', methods=['POST'])
def validate_captcha():
    """AJAX endpoint for client-side captcha validation."""
    user_captcha = request.form.get('captcha')
    if check_math_captcha(user_captcha):
        return jsonify({'valid': True})
    # Generate new captcha if validation fails
    new_q = generate_math_captcha()
    return jsonify({'valid': False, 'message': 'Incorrect captcha. Please try again.', 'captcha_question': new_q})


@app.route('/admin/analytics')
def admin_analytics():
    """Admin-only analytics dashboard showing business view and review statistics."""
    user_id = session.get('user_id')
    if not user_id:
        return render_template('login.html', error='Please log in as an admin to view analytics.')

    conn = get_db_connection()
    try:
        user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    except Exception:
        user = None

    # Verify admin status (check both database flag and environment config)
    is_admin = False
    try:
        if user and 'is_admin' in user.keys() and user['is_admin']:
            is_admin = True
    except Exception:
        is_admin = False

    if not is_admin and user:
        admin_users = os.environ.get('ADMIN_USERS', '')
        admin_list = [u.strip() for u in admin_users.split(',') if u.strip()]
        if user['username'] in admin_list:
            is_admin = True

    if not is_admin:
        # If not admin, store an error message in session and redirect to full home
        # so the user sees the standard home page layout with the error displayed.
        session['error_message'] = 'Admin privileges required to view this page.'
        conn.close()
        return redirect(url_for('home'))

    # Fetch analytics data sorted by engagement
    rows = conn.execute("SELECT a.id, a.business_id, a.user_id, a.views, a.review_count, m.name as business_name FROM analytics a LEFT JOIN myFirstBusiness m ON a.business_id = m.id ORDER BY a.views DESC, a.review_count DESC").fetchall()
    conn.close()
    return render_template('admin_analytics.html', analytics=rows)


@app.route("/deals")
def deals():
    """Show all available deals across businesses."""
    conn = get_db_connection()
    deals = conn.execute("SELECT * FROM deals").fetchall()
    conn.close()
    return render_template("deals.html", deals=deals)


@app.route('/deals/<int:business_id>')
def business_deals(business_id):
    """Show deals for a specific business."""
    conn = get_db_connection()
    business = conn.execute("SELECT * FROM myFirstBusiness WHERE id = ?", (business_id,)).fetchone()
    deals = conn.execute("SELECT * FROM deals WHERE business_id = ?", (business_id,)).fetchall()
    conn.close()
    return render_template('deals.html', deals=deals, business=business)


@app.route('/delete_business/<int:business_id>', methods=['POST'])
def delete_business(business_id):
    """Admin-only: delete a business and all related data (reviews, deals, favorites, analytics)."""
    user_id = session.get('user_id')
    if not user_id:
        return render_template('login.html', error='Please log in as an admin to delete businesses.', captcha_question=generate_math_captcha())

    conn = get_db_connection()
    try:
        user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    except Exception:
        user = None

    # Verify admin privileges
    is_admin = False
    try:
        if user and 'is_admin' in user.keys() and user['is_admin']:
            is_admin = True
    except Exception:
        is_admin = False

    if not is_admin and user:
        admin_users = os.environ.get('ADMIN_USERS', '')
        admin_list = [u.strip() for u in admin_users.split(',') if u.strip()]
        if user and 'username' in user.keys() and user['username'] in admin_list:
            is_admin = True

    if not is_admin:
        conn.close()
        return render_template('login.html', error='Admin privileges required to delete businesses.', captcha_question=generate_math_captcha())

    cursor = conn.cursor()
    try:
        # Delete in order to respect foreign key constraints
        cursor.execute("DELETE FROM reviews WHERE business_id = ?", (business_id,))
        cursor.execute("DELETE FROM deals WHERE business_id = ?", (business_id,))
        cursor.execute("DELETE FROM favorites WHERE business_id = ?", (business_id,))
        cursor.execute("DELETE FROM analytics WHERE business_id = ?", (business_id,))
        cursor.execute("DELETE FROM myFirstBusiness WHERE id = ?", (business_id,))
        conn.commit()
    except Exception:
        conn.rollback()
        app.logger.exception('Failed to delete business %s', business_id)
    finally:
        conn.close()

    return redirect(url_for('home'))


@app.route('/add_deal', methods=['GET', 'POST'])
@app.route('/add_deal/<int:business_id>', methods=['GET', 'POST'])
def add_deal(business_id=None):
    # Admin-protected: show a form to create a new deal, optionally tied to a business.
    user_id = session.get('user_id')
    if not user_id:
        return render_template('login.html', error='Please log in to add deals.', captcha_question=generate_math_captcha())

    conn = get_db_connection()
    try:
        user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    except Exception:
        user = None

    is_admin = False
    try:
        if user and 'is_admin' in user.keys() and user['is_admin']:
            is_admin = True
    except Exception:
        is_admin = False
    if not is_admin and user:
        admin_users = os.environ.get('ADMIN_USERS', '')
        admin_list = [u.strip() for u in admin_users.split(',') if u.strip()]
        if 'username' in user.keys() and user['username'] in admin_list:
            is_admin = True

    if not is_admin:
        conn.close()
        return render_template('home.html', items=[], items_count=0, error='Admin privileges required to add deals.')

    # If POST, insert the deal
    if request.method == 'POST':
        # business_id may come from URL or form
        try:
            form_business_id = int(request.form.get('business_id') or business_id or 0) or None
        except Exception:
            form_business_id = None

        deal_description = request.form.get('deal_description') or ''
        deal_code = request.form.get('deal_code') or ''
        deal_expiration = request.form.get('deal_expiration') or None

        # If a business_id was provided, ensure it exists and capture its name
        business_name = ''
        if form_business_id:
            b = conn.execute("SELECT * FROM myFirstBusiness WHERE id = ?", (form_business_id,)).fetchone()
            if not b:
                conn.close()
                return render_template('add_deal.html', error='Business not found.', business_id=form_business_id)
            business_name = b['name']

        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO deals (business_id, business_name, deal_description, deal_code, deal_expiration) VALUES (?, ?, ?, ?, ?)",
            (form_business_id, business_name, deal_description, deal_code, deal_expiration)
        )
        conn.commit()
        conn.close()
        if form_business_id:
            return redirect(url_for('business_deals', business_id=form_business_id))
        return redirect(url_for('deals'))

    # GET: render form. If business_id provided, load business for context.
    business = None
    try:
        if business_id is not None:
            business = conn.execute("SELECT * FROM myFirstBusiness WHERE id = ?", (business_id,)).fetchone()
    finally:
        conn.close()

    return render_template('add_deal.html', business=business, business_id=business_id)


@app.route('/favorite', methods=['POST'])
def toggle_favorite():
    """Add or remove a business from user's favorites."""
    user_id = session.get('user_id')
    if not user_id:
        return render_template('login.html', error='Please log in to favorite businesses.', captcha_question=generate_math_captcha())

    try:
        business_id = int(request.form.get('business_id') or 0)
    except Exception:
        return redirect(request.referrer or url_for('home'))

    conn = get_db_connection()
    try:
        existing = conn.execute("SELECT * FROM favorites WHERE user_id = ? AND business_id = ?", (user_id, business_id)).fetchone()
    except Exception:
        existing = None

    cursor = conn.cursor()
    if existing:
        # Remove from favorites
        cursor.execute("DELETE FROM favorites WHERE id = ?", (existing['id'],))
        conn.commit()
        conn.close()
        return redirect(request.referrer or url_for('favorites'))
    else:
        # Add to favorites
        business = conn.execute("SELECT * FROM myFirstBusiness WHERE id = ?", (business_id,)).fetchone()
        if business:
            cursor.execute(
                "INSERT INTO favorites (user_id, business_id, business_name, category, address, description) VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, business_id, business['name'], business['category'], business['address'], business['description'])
            )
            conn.commit()
        conn.close()
        return redirect(request.referrer or url_for('home'))

@app.route("/favorites")
def favorites():
    """Display user's favorited businesses."""
    user_id = session.get("user_id")
    if not user_id:
        return render_template("login.html", error="Please log in to view favorites.", captcha_question=generate_math_captcha())
    conn = get_db_connection()
    favorites = conn.execute("SELECT * FROM favorites WHERE user_id = ?", (user_id,)).fetchall()
    conn.close()
    return render_template("favorites.html", favorites=favorites)

@app.route("/", methods=["GET", "POST"])
def login():
    """Authenticate user and create session."""
    print("Request method:", request.method)
    if request.method == "POST":
        # Verify captcha before processing login
        user_captcha = request.form.get('captcha')
        if not check_math_captcha(user_captcha):
            return render_template("login.html", error="Incorrect captcha. Please try again.", captcha_question=generate_math_captcha())

        username = request.form['username']
        password = request.form['password']
        conn = get_db_connection()
        user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        conn.close()
        
        # Verify password hash
        if user and bcrypt.check_password_hash(user['password_hash'], password):
            # Set session variables for logged-in user
            session['user_id'] = user['id']
            try:
                session['username'] = user['username'] if 'username' in user.keys() else ''
            except Exception:
                session['username'] = ''
            try:
                session['first_name'] = user['first_name'] if 'first_name' in user.keys() else ''
            except Exception:
                session['first_name'] = ''
            try:
                session['last_name'] = user['last_name'] if 'last_name' in user.keys() else ''
            except Exception:
                session['last_name'] = ''
            return redirect(url_for("home"))
        else:
            return render_template("login.html", error="Invalid username or password.", captcha_question=generate_math_captcha())
    else:
        return render_template("login.html", captcha_question=generate_math_captcha())


@app.route('/logout')
def logout():
    """Clear user session and return to login."""
    session.clear()
    return redirect(url_for('login'))

@app.route("/signup", methods=["GET", "POST"])
def signup():
    """Create new user account with validation and duplicate checking."""
    conn = get_db_connection()
    try:
        if request.method == "POST":
            app.logger.info("Signup POST received: form keys=%s", list(request.form.keys()))
            app.logger.info("Signup processing")
            # Verify captcha
            user_captcha = request.form.get('captcha')
            if not check_math_captcha(user_captcha):
                conn.close()
                return render_template("signup.html", error="Incorrect captcha. Please try again.", captcha_question=generate_math_captcha(), invalid_fields={}, form=request.form)
            
            # Validate all signup fields (server-side)
            valid, err = validate_signup_form(request.form)
            if not valid:
                # Map common validation messages to field-level indicators for the template
                invalid_fields = {}
                msg = (err or '').lower()
                if 'email' in msg:
                    invalid_fields['email'] = True
                if 'phone' in msg or 'phone number' in msg:
                    invalid_fields['phone_number'] = True
                conn.close()
                return render_template("signup.html", error=err, captcha_question=generate_math_captcha(), invalid_fields=invalid_fields, form=request.form)

            # Sanitize and hash password
            username = sanitize_text(request.form.get("username"))
            password_hash = bcrypt.generate_password_hash(request.form.get("password")).decode('utf-8')
            phone_number = sanitize_text(request.form.get("phone_number"))
            email = sanitize_text(request.form.get("email"))
            first_name = sanitize_text(request.form.get("first_name"))
            last_name = sanitize_text(request.form.get("last_name"))
            
            cursor = conn.cursor()
            # Check if name columns exist and add them if missing (migration safety)
            try:
                cols = [r['name'] for r in conn.execute("PRAGMA table_info(users)").fetchall()]
            except Exception:
                cols = []
            if 'first_name' not in cols:
                try:
                    cursor.execute("ALTER TABLE users ADD COLUMN first_name TEXT")
                except Exception:
                    pass
            if 'last_name' not in cols:
                try:
                    cursor.execute("ALTER TABLE users ADD COLUMN last_name TEXT")
                except Exception:
                    pass
            
            # Insert new user
            cursor.execute("""
                INSERT INTO users (username, password_hash, phone_number, email, first_name, last_name)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (username, password_hash, phone_number, email, first_name, last_name))
            conn.commit()
            conn.close()
            return render_template("login.html", success="Account created successfully! Please log in.", captcha_question=generate_math_captcha())
    except sqlite3.IntegrityError as e:
        # Handle unique constraint violations with specific error messages
        conn.close()
        err = str(e)
        if "UNIQUE constraint failed: users.username" in err:
            error_message = "Username already exists. Please choose a different one."
        elif "UNIQUE constraint failed: users.phone_number" in err:
            error_message = "Phone number already exists. Please use a different one."
        elif "UNIQUE constraint failed: users.email" in err:
            error_message = "Email already exists. Please use a different one."
        else:
            error_message = "Database integrity error."
        # Mark the relevant field(s) as invalid for clearer feedback
        invalid_fields = {}
        if 'username' in error_message.lower():
            invalid_fields['username'] = True
        if 'phone' in error_message.lower():
            invalid_fields['phone_number'] = True
        if 'email' in error_message.lower():
            invalid_fields['email'] = True
        return render_template("signup.html", error=error_message, captcha_question=generate_math_captcha(), invalid_fields=invalid_fields, form=request.form)

    question = generate_math_captcha()
    # Ensure template always receives `form` and `invalid_fields` to avoid undefined errors
    return render_template("signup.html", captcha_question=question, form={}, invalid_fields={})

@app.route("/add_review", methods=["GET", "POST"])
@app.route("/add_review/<int:business_id>", methods=["GET", "POST"])
def add_review(business_id=None):
    """Submit a review for a business with captcha validation and analytics tracking."""
    if request.method == "POST":
        user_id = session.get("user_id")
        if not user_id:
            return render_template("login.html", error="Please log in to add reviews.", captcha_question=generate_math_captcha())
        
        business_id = int(request.form.get("business_id") or business_id)
        app.logger.info("add_review POST received for business_id=%s", business_id)
        
        # Verify captcha
        user_captcha = request.form.get('captcha')
        if not check_math_captcha(user_captcha):
            conn = get_db_connection()
            business = conn.execute("SELECT * FROM myFirstBusiness WHERE id = ?", (business_id,)).fetchone() if business_id else None
            conn.close()
            return render_template("add_review.html", business=business, business_id=business_id, error="Incorrect captcha. Please try again.", captcha_question=generate_math_captcha(), reviewer_name=request.form.get("reviewer_name"))

        # Sanitize and validate review fields
        reviewer_name = sanitize_text(request.form.get("reviewer_name"))
        title = sanitize_text(request.form.get("title") or '')
        try:
            rating = int(request.form.get("rating"))
            if rating < 1 or rating > 5:
                raise ValueError()
        except Exception:
            conn = get_db_connection()
            business = conn.execute("SELECT * FROM myFirstBusiness WHERE id = ?", (business_id,)).fetchone() if business_id else None
            conn.close()
            return render_template("add_review.html", business=business, error="Rating must be an integer between 1 and 5.", captcha_question=generate_math_captcha())
        comments = sanitize_text(request.form.get("comment") or request.form.get("comments"))
        
        conn = get_db_connection()
        cursor = conn.cursor()
        # Add missing review columns if they don't exist (migration safety)
        try:
            cols = [r['name'] for r in conn.execute("PRAGMA table_info(reviews)").fetchall()]
        except Exception:
            cols = []
        try:
            if 'title' not in cols:
                cursor.execute("ALTER TABLE reviews ADD COLUMN title TEXT")
            if 'reviewer_name' not in cols:
                cursor.execute("ALTER TABLE reviews ADD COLUMN reviewer_name TEXT")
            conn.commit()
        except Exception:
            pass

        # Insert the review
        cursor.execute("""
            INSERT INTO reviews (business_id, user_id, rating, comment, title, reviewer_name)
            VALUES (?, ?, ?, ?, ?, ?)
            """, (business_id, user_id, rating, comments, title, reviewer_name))
        conn.commit()
        
        # Update analytics to track review activity
        try:
            existing = conn.execute("SELECT * FROM analytics WHERE user_id = ? AND business_id = ?",
                                    (user_id, business_id)).fetchone()
            if existing:
                cursor.execute("UPDATE analytics SET review_count = review_count + 1 WHERE id = ?", (existing["id"],))
            else:
                cursor.execute("INSERT INTO analytics (business_id, user_id, views, review_count) VALUES (?, ?, 0, 1)",
                               (business_id, user_id))
            conn.commit()
        except Exception:
            app.logger.exception('Failed to update analytics for review')
        finally:
            conn.close()
        return redirect(url_for("home"))
    
    # GET request: show the review form
    conn = get_db_connection()
    business = None
    reviewer_name = None
    try:
        if business_id is not None:
            business = conn.execute("SELECT * FROM myFirstBusiness WHERE id = ?", (business_id,)).fetchone()
        # Pre-fill reviewer name from user's profile
        user_id = session.get('user_id')
        if user_id:
            try:
                user_row = conn.execute("SELECT username, first_name, last_name FROM users WHERE id = ?", (user_id,)).fetchone()
                if user_row:
                    try:
                        fname = user_row['first_name'] if 'first_name' in user_row.keys() and user_row['first_name'] else ''
                        lname = user_row['last_name'] if 'last_name' in user_row.keys() and user_row['last_name'] else ''
                        if fname or lname:
                            reviewer_name = (fname + ' ' + lname).strip()
                        else:
                            reviewer_name = user_row['username']
                    except Exception:
                        reviewer_name = user_row['username'] if 'username' in user_row.keys() else None
            except Exception:
                reviewer_name = None
    finally:
        conn.close()
    return render_template("add_review.html", business=business, captcha_question=generate_math_captcha(), reviewer_name=reviewer_name)

@app.route("/reviews/<int:business_id>", methods=["GET", "POST"])
def view_reviews(business_id):
    """View all reviews for a business with sorting options and analytics tracking."""
    conn = get_db_connection()
    sort_by = None
    if request.method == 'POST' and 'sort_by' in request.form:
        sort_by = request.form.get('sort_by')

    # Apply sorting to reviews
    if sort_by == 'Highest Rating':
        reviews = conn.execute("SELECT * FROM reviews WHERE business_id = ? ORDER BY rating DESC", (business_id,)).fetchall()
    elif sort_by == 'Lowest Rating':
        reviews = conn.execute("SELECT * FROM reviews WHERE business_id = ? ORDER BY rating ASC", (business_id,)).fetchall()
    elif sort_by == 'Oldest':
        reviews = conn.execute("SELECT * FROM reviews WHERE business_id = ? ORDER BY id ASC", (business_id,)).fetchall()
    else:
        # Default: newest first
        reviews = conn.execute("SELECT * FROM reviews WHERE business_id = ? ORDER BY id DESC", (business_id,)).fetchall()
    
    business = conn.execute("SELECT * FROM myFirstBusiness WHERE id = ?", (business_id,)).fetchone()

    # Track view in analytics for logged-in users
    user_id = session.get("user_id")
    try:
        if user_id:
            existing = conn.execute("SELECT * FROM analytics WHERE user_id = ? AND business_id = ?",
                                    (user_id, business_id)).fetchone()
            cursor = conn.cursor()
            if existing:
                cursor.execute("UPDATE analytics SET views = views + 1 WHERE id = ?", (existing["id"],))
            else:
                cursor.execute("INSERT INTO analytics (business_id, user_id, views, review_count) VALUES (?, ?, 1, 0)",
                               (business_id, user_id))
            conn.commit()
    finally:
        conn.close()
    return render_template("reviews.html", reviews=reviews, business_id=business_id, business=business, sort_by=sort_by)


@app.route("/click/<int:business_id>")
def track_click(business_id):
    """Redirect helper for navigating to business reviews."""
    return redirect(url_for('view_reviews', business_id=business_id))

@app.route('/help')
def help_page():
    """Display help and instructions page."""
    return render_template('help.html')

# Run the development server
if __name__ == "__main__":
    app.run(debug=True)
