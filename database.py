import os
from datetime import datetime, timedelta, date
from dotenv import load_dotenv
from pymongo import MongoClient, ASCENDING, DESCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError, PyMongoError, ServerSelectionTimeoutError, ConfigurationError

try:
    import certifi
    TLS_CA_FILE = certifi.where()
except ImportError:
    TLS_CA_FILE = None

load_dotenv()
MONGO_URI = os.getenv("MONGO_URI", "")
DB_NAME = os.getenv("DB_NAME", "library_db")
LOAN_DAYS = 14
FINE_PER_DAY = 5
MAX_BOOKS_PER_MEMBER = 3

client = None
db = None
books = members = issues = counters = None
IS_MOCK = False
DB_STATUS_MSG = ""

def connect_database():
    global client, db, books, members, issues, counters, IS_MOCK, DB_STATUS_MSG

    # Fast connection attempt to MongoDB Atlas
    if MONGO_URI:
        try:
            connect_kwargs = {
                "serverSelectionTimeoutMS": 2000,
                "connectTimeoutMS": 2000,
                "socketTimeoutMS": 2000
            }
            if TLS_CA_FILE:
                connect_kwargs["tlsCAFile"] = TLS_CA_FILE
                
            test_client = MongoClient(MONGO_URI, **connect_kwargs)
            test_client.admin.command("ping")
            client = test_client
            db = client[DB_NAME]
            IS_MOCK = False
            DB_STATUS_MSG = "Connected to MongoDB Atlas"
        except Exception as err:
            client = None

    # Fallback to mongomock if Atlas connection fails or URI is missing
    if client is None:
        try:
            import mongomock
            client = mongomock.MongoClient()
            db = client[DB_NAME]
            IS_MOCK = True
            DB_STATUS_MSG = "Running in Offline / In-Memory Mock Mode (MongoDB Atlas unreachable or IP not whitelisted)"
        except Exception as e:
            raise RuntimeError(f"Could not connect to MongoDB Atlas nor fallback to mongomock: {e}")

    books = db["books"]
    members = db["members"]
    issues = db["issues"]
    counters = db["counters"]

    # Setup indexes
    try:
        books.create_index("book_id", unique=True)
        books.create_index("isbn", unique=True)
        books.create_index("category")
        members.create_index("member_id", unique=True)
        members.create_index("email", unique=True)
        issues.create_index("issue_id", unique=True)
        issues.create_index([("status", ASCENDING), ("due_date", ASCENDING)])
    except Exception:
        pass  # mongomock handles basic operations

    # Auto seed initial data if database is empty
    if books.count_documents({}) == 0:
        seed_sample_data()

def next_id(prefix, key):
    if counters is None:
        raise RuntimeError("Database not initialized.")
    doc = counters.find_one_and_update(
        {"_id": key},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER
    )
    return f"{prefix}{doc['seq']:03d}"

def create_issue(book_id, member_id, issue_dt=None):
    issue_dt = issue_dt or datetime.now()
    if not members.find_one({"member_id": member_id}):
        return False, "Member not found."
    book = books.find_one({"book_id": book_id})
    if not book:
        return False, "Book not found."
    if issues.find_one({"member_id": member_id, "book_id": book_id, "status": "Issued"}):
        return False, "This member already holds an active copy of this book."
    if issues.count_documents({"member_id": member_id, "status": "Issued"}) >= MAX_BOOKS_PER_MEMBER:
        return False, f"Member already has {MAX_BOOKS_PER_MEMBER} active books borrowed (maximum allowed)."

    # Atomically decrement available copies
    result = books.update_one(
        {"book_id": book_id, "available_copies": {"$gt": 0}},
        {"$inc": {"available_copies": -1}}
    )
    if result.modified_count == 0:
        return False, "No copies of this book are currently available."

    issue = {
        "issue_id": next_id("I", "issue"),
        "book_id": book_id,
        "member_id": member_id,
        "issue_date": issue_dt,
        "due_date": issue_dt + timedelta(days=LOAN_DAYS),
        "return_date": None,
        "fine": 0,
        "status": "Issued"
    }

    try:
        issues.insert_one(issue)
    except Exception as e:
        # Rollback available copies increment on insertion failure
        books.update_one({"book_id": book_id}, {"$inc": {"available_copies": 1}})
        return False, f"Could not create issue record: {e}"

    return True, issue

