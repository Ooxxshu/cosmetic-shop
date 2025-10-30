import os
from dotenv import load_dotenv
load_dotenv()
from flask import Flask, render_template, request, redirect, url_for, session, flash
from decimal import Decimal
import uuid

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "please-change-this-in-production")

# --- 商品目錄（示範：面膜、護手霜 + 幾個延伸品項） ---
CATALOG = [
    {
        "id": "mask-cica",
        "name": "CICA舒緩面膜",
        "price": Decimal("129"),
        "category": "面膜",
        "img": "https://via.placeholder.com/600x400?text=CICA+Mask",
        "desc": "敏感肌友善，換季舒緩保濕。"
    },
    {
        "id": "mask-heartleaf",
        "name": "魚腥草保濕面膜",
        "price": Decimal("99"),
        "category": "面膜",
        "img": "https://via.placeholder.com/600x400?text=Heartleaf+Mask",
        "desc": "清爽補水、不黏膩。"
    },
    {
        "id": "hand-cream-coconut",
        "name": "椰香護手霜 30g",
        "price": Decimal("89"),
        "category": "護手霜",
        "img": "https://via.placeholder.com/600x400?text=Coconut+Hand+Cream",
        "desc": "輕盈不油，淡淡果香。"
    },
    {
        "id": "hand-cream-ceramide",
        "name": "神經醯胺修護護手霜 45g",
        "price": Decimal("159"),
        "category": "護手霜",
        "img": "https://via.placeholder.com/600x400?text=Ceramide+Hand+Cream",
        "desc": "乾裂手救星，深度修護。"
    }
]

# ----------------- 工具函式 -----------------
def _get_cart():
    """從 session 取購物車（dict: {product_id: qty}）"""
    return session.setdefault("cart", {})

def _save_cart(cart):
    session["cart"] = cart
    session.modified = True

def _find_product(pid):
    return next((p for p in CATALOG if p["id"] == pid), None)

def _cart_detail():
    """把購物車轉成可渲染的明細（含小計與總計）"""
    cart = _get_cart()
    items = []
    total = Decimal("0")
    for pid, qty in cart.items():
        product = _find_product(pid)
        if not product:
            continue
        qty = int(qty)
        subtotal = product["price"] * qty
        total += subtotal
        items.append({
            "id": product["id"],
            "name": product["name"],
            "img": product["img"],
            "price": product["price"],
            "qty": qty,
            "subtotal": subtotal
        })
    return items, total

@app.context_processor
def inject_cart_count():
    """導覽列顯示購物車數量"""
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
    items = [p for p in CATALOG if (not cat or p["category"] == cat)]
    categories = sorted(set(p["category"] for p in CATALOG))
    return render_template("products.html", items=items, categories=categories, current_cat=cat)

@app.route("/add-to-cart", methods=["POST"])
def add_to_cart():
    pid = request.form.get("pid")
    qty = int(request.form.get("qty", 1))
    product = _find_product(pid)
    if not product:
        flash("找不到此商品", "danger")
        return redirect(url_for("products"))

    cart = _get_cart()
    cart[pid] = cart.get(pid, 0) + qty
    _save_cart(cart)
    flash(f"已加入購物車：{product['name']} x{qty}", "success")
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
    # 先抓購物車明細
    items, total = _cart_detail()
    if request.method == "GET":
        return render_template("checkout.html", items=items, total=total)

    # POST：接表單
    name = (request.form.get("name") or "").strip()
    email = (request.form.get("email") or "").strip()
    address = (request.form.get("address") or "").strip()
    payment = (request.form.get("payment") or "").strip()

    # 基本驗證
    if not name or not email or not address or not payment:
        flash("請完整填寫結帳表單。", "danger")
        return redirect(url_for("checkout"))

    if not items:
        flash("購物車是空的，請先加入商品。", "warning")
        return redirect(url_for("products"))

    # 產生簡單訂單編號（示意）
    order_id = uuid.uuid4().hex[:10].upper()

    # 這裡可接 Email/金流（之後我們再加）
    session.pop("cart", None)

    # 暫存資訊在 session 用於成功頁顯示（單次）
    session["last_order"] = {"order_id": order_id, "email": email}
    return redirect(url_for("order_success"))

@app.route("/order-success")
def order_success():
    info = session.pop("last_order", None)
    if not info:
        return redirect(url_for("products"))
    return render_template("order_success.html", order_id=info["order_id"], email=info["email"])

# ----------------- 主程式 -----------------
if __name__ == "__main__":
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    app.run(debug=debug)
