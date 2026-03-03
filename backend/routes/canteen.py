from flask import Blueprint, request, jsonify
from datetime import datetime
from bson import ObjectId
import random
import os
from werkzeug.security import generate_password_hash, check_password_hash
from db import db

# -----------------------------------
# Blueprint
# -----------------------------------
canteen_bp = Blueprint("canteen_bp", __name__, url_prefix="/api/canteen")

# -----------------------------------
# Collections
# -----------------------------------
users_collection = db.users
canteens_collection = db.canteens
menu_collection = db.menu
orders_collection = db.orders

# -----------------------------------
# Upload Folder Setup
# -----------------------------------
UPLOAD_FOLDER = "static/menu_images"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ===================================
# STUDENT SIDE
# ===================================

@canteen_bp.route("/canteens", methods=["GET"])
def get_canteens():
    canteens = list(canteens_collection.find())
    for c in canteens:
        c["_id"] = str(c["_id"])
        c.pop("password", None)
    return jsonify(canteens)


@canteen_bp.route("/menu/<canteen_id>", methods=["GET"])
def get_menu(canteen_id):
    items = list(menu_collection.find({"canteen_id": canteen_id}))
    for item in items:
        item["_id"] = str(item["_id"])
    return jsonify(items)


@canteen_bp.route("/menu/all", methods=["GET"])
def get_all_menu():
    items = list(menu_collection.find())
    for item in items:
        item["_id"] = str(item["_id"])
    return jsonify(items)


@canteen_bp.route("/place-order", methods=["POST"])
def place_order():
    data = request.json

    token_number = random.randint(100, 999)

    order = {
        "user_id": data["user_id"],
        "canteen_id": data["canteen_id"],
        "items": data["items"],
        "total_price": float(data["total_price"]),
        "payment_status": "Pending",
        "order_status": "New",
        "token_number": token_number,
        "created_at": datetime.utcnow()
    }

    result = orders_collection.insert_one(order)

    return jsonify({
        "message": "Order Placed Successfully",
        "order_id": str(result.inserted_id),
        "token_number": token_number
    })


@canteen_bp.route("/my-orders/<user_id>", methods=["GET"])
def my_orders(user_id):
    orders = list(orders_collection.find({"user_id": user_id}))
    for order in orders:
        order["_id"] = str(order["_id"])
    return jsonify(orders)

# ===================================
# OWNER SIDE
# ===================================

@canteen_bp.route("/owner/orders/<canteen_id>", methods=["GET"])
def owner_orders(canteen_id):
    orders = list(orders_collection.find({"canteen_id": canteen_id}))
    for order in orders:
        order["_id"] = str(order["_id"])
    return jsonify(orders)


@canteen_bp.route("/owner/update-status/<order_id>", methods=["POST"])
def update_status(order_id):
    data = request.json
    try:
        orders_collection.update_one(
            {"_id": ObjectId(order_id)},
            {"$set": {"order_status": data["status"]}}
        )
        return jsonify({"message": "Order status updated"})
    except:
        return jsonify({"error": "Invalid Order ID"}), 400


@canteen_bp.route("/owner/daily-sales/<canteen_id>", methods=["GET"])
def daily_sales(canteen_id):
    today = datetime.utcnow().date()

    orders = list(orders_collection.find({
        "canteen_id": canteen_id
    }))

    today_orders = [
        o for o in orders
        if o["created_at"].date() == today
    ]

    total = sum(o["total_price"] for o in today_orders)

    return jsonify({
        "total_orders": len(today_orders),
        "total_sales": total
    })

@canteen_bp.route("/owner/add-menu", methods=["POST"])
def add_menu():
    canteen_id = request.form.get("canteen_id")
    name = request.form.get("name")
    category = request.form.get("category")
    price = request.form.get("price")
    photo = request.files.get("photo")

    if not all([canteen_id, name, category, price]):
        return jsonify({"error": "All fields required"}), 400

    photo_url = None

    if photo:
        filename = photo.filename
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        photo.save(filepath)

        # 👇 IMPORTANT LINE
        photo_url = f"https://college-hwbb.onrender.com/{filepath}"

    menu_item = {
        "canteen_id": canteen_id,
        "name": name,
        "category": category,
        "price": float(price),
        "photo": photo_url
    }

    menu_collection.insert_one(menu_item)

    return jsonify({"message": "Menu item added successfully"})

