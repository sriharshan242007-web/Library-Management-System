from datetime import datetime
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from pymongo.errors import DuplicateKeyError, PyMongoError
import database

app = Flask(__name__)
app.config["SECRET_KEY"] = "library-demo-secret"

try:
    database.connect_database()
    DB_ERROR = None
except Exception as e:
    DB_ERROR = str(e)

@app.context_processor
def inject_globals():
    return {
        "db_error": DB_ERROR,
        "db_status_msg": database.DB_STATUS_MSG if not DB_ERROR else DB_ERROR,
        "is_mock": getattr(database, "IS_MOCK", False)
    }

@app.route("/")
def home():
    if DB_ERROR:
        return render_template(
            "home.html",
            books=[],
            categories=[],
            summary={},
            db_error=DB_ERROR
        )

    books = [
        database.serialize_book(book)
        for book in database.books.find().sort("title", 1)
    ]
    categories = sorted(list(set(database.books.distinct("category"))))
    summary = database.library_summary()

    return render_template(
        "home.html",
        books=books,
        categories=categories,
        summary=summary,
        db_error=None
    )

@app.get("/api/books")
def api_books():
    if DB_ERROR:
        return jsonify({"error": DB_ERROR}), 500
    q = request.args.get("q", "").strip()
    category = request.args.get("category", "").strip()
    query = {}
    if q:
        query["$or"] = [
            {"title": {"$regex": q, "$options": "i"}},
            {"author": {"$regex": q, "$options": "i"}},
            {"isbn": {"$regex": q, "$options": "i"}}
        ]
    if category:
        query["category"] = category
    result = [database.serialize_book(b) for b in database.books.find(query).sort("title", 1)]
    return jsonify(result)

@app.post("/api/borrow")
def api_borrow():
    if DB_ERROR:
        return jsonify({"success": False, "message": DB_ERROR}), 500
    data = request.get_json(silent=True) or request.form
    name = str(data.get("name", "")).strip()
    student_id = str(data.get("student_id", "")).strip()
    email = str(data.get("email", "")).strip().lower()
    phone = str(data.get("phone", "")).strip()
    department = str(data.get("department", "Student")).strip() or "Student"
    book_id = str(data.get("book_id", "")).strip()

    if not name or not student_id or not email or not book_id:
        return jsonify({"success": False, "message": "Please complete all required fields (Name, Student ID, Email, Book)."}), 400

    book = database.books.find_one({"book_id": book_id})
    if not book:
        return jsonify({"success": False, "message": "Selected book was not found in database."}), 404

    # Check if member exists by email or student_id
    member = database.members.find_one({"$or": [{"email": email}, {"student_id": student_id}]})
    if member:
        member_id = member["member_id"]
        database.members.update_one(
            {"member_id": member_id},
            {"$set": {"name": name, "phone": phone, "department": department, "student_id": student_id, "email": email}}
        )
    else:
        try:
            member_id = database.next_id("M", "member")
            database.members.insert_one({
                "member_id": member_id,
                "name": name,
                "student_id": student_id,
                "department": department,
                "email": email,
                "phone": phone,
                "joined_on": datetime.now()
            })
        except DuplicateKeyError:
            member = database.members.find_one({"$or": [{"email": email}, {"student_id": student_id}]})
            member_id = member["member_id"] if member else None

    if not member_id:
        return jsonify({"success": False, "message": "Could not create or retrieve member record."}), 500

    ok, result = database.create_issue(book_id, member_id)
    if not ok:
        return jsonify({"success": False, "message": result}), 409

    due_date_str = result["due_date"].strftime("%d %b %Y") if isinstance(result["due_date"], datetime) else str(result["due_date"])
    return jsonify({
        "success": True,
        "message": "Book borrowed successfully.",
        "issue_id": result["issue_id"],
        "book": book["title"],
        "due_date": due_date_str
    })

@app.route("/admin")
def admin():
    if DB_ERROR:
        return render_template("admin.html", summary={}, books=[], issues=[], members=[], member_map={}, db_error=DB_ERROR)

    raw_books = [database.serialize_book(b) for b in database.books.find().sort("title", 1)]
    raw_members = [database.serialize_member(m) for m in database.members.find().sort("name", 1)]
    raw_issues = [database.serialize_issue(i) for i in database.issues.find().sort("issue_date", -1)]
    
    member_map = {m["member_id"]: m for m in raw_members}
    book_map = {b["book_id"]: b for b in raw_books}

    # Annotate issues with book title & member name
    for i in raw_issues:
        i["book_title"] = book_map.get(i["book_id"], {}).get("title", i["book_id"])
        i["member_name"] = member_map.get(i["member_id"], {}).get("name", i["member_id"])

    return render_template(
        "admin.html",
        summary=database.library_summary(),
        books=raw_books,
        members=raw_members,
        issues=raw_issues,
        member_map=member_map,
        db_error=None
    )

@app.post("/admin/seed")
def seed():
    if not DB_ERROR:
        count = database.seed_sample_data()
        flash(f"{count} sample book(s) added successfully.", "success")
    return redirect(url_for("admin"))

@app.post("/admin/books/add")
def add_book():
    try:
        title = request.form.get("title", "").strip()
        author = request.form.get("author", "").strip()
        category = request.form.get("category", "").strip()
        isbn = request.form.get("isbn", "").strip()
        year_str = request.form.get("year", "").strip()
        copies_str = request.form.get("copies", "").strip()

        if not title or not author or not category or not isbn or not year_str or not copies_str:
            flash("All fields are required to add a book.", "error")
            return redirect(url_for("admin"))

        year = int(year_str)
        copies = int(copies_str)

        if copies <= 0:
            flash("Total copies must be at least 1.", "error")
            return redirect(url_for("admin"))

        if database.books.find_one({"isbn": isbn}):
            flash("A book with this ISBN already exists in inventory.", "error")
            return redirect(url_for("admin"))

        b_id = database.next_id("B", "book")
        database.books.insert_one({
            "book_id": b_id,
            "title": title,
            "author": author,
            "category": category,
            "isbn": isbn,
            "published_year": year,
            "total_copies": copies,
            "available_copies": copies,
            "added_on": datetime.now()
        })
        flash(f"Book '{title}' added successfully (ID: {b_id}).", "success")
    except ValueError:
        flash("Invalid year or copies entered. Please enter valid numbers.", "error")
    except DuplicateKeyError:
        flash("ISBN already exists in database.", "error")
    except Exception as e:
        flash(f"Could not add book: {e}", "error")

    return redirect(url_for("admin"))

@app.post("/admin/books/delete/<book_id>")
def delete_book_route(book_id):
    ok, msg = database.delete_book(book_id)
    flash(msg, "success" if ok else "error")
    return redirect(url_for("admin"))

@app.post("/admin/return/<issue_id>")
def return_book(issue_id):
    ok, result = database.return_issue(issue_id)
    if ok:
        fine_msg = f" Fine: Rs.{result['fine']} ({result['late_days']} late day(s))." if result['fine'] > 0 else ""
        flash(f"Book returned successfully.{fine_msg}", "success")
    else:
        flash(result, "error")
    return redirect(url_for("admin"))

if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)
