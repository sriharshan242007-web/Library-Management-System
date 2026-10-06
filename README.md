# Libra — Python + Flask + MongoDB Atlas Library Management System

This version converts the original console-based Python + PyMongo library project into a professional web application while keeping the original MongoDB collections and core issue/return rules.

## Stack
- Python
- Flask
- PyMongo
- MongoDB Atlas
- HTML/CSS/JavaScript (frontend rendered by Flask)

## Existing database structure retained
- `books`
- `members`
- `issues`
- `counters`

The original rules are retained: 14-day loan, Rs.5/day late fine, and maximum 3 active books per member.

## Setup
1. Install Python.
2. Open this folder in VS Code.
3. Create a virtual environment if desired:
   `python -m venv venv`
4. Activate it on Windows:
   `venv\\Scripts\\activate`
5. Install packages:
   `pip install -r requirements.txt`
6. Copy `.env.example` to `.env`.
7. Put your MongoDB Atlas URI in `.env`:
   `MONGO_URI=mongodb+srv://USERNAME:PASSWORD@cluster1.xxxxx.mongodb.net/?retryWrites=true&w=majority`
8. Run:
   `python app.py`
9. Open `http://127.0.0.1:5000`

## Demo data
Open `http://127.0.0.1:5000/admin` and click **Load Sample Books** if the database is empty.

## Customer flow
Home → search/filter books → Borrow → enter customer details → Flask `/api/borrow` → member is created/updated → issue is created → available copies are decremented → confirmation is shown.

## Admin flow
`/admin` shows library summary, inventory, issue history, returns, and a form to add books.

## Important
Never put the MongoDB Atlas username/password inside HTML or JavaScript. Keep it in `.env` and only use it from Python.