@canteen_bp.route("/owner/delete-menu/<menu_id>", methods=["DELETE"])
def owner_delete_menu(menu_id):
    try:
        result = menu_collection.delete_one({"_id": ObjectId(menu_id)})
        if result.deleted_count == 0:
            return jsonify({"error": "Item not found"}), 404
        return jsonify({"message": "Item deleted successfully"})
    except:
        return jsonify({"error": "Invalid ID"}), 400


# ===================================
# ADMIN SIDE
# ===================================

@canteen_bp.route("/admin/orders", methods=["GET"])
def all_orders():
    orders = list(orders_collection.find())
    for order in orders:
        order["_id"] = str(order["_id"])
    return jsonify(orders)


@canteen_bp.route("/admin/delete-menu/<menu_id>", methods=["DELETE"])
def admin_delete_menu(menu_id):
    try:
        menu_collection.delete_one({"_id": ObjectId(menu_id)})
        return jsonify({"message": "Menu deleted successfully"})
    except:
        return jsonify({"error": "Invalid ID"}), 400


@canteen_bp.route("/admin/commission", methods=["GET"])
def commission_report():
    orders = list(orders_collection.find())
    total_sales = sum(o["total_price"] for o in orders)
    commission = total_sales * 0.10

    return jsonify({
        "total_sales": total_sales,
        "commission_earned": commission
    })

# ===================================
# AUTH (OWNER)
# ===================================

@canteen_bp.route("/signup", methods=["POST"])
def canteen_signup():
    data = request.json

    name = data.get("name")
    password = data.get("password")
    mobile = data.get("mobile")

    if not all([name, password, mobile]):
        return jsonify({"error": "All fields required"}), 400

    if canteens_collection.find_one({"mobile": mobile}):
        return jsonify({"error": "Mobile already registered"}), 400

    hashed_password = generate_password_hash(password)

    result = canteens_collection.insert_one({
        "name": name,
        "mobile": mobile,
        "password": hashed_password,
        "created_at": datetime.utcnow()
    })

    return jsonify({
        "message": "Canteen Registered Successfully",
        "canteen_id": str(result.inserted_id)
    })


@canteen_bp.route("/login", methods=["POST"])
def canteen_login():
    data = request.json

    mobile = data.get("mobile")
    password = data.get("password")

    if not mobile or not password:
        return jsonify({"error": "Mobile and Password required"}), 400

    canteen = canteens_collection.find_one({"mobile": mobile})

    if not canteen:
        return jsonify({"error": "Canteen not found"}), 404

    if not check_password_hash(canteen["password"], password):
        return jsonify({"error": "Invalid credentials"}), 401

    return jsonify({
        "message": "Login Successful",
        "canteen_id": str(canteen["_id"]),
        "name": canteen["name"]
    })


@canteen_bp.route("/delete/<canteen_id>", methods=["DELETE"])
def delete_canteen(canteen_id):
    try:
        result = canteens_collection.delete_one({"_id": ObjectId(canteen_id)})
        if result.deleted_count == 0:
            return jsonify({"error": "Canteen not found"}), 404
        return jsonify({"message": "Canteen deleted successfully"})
    except:
        return jsonify({"error": "Invalid ID"}), 400
@canteen_bp.route("/admin/menu/<canteen_id>", methods=["GET"])
def admin_menu_by_canteen(canteen_id):
    items = list(menu_collection.find({"canteen_id": canteen_id}))
    
    for item in items:
        item["_id"] = str(item["_id"])
    
    return jsonify(items)
@canteen_bp.route("/admin/orders/<canteen_id>", methods=["GET"])
def admin_orders_by_canteen(canteen_id):
    orders = list(orders_collection.find({"canteen_id": canteen_id}))
    
    for order in orders:
        order["_id"] = str(order["_id"])
    
    return jsonify(orders)