import os
from dotenv import load_dotenv
load_dotenv()

from flask import Flask, render_template, request, redirect, url_for, session, flash
from decimal import Decimal
import uuid

# === Flask App 基本設定 ===
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "please-change-this-in-production")

# === 資料庫設定（先用 SQLite；之後上 Render 會改成 PostgreSQL） ===
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.sql import func

app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///cosmetic.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

class Product(db.Model):
    __tablename__ = "products"
    id = db.Column(db.String(64), primary_key=True)       # 例如 "mask-cica"
    name = db.Column(db.String(120), nullable=False)
    price = db.Column(db.Numeric(10, 2), nullable=False)  # Decimal
    category = db.Column(db.String(50), index=True)
    img = db.Column(db.String(500))
    desc = db.Column(db.Text)
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now())

# --- 第一次啟動時匯入示範商品 ---
SEED_ITEMS = [
    {"id": "mask-cica", "name": "CICA舒緩面膜", "price": Decimal("129"), "category": "面膜",
     "img": "https://via.placeholder.com/600x400?text=CICA+Mask", "desc": "敏感肌友善，換季舒緩保濕。"},
    {"id": "mask-heartleaf", "name": "魚腥草保濕面膜", "price": Decimal("99"), "category": "面膜",
     "img": "https://via.placeholder.com/600x400?text=Heartleaf+Mask", "desc": "清爽補水、不黏膩。"},
    {"id": "hand-cream-coconut", "name": "椰香護手霜 30g", "price": Decimal("89"), "category": "護手霜",
     "img": "https://via.placeholder.com/600x400?text=Coconut+Hand+Cream", "desc": "輕盈不油，淡淡果香。"},
    {"id": "hand-cream-ceramide", "name": "神經醯胺修護護手霜 45g", "price": Decimal("159"), "category": "護手霜",
     "img": "https://via.placeholder.com/600x400?text=Ceramide+Hand+Cream", "desc": "乾裂手救星，深度修護。"},
]

def ensure_seed_data():
    """若資料表為空，匯入預設商品"""
    if Product.query.count() == 0:
        for it in SEED_ITEMS:
            db.session.add(Product(**it))
        db.session.commit()

# ----------------- 購物車工具 -----------------
def _get_cart():
    """從 session 取購物車（dict: {product_id: qty}）"""
    return session.setdefault("cart", {})

def _save_cart(cart):
    session["cart"] = cart
    session.modified = True

def _find_product(pid: str) -> Product | None:
    return Product.query.get(pid)

def _cart_detail():
    """把購物車轉成可渲染的明細（含小計與總計）"""
    cart = _get_cart()
    items = []
    total = Decimal("0")
    for pid, qty in cart.items():
        p = _find_product(pid)
        if not p:
            continue
        qty = int(qty)
        price = Decimal(p.price)  # SQLAlchemy Numeric -> Decimal
        subtotal = price * qty
        total += subtotal
        items.append({
            "id": p.id,
            "name": p.name,
            "img": p.img,
            "price": price,
            "qty": qty,
            "subtotal": subtotal
        })
    return items, total

@app.context_processor
def inject_cart_count():
    cart = _get_cart()
    count = sum(int(q) for q in cart.values())
    return {"cart_count": count}

# ----------------- 前端頁面 -----------------
@app.route("/")
def home():
    return redirect(url_for("products"))

@app.route("/products")
def products():
    cat = request.args.get("cat")
    if cat:
        items = Product.query.filter_by(category=cat).order_by(Product.created_at.desc()).all()
    else:
        items = Product.query.order_by(Product.created_at.desc()).all()

    # 取所有分類（distinct）
    all_items = Product.query.with_entities(Product.category).all()
    categories = sorted({c[0] for c in all_items if c[0]})
    return render_template("products.html", items=items, categories=categories, current_cat=cat)

@app.route("/add-to-cart", methods=["POST"])
def add_to_cart():
    pid = request.form.get("pid")
    qty = int(request.form.get("qty", 1))
    p = _find_product(pid)
    if not p:
        flash("找不到此商品", "danger")
        return redirect(url_for("products"))

    cart = _get_cart()
    cart[pid] = cart.get(pid, 0) + qty
    _save_cart(cart)
    flash(f"已加入購物車：{p.name} x{qty}", "success")
    return redirect(request.referrer or url_for("products"))

@app.route("/cart")
def cart():
    items, total = _cart_detail()
    return render_template("cart.html", items=items, total=total)

@app.route("/update-cart", methods=["POST"])
def update_cart():
    cart = {}
    for key, value in request.form.items():
        if key.startswith("qty_"):
            pid = key.replace("qty_", "", 1)
            qty = max(0, int(value or 0))
            if qty > 0:
                cart[pid] = qty
    _save_cart(cart)
    flash("購物車已更新", "info")
    return redirect(url_for("cart"))

@app.route("/remove/<pid>", methods=["POST"])
def remove_item(pid):
    cart = _get_cart()
    if pid in cart:
        del cart[pid]
        _save_cart(cart)
        flash("已移除商品", "warning")
    return redirect(url_for("cart"))

# ----------------- 結帳流程 -----------------
@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    items, total = _cart_detail()
    if request.method == "GET":
        return render_template("checkout.html", items=items, total=total)

    name = (request.form.get("name") or "").strip()
    email = (request.form.get("email") or "").strip()
    address = (request.form.get("address") or "").strip()
    payment = (request.form.get("payment") or "").strip()

    if not name or not email or not address or not payment:
        flash("請完整填寫結帳表單。", "danger")
        return redirect(url_for("checkout"))

    if not items:
        flash("購物車是空的，請先加入商品。", "warning")
        return redirect(url_for("products"))

    order_id = uuid.uuid4().hex[:10].upper()
    session.pop("cart", None)
    session["last_order"] = {"order_id": order_id, "email": email}
    return redirect(url_for("order_success"))

@app.route("/order-success")
def order_success():
    info = session.pop("last_order", None)
    if not info:
        return redirect(url_for("products"))
    return render_template("order_success.html", order_id=info["order_id"], email=info["email"])


from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user

# 登入管理初始化
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "admin_login"

# 使用者資料類別
class User(UserMixin):
    def __init__(self, id):
        self.id = id

@login_manager.user_loader
def load_user(user_id):
    return User(user_id)

# --- 管理登入區域 ---

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        admin_user = os.getenv("ADMIN_USERNAME", "admin")
        admin_pass = os.getenv("ADMIN_PASSWORD", "admin123")

        if username == admin_user and password == admin_pass:
            login_user(User(id=username))
            flash("登入成功！", "success")
            return redirect(url_for("admin_dashboard"))
        else:
            flash("帳號或密碼錯誤！", "danger")

    return render_template("admin_login.html")

@app.route("/admin/logout")
@login_required
def admin_logout():
    logout_user()
    flash("已登出。", "info")
    return redirect(url_for("admin_login"))

@app.route("/admin")
@login_required
def admin_dashboard():
    return render_template("admin_dashboard.html", username=current_user.id)


# ----------------- 啟動區 -----------------
if __name__ == "__main__":
    # 建表 + 種子資料
    with app.app_context():
        db.create_all()
        ensure_seed_data()

    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    app.run(debug=debug)