def return_issue(issue_id):
    issue = issues.find_one({"issue_id": issue_id, "status": "Issued"})
    if not issue:
        return False, "No active issue found with this ID."

    now = datetime.now()
    due_date = issue.get("due_date")
    if isinstance(due_date, str):
        try:
            due_date = datetime.fromisoformat(due_date)
        except ValueError:
            due_date = now

    due_date_val = due_date.date() if isinstance(due_date, (datetime, date)) else now.date()
    late_days = max(0, (now.date() - due_date_val).days)
    fine = late_days * FINE_PER_DAY

    issues.update_one(
        {"issue_id": issue_id},
        {"$set": {"return_date": now, "status": "Returned", "fine": fine}}
    )
    books.update_one({"book_id": issue["book_id"]}, {"$inc": {"available_copies": 1}})
    return True, {"fine": fine, "late_days": late_days}

def seed_sample_data():
    sample_books = [
        ("Introduction to Algorithms", "Thomas H. Cormen", "Computer Science", "9780262033848", 2009, 4),
        ("Python Crash Course", "Eric Matthes", "Programming", "9781593279288", 2019, 5),
        ("Database System Concepts", "Abraham Silberschatz", "Database", "9780078022159", 2019, 3),
        ("The Pragmatic Programmer", "Andrew Hunt", "Programming", "9780135957059", 2019, 2),
        ("MongoDB: The Definitive Guide", "Shannon Bradshaw", "Database", "9781491954461", 2019, 3),
        ("Wings of Fire", "A. P. J. Abdul Kalam", "Biography", "9788173711466", 1999, 4),
        ("Operating System Concepts", "Abraham Silberschatz", "Computer Science", "9781119800361", 2021, 3),
        ("Discrete Mathematics", "Kenneth H. Rosen", "Mathematics", "9780073383095", 2011, 2),
    ]
    added_books = 0
    for title, author, category, isbn, year, copies in sample_books:
        if not books.find_one({"isbn": isbn}):
            b_id = next_id("B", "book")
            books.insert_one({
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
            added_books += 1
    return added_books

def delete_book(book_id):
    if issues.find_one({"book_id": book_id, "status": "Issued"}):
        return False, "Cannot delete book while copies are currently issued to members."
    res = books.delete_one({"book_id": book_id})
    if res.deleted_count > 0:
        return True, "Book deleted successfully."
    return False, "Book not found."

def library_summary():
    if books is None:
        return {"titles": 0, "copies": 0, "available": 0, "on_loan": 0, "members": 0, "issued": 0, "overdue": 0}
    agg = list(books.aggregate([{"$group": {"_id": None, "total": {"$sum": "$total_copies"}, "available": {"$sum": "$available_copies"}}}]))
    total = agg[0]["total"] if agg else 0
    available = agg[0]["available"] if agg else 0
    return {
        "titles": books.count_documents({}),
        "copies": total,
        "available": available,
        "on_loan": max(0, total - available),
        "members": members.count_documents({}),
        "issued": issues.count_documents({"status": "Issued"}),
        "overdue": issues.count_documents({"status": "Issued", "due_date": {"$lt": datetime.now()}})
    }

def serialize_book(b):
    if not b:
        return {}
    b = dict(b)
    b.pop("_id", None)
    if isinstance(b.get("added_on"), datetime):
        b["added_on"] = b["added_on"].isoformat()
    return b

def serialize_issue(i):
    if not i:
        return {}
    i = dict(i)
    i.pop("_id", None)
    for k in ("issue_date", "due_date", "return_date"):
        if isinstance(i.get(k), datetime):
            i[k] = i[k].isoformat()
    return i

def serialize_member(m):
    if not m:
        return {}
    m = dict(m)
    m.pop("_id", None)
    if isinstance(m.get("joined_on"), datetime):
        m["joined_on"] = m["joined_on"].isoformat()
    return m
