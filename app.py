import hashlib
import os
import sqlite3
from functools import wraps
from pathlib import Path

from flask import (
    Flask,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.utils import secure_filename


BASE_DIR = Path(__file__).parent
DATABASE_PATH = BASE_DIR / "database.db"
UPLOAD_FOLDER = BASE_DIR / "static" / "images" / "products"
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp", "bmp"}

app = Flask(__name__)
app.config["SECRET_KEY"] = "dev-secret-key"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_error):
    connection = g.pop("db", None)
    if connection is not None:
        connection.close()


def hash_password(password):
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def normalize_role_name(role_name):
    value = (role_name or "").strip().lower().replace("ё", "е")

    if "админ" in value or "admin" in value:
        return "admin"
    if "менедж" in value or "manager" in value:
        return "manager"
    if "клиент" in value or "client" in value:
        return "client"
    if "гост" in value or "guest" in value:
        return "guest"

    return value


def get_current_role():
    return session.get("role_key", "guest")


def can_use_advanced_tools():
    return get_current_role() in {"manager", "admin"}


def can_manage_products():
    return get_current_role() == "admin"


def can_view_orders():
    return get_current_role() in {"manager", "admin"}


def login_user(user_row):
    session.clear()
    session["user_id"] = user_row["id"]
    session["full_name"] = user_row["full_name"]
    session["role_name"] = user_row["role_name"]
    session["role_key"] = normalize_role_name(user_row["role_name"])


def login_guest():
    session.clear()
    session["user_id"] = None
    session["full_name"] = "Гость"
    session["role_name"] = "Гость"
    session["role_key"] = "guest"


def require_roles(*allowed_roles):
    def decorator(view_function):
        @wraps(view_function)
        def wrapped_view(*args, **kwargs):
            if get_current_role() not in allowed_roles:
                flash(
                    "У вас нет доступа к этой странице. "
                    "Выполните вход под подходящей учетной записью.",
                    "error",
                )
                return redirect(url_for("products"))
            return view_function(*args, **kwargs)

        return wrapped_view

    return decorator


def allowed_file(file_name):
    if "." not in file_name:
        return False
    extension = file_name.rsplit(".", 1)[1].lower()
    return extension in ALLOWED_EXTENSIONS


def save_uploaded_photo(file_storage):
    if file_storage is None or not file_storage.filename:
        return None

    if not allowed_file(file_storage.filename):
        raise ValueError(
            "Недопустимый формат изображения. "
            "Разрешены png, jpg, jpeg, gif, webp, bmp."
        )

    UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)

    extension = Path(secure_filename(file_storage.filename)).suffix.lower()
    file_name = f"product_{os.urandom(8).hex()}{extension}"
    file_path = UPLOAD_FOLDER / file_name
    file_storage.save(file_path)

    return f"images/products/{file_name}"


def get_or_create_reference(connection, table_name, name):
    allowed_tables = {"suppliers", "categories", "manufacturers"}

    if table_name not in allowed_tables:
        raise ValueError("Недопустимое имя таблицы.")

    normalized_name = (name or "").strip()

    if not normalized_name:
        raise ValueError("Поле не может быть пустым.")

    row = connection.execute(
        f"SELECT id FROM {table_name} WHERE name = ?",
        (normalized_name,),
    ).fetchone()

    if row is not None:
        return row["id"]

    cursor = connection.execute(
        f"INSERT INTO {table_name} (name) VALUES (?)",
        (normalized_name,),
    )
    return cursor.lastrowid


def get_product_or_404(product_id):
    product = get_db().execute(
        """
        SELECT
            p.id,
            p.article,
            p.name,
            p.unit,
            p.price,
            p.discount,
            p.stock,
            p.description,
            p.photo_path,
            p.category_id,
            p.manufacturer_id,
            p.supplier_id,
            c.name AS category_name,
            m.name AS manufacturer_name,
            s.name AS supplier_name
        FROM products p
        JOIN categories c ON c.id = p.category_id
        JOIN manufacturers m ON m.id = p.manufacturer_id
        JOIN suppliers s ON s.id = p.supplier_id
        WHERE p.id = ?
        """,
        (product_id,),
    ).fetchone()

    if product is None:
        flash("Товар не найден.", "error")
        return None

    return product


@app.context_processor
def inject_template_data():
    return {
        "current_full_name": session.get("full_name"),
        "current_role_name": session.get("role_name"),
        "current_role_key": get_current_role(),
        "can_use_advanced_tools": can_use_advanced_tools(),
        "can_manage_products": can_manage_products(),
        "can_view_orders": can_view_orders(),
    }


@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        login_value = request.form.get("login", "").strip()
        password_value = request.form.get("password", "")

        if not login_value or not password_value:
            flash(
                "Введите логин и пароль. "
                "Поля не должны быть пустыми.",
                "error",
            )
            return render_template("login.html", title="Вход")

        user = get_db().execute(
            """
            SELECT
                users.id,
                users.full_name,
                users.login,
                users.password_hash,
                roles.name AS role_name
            FROM users
            JOIN roles ON roles.id = users.role_id
            WHERE users.login = ?
            """,
            (login_value,),
        ).fetchone()

        if user is None or user["password_hash"] != hash_password(password_value):
            flash(
                "Неверный логин или пароль. "
                "Проверьте данные и попробуйте снова.",
                "error",
            )
            return render_template("login.html", title="Вход")

        login_user(user)
        return redirect(url_for("products"))

    return render_template("login.html", title="Вход")


@app.route("/guest")
def guest_login():
    login_guest()
    return redirect(url_for("products"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/products")
def products():
    connection = get_db()

    search_text = request.args.get("search", "").strip()
    supplier_id = request.args.get("supplier_id", "all")
    stock_sort = request.args.get("stock_sort", "")

    if not can_use_advanced_tools():
        search_text = ""
        supplier_id = "all"
        stock_sort = ""

    sql = """
        SELECT
            p.id,
            p.article,
            p.name,
            p.unit,
            p.price,
            p.discount,
            p.stock,
            p.description,
            p.photo_path,
            c.name AS category_name,
            m.name AS manufacturer_name,
            s.name AS supplier_name,
            s.id AS supplier_id
        FROM products p
        JOIN categories c ON c.id = p.category_id
        JOIN manufacturers m ON m.id = p.manufacturer_id
        JOIN suppliers s ON s.id = p.supplier_id
        WHERE 1 = 1
    """
    params = []

    if search_text:
        pattern = f"%{search_text.lower()}%"
        sql += """
            AND (
                LOWER(p.article) LIKE ?
                OR LOWER(p.name) LIKE ?
                OR LOWER(p.unit) LIKE ?
                OR LOWER(COALESCE(p.description, '')) LIKE ?
                OR LOWER(c.name) LIKE ?
                OR LOWER(m.name) LIKE ?
                OR LOWER(s.name) LIKE ?
            )
        """
        params.extend([pattern] * 7)

    if supplier_id != "all":
        sql += " AND s.id = ? "
        params.append(supplier_id)

    if stock_sort == "asc":
        sql += " ORDER BY p.stock ASC, p.name ASC "
    elif stock_sort == "desc":
        sql += " ORDER BY p.stock DESC, p.name ASC "
    else:
        sql += " ORDER BY p.name ASC "

    products_rows = connection.execute(sql, params).fetchall()
    suppliers_rows = connection.execute(
        "SELECT id, name FROM suppliers ORDER BY name"
    ).fetchall()

    return render_template(
        "products.html",
        title="Список товаров",
        products=products_rows,
        suppliers=suppliers_rows,
        search_text=search_text,
        supplier_id=supplier_id,
        stock_sort=stock_sort,
    )


@app.route("/products/new", methods=["GET", "POST"])
@require_roles("admin")
def create_product():
    connection = get_db()

    categories = connection.execute(
        "SELECT id, name FROM categories ORDER BY name"
    ).fetchall()
    manufacturers = connection.execute(
        "SELECT id, name FROM manufacturers ORDER BY name"
    ).fetchall()
    suppliers = connection.execute(
        "SELECT id, name FROM suppliers ORDER BY name"
    ).fetchall()

    if request.method == "POST":
        try:
            article = request.form.get("article", "").strip()
            name = request.form.get("name", "").strip()
            unit = request.form.get("unit", "").strip()
            supplier_name = request.form.get("supplier_name", "").strip()
            description = request.form.get("description", "").strip()
            category_id = request.form.get("category_id", type=int)
            manufacturer_id = request.form.get("manufacturer_id", type=int)

            if not article:
                raise ValueError("Укажите артикул товара.")
            if not name:
                raise ValueError("Укажите наименование товара.")
            if not unit:
                raise ValueError("Укажите единицу измерения.")
            if not supplier_name:
                raise ValueError("Укажите поставщика.")
            if category_id is None:
                raise ValueError("Выберите категорию.")
            if manufacturer_id is None:
                raise ValueError("Выберите производителя.")

            try:
                price = float(request.form.get("price", "0").strip())
            except ValueError as exc:
                raise ValueError("Цена должна быть числом.") from exc

            try:
                stock = int(request.form.get("stock", "0").strip())
            except ValueError as exc:
                raise ValueError("Количество на складе должно быть целым числом.") from exc

            try:
                discount = int(request.form.get("discount", "0").strip())
            except ValueError as exc:
                raise ValueError("Скидка должна быть целым числом.") from exc

            if price < 0:
                raise ValueError("Цена не может быть отрицательной.")
            if stock < 0:
                raise ValueError("Количество на складе не может быть отрицательным.")
            if discount < 0 or discount > 100:
                raise ValueError("Скидка должна быть в диапазоне от 0 до 100.")

            supplier_id_value = get_or_create_reference(
                connection,
                "suppliers",
                supplier_name,
            )

            photo_path = save_uploaded_photo(request.files.get("photo"))

            connection.execute(
                """
                INSERT INTO products (
                    article,
                    name,
                    unit,
                    price,
                    supplier_id,
                    manufacturer_id,
                    category_id,
                    discount,
                    stock,
                    description,
                    photo_path
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    article,
                    name,
                    unit,
                    price,
                    supplier_id_value,
                    manufacturer_id,
                    category_id,
                    discount,
                    stock,
                    description,
                    photo_path,
                ),
            )
            connection.commit()

            flash("Товар успешно добавлен.", "success")
            return redirect(url_for("products"))

        except sqlite3.IntegrityError:
            connection.rollback()
            flash(
                "Не удалось сохранить товар. "
                "Проверьте, не используется ли уже такой артикул.",
                "error",
            )
        except ValueError as error:
            connection.rollback()
            flash(str(error), "error")
        except Exception:
            connection.rollback()
            flash(
                "Произошла ошибка при добавлении товара. "
                "Проверьте введённые данные и повторите попытку.",
                "error",
            )

    return render_template(
        "product_form.html",
        title="Добавление товара",
        form_title="Добавление товара",
        product=None,
        categories=categories,
        manufacturers=manufacturers,
        suppliers=suppliers,
    )


@app.route("/products/<int:product_id>/edit", methods=["GET", "POST"])
@require_roles("admin")
def edit_product(product_id):
    connection = get_db()
    product = get_product_or_404(product_id)

    if product is None:
        return redirect(url_for("products"))

    categories = connection.execute(
        "SELECT id, name FROM categories ORDER BY name"
    ).fetchall()
    manufacturers = connection.execute(
        "SELECT id, name FROM manufacturers ORDER BY name"
    ).fetchall()
    suppliers = connection.execute(
        "SELECT id, name FROM suppliers ORDER BY name"
    ).fetchall()

    if request.method == "POST":
        try:
            article = request.form.get("article", "").strip()
            name = request.form.get("name", "").strip()
            unit = request.form.get("unit", "").strip()
            supplier_name = request.form.get("supplier_name", "").strip()
            description = request.form.get("description", "").strip()
            category_id = request.form.get("category_id", type=int)
            manufacturer_id = request.form.get("manufacturer_id", type=int)

            if not article:
                raise ValueError("Укажите артикул товара.")
            if not name:
                raise ValueError("Укажите наименование товара.")
            if not unit:
                raise ValueError("Укажите единицу измерения.")
            if not supplier_name:
                raise ValueError("Укажите поставщика.")
            if category_id is None:
                raise ValueError("Выберите категорию.")
            if manufacturer_id is None:
                raise ValueError("Выберите производителя.")

            try:
                price = float(request.form.get("price", "0").strip())
            except ValueError as exc:
                raise ValueError("Цена должна быть числом.") from exc

            try:
                stock = int(request.form.get("stock", "0").strip())
            except ValueError as exc:
                raise ValueError("Количество на складе должно быть целым числом.") from exc

            try:
                discount = int(request.form.get("discount", "0").strip())
            except ValueError as exc:
                raise ValueError("Скидка должна быть целым числом.") from exc

            if price < 0:
                raise ValueError("Цена не может быть отрицательной.")
            if stock < 0:
                raise ValueError("Количество на складе не может быть отрицательным.")
            if discount < 0 or discount > 100:
                raise ValueError("Скидка должна быть в диапазоне от 0 до 100.")

            supplier_id_value = get_or_create_reference(
                connection,
                "suppliers",
                supplier_name,
            )

            photo_path = product["photo_path"]
            uploaded_file = request.files.get("photo")

            if uploaded_file is not None and uploaded_file.filename:
                photo_path = save_uploaded_photo(uploaded_file)

            connection.execute(
                """
                UPDATE products
                SET
                    article = ?,
                    name = ?,
                    unit = ?,
                    price = ?,
                    supplier_id = ?,
                    manufacturer_id = ?,
                    category_id = ?,
                    discount = ?,
                    stock = ?,
                    description = ?,
                    photo_path = ?
                WHERE id = ?
                """,
                (
                    article,
                    name,
                    unit,
                    price,
                    supplier_id_value,
                    manufacturer_id,
                    category_id,
                    discount,
                    stock,
                    description,
                    photo_path,
                    product_id,
                ),
            )
            connection.commit()

            flash("Товар успешно обновлён.", "success")
            return redirect(url_for("products"))

        except sqlite3.IntegrityError:
            connection.rollback()
            flash(
                "Не удалось сохранить изменения. "
                "Проверьте уникальность артикула.",
                "error",
            )
        except ValueError as error:
            connection.rollback()
            flash(str(error), "error")
        except Exception:
            connection.rollback()
            flash(
                "Произошла ошибка при редактировании товара. "
                "Проверьте введённые данные и повторите попытку.",
                "error",
            )

    return render_template(
        "product_form.html",
        title="Редактирование товара",
        form_title="Редактирование товара",
        product=product,
        categories=categories,
        manufacturers=manufacturers,
        suppliers=suppliers,
    )


@app.route("/products/<int:product_id>/delete", methods=["POST"])
@require_roles("admin")
def delete_product(product_id):
    connection = get_db()
    product = get_product_or_404(product_id)

    if product is None:
        return redirect(url_for("products"))

    try:
        connection.execute("DELETE FROM products WHERE id = ?", (product_id,))
        connection.commit()
        flash("Товар успешно удалён.", "success")
    except sqlite3.IntegrityError:
        connection.rollback()
        flash(
            "Невозможно удалить товар, потому что он уже используется в заказах.",
            "error",
        )
    except Exception:
        connection.rollback()
        flash(
            "Произошла ошибка при удалении товара.",
            "error",
        )

    return redirect(url_for("products"))


@app.route("/orders")
@require_roles("manager", "admin")
def orders():
    return render_template(
        "orders.html",
        title="Заказы",
    )


if __name__ == "__main__":
    app.run(debug=True)
