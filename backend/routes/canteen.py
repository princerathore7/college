from flask import Blueprint, request, jsonify
from datetime import datetime
from bson import ObjectId
import random
import os
from werkzeug.security import generate_password_hash, check_password_hash
from db import db   # ✅ Central DB import

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

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
# ==============================
# STUDENT SIDE APIs
# ==============================

# Get all canteens
@canteen_bp.route("/canteens", methods=["GET"])
def get_canteens():
    canteens = list(canteens_collection.find({}, {"_id": 0}))
    return jsonify(canteens)


# Get menu by canteen id
@canteen_bp.route("/menu/<canteen_id>", methods=["GET"])
def get_menu(canteen_id):
    menu = list(menu_collection.find(
        {"canteen_id": canteen_id},
        {"_id": 0}
    ))
    return jsonify(menu)


# Place Order
@canteen_bp.route("/place-order", methods=["POST"])
def place_order():
    data = request.json

    token_number = random.randint(100, 999)

    order = {
        "user_id": data["user_id"],
        "canteen_id": data["canteen_id"],
        "items": data["items"],
        "total_price": data["total_price"],
        "payment_status": "Pending",
        "order_status": "New",
        "token_number": token_number,
        "created_at": datetime.utcnow()
    }

    result = orders_collection.insert_one(order)

    return jsonify({
        "message": "Order Placed",
        "order_id": str(result.inserted_id),
        "token_number": token_number
    })


# Get student orders
@canteen_bp.route("/my-orders/<user_id>", methods=["GET"])
def my_orders(user_id):
    orders = list(orders_collection.find(
        {"user_id": user_id},
        {"_id": 0}
    ))
    return jsonify(orders)


# ==============================
# OWNER SIDE APIs
# ==============================

# Get new orders for canteen
@canteen_bp.route("/owner/orders/<canteen_id>", methods=["GET"])
def owner_orders(canteen_id):
    orders = list(orders_collection.find(
        {"canteen_id": canteen_id},
        {"_id": 0}
    ))
    return jsonify(orders)


# Update order status
@canteen_bp.route("/owner/update-status/<order_id>", methods=["POST"])
def update_status(order_id):
    data = request.json
    orders_collection.update_one(
        {"_id": ObjectId(order_id)},
        {"$set": {"order_status": data["status"]}}
    )
    return jsonify({"message": "Order status updated"})


# Daily sales report
@canteen_bp.route("/owner/daily-sales/<canteen_id>", methods=["GET"])
def daily_sales(canteen_id):
    today = datetime.utcnow().date()

    orders = list(orders_collection.find({
        "canteen_id": canteen_id
    }))

    total = sum(order["total_price"] for order in orders)

    return jsonify({
        "total_orders": len(orders),
        "total_sales": total
    })


# Menu Edit (Owner)
@canteen_bp.route("/owner/add-menu", methods=["POST"])
def add_menu():

    canteen_id = request.form.get("canteen_id")
    name = request.form.get("name")
    category = request.form.get("category")
    price = request.form.get("price")

    if not canteen_id or not name or not category or not price:
        return jsonify({"error": "All fields required"}), 400

    image_url = None

    if "photo" in request.files:
        photo = request.files["photo"]

        if photo.filename != "":
            filename = secure_filename(photo.filename)
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            photo.save(filepath)
            image_url = f"/static/menu_images/{filename}"

    menu_item = {
        "canteen_id": canteen_id,
        "name": name,
        "category": category,
        "price": float(price),
        "image": image_url
    }

    menu_collection.insert_one(menu_item)

    return jsonify({"message": "Menu item added successfully"})
# ==============================
# ADMIN SIDE APIs
# ==============================

# Get all orders (Admin)
@canteen_bp.route("/admin/orders", methods=["GET"])
def all_orders():
    orders = list(orders_collection.find({}, {"_id": 0}))
    return jsonify(orders)


# Delete menu item (Admin)
@canteen_bp.route("/admin/delete-menu/<menu_id>", methods=["DELETE"])
def delete_menu(menu_id):
    menu_collection.delete_one({"_id": ObjectId(menu_id)})
    return jsonify({"message": "Menu deleted"})


# Commission system (basic example)
@canteen_bp.route("/admin/commission", methods=["GET"])
def commission_report():
    orders = list(orders_collection.find({}))
    total_sales = sum(order["total_price"] for order in orders)

    commission = total_sales * 0.10  # 10% commission example

    return jsonify({
        "total_sales": total_sales,
        "commission_earned": commission
    })
# ==============================
# CANTEEN AUTH (Owner)
# ==============================

@canteen_bp.route("/api/canteen/signup", methods=["POST"])
def canteen_signup():
    data = request.json

    name = data.get("name")
    password = data.get("password")
    mobile = data.get("mobile")

    if not name or not password or not mobile:
        return jsonify({"error": "All fields required"}), 400

    # Check if mobile already exists
    existing = canteens_collection.find_one({"mobile": mobile})
    if existing:
        return jsonify({"error": "Mobile already registered"}), 400

    hashed_password = generate_password_hash(password)

    canteen_data = {
        "name": name,
        "mobile": mobile,
        "password": hashed_password,
        "created_at": datetime.utcnow()
    }

    result = canteens_collection.insert_one(canteen_data)

    return jsonify({
        "message": "Canteen Registered Successfully",
        "canteen_id": str(result.inserted_id)
    })
@canteen_bp.route("/canteen/login", methods=["POST"])
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
@canteen_bp.route("/canteen/delete/<canteen_id>", methods=["DELETE"])
def delete_canteen(canteen_id):

    result = canteens_collection.delete_one({
        "_id": ObjectId(canteen_id)
    })

    if result.deleted_count == 0:
        return jsonify({"error": "Canteen not found"}), 404

    return jsonify({"message": "Canteen deleted successfully"})
@canteen_bp.route("/owner/delete-menu/<menu_id>", methods=["DELETE"])
def owner_delete_menu(menu_id):

    result = menu_collection.delete_one({"_id": ObjectId(menu_id)})

    if result.deleted_count == 0:
        return jsonify({"error": "Item not found"}), 404

    return jsonify({"message": "Item deleted successfully"})