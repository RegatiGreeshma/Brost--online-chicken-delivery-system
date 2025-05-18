from flask import Flask, request, jsonify, render_template, redirect, url_for, session
import mysql.connector
import random
import string
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Required for session management

# MySQL Database Connection
db = mysql.connector.connect(
    host="localhost",
    user="root",
    password="regati@2610",
    database="project"
)
cursor = db.cursor()

# Route to render login page
@app.route('/', methods=['GET', 'POST'])
def login_page():
    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register_page():
    if request.method == 'GET':
        return render_template('register.html')
    
    data = request.json  
    print("Received data:", data)  # Debugging

    first_name = data.get('first_name')
    last_name = data.get('last_name')
    email = data.get('email')
    password = data.get('password')
    
    # Get address fields from the form
    addresses = []
    address_container = data.get('addresses', [])
    for addr in address_container:
        addresses.append({
            'address': addr.get('address'),
            'landmark': addr.get('landmark'),
            'pincode': addr.get('pincode')
        })

    try:
        # Insert user details into register table
        cursor.execute("""
            INSERT INTO register (first_name, last_name, email, password) 
            VALUES (%s, %s, %s, %s)
        """, (first_name, last_name, email, password))
        db.commit()

        user_id = cursor.lastrowid

        # Insert addresses
        if addresses:
            for addr in addresses:
                cursor.execute("""
                    INSERT INTO addresses (user_id, address, landmark, pincode) 
                    VALUES (%s, %s, %s, %s)
                """, (user_id, addr['address'], addr['landmark'], addr['pincode']))
            db.commit()

        return jsonify({'message': 'User registered successfully', 'redirect': url_for('main_page')}), 201
    except mysql.connector.Error as err:
        db.rollback()
        return jsonify({'message': f'Registration failed: {str(err)}'}), 400

# Modified login route to handle admin redirection
@app.route('/login', methods=['POST'])
def login():
    email = request.form['email']
    password = request.form['password']

    cursor.execute("SELECT id, password, email FROM register WHERE email = %s", (email,))
    user = cursor.fetchone()

    if user and user[1] == password:  # Plain text password comparison
        session['user_id'] = user[0]  # Store user session
        
        # Check if user is admin
        if email == "admin@gmail.com":
            return redirect(url_for('admin_page'))  # Redirect to admin page
        return redirect(url_for('main_page'))  # Redirect to mainpage.html
    else:
        return render_template('login.html', error="Invalid email or password")


@app.route('/admin')
def admin_page():
    if 'user_id' not in session:
        return redirect(url_for('login_page'))
    
    cursor.execute("SELECT email FROM register WHERE id = %s", (session['user_id'],))
    user = cursor.fetchone()
    
    if not user or user[0] != "admin@gmail.com":
        return redirect(url_for('main_page'))
    
    cursor_dict = db.cursor(dictionary=True)
    
    # Fetch user data
    cursor_dict.execute("""
        SELECT r.id, r.first_name, r.last_name, r.email, 
               a.address, a.landmark, a.pincode
        FROM register r
        LEFT JOIN addresses a ON r.id = a.user_id
    """)
    users = cursor_dict.fetchall()
    
    # Fetch pending orders
    cursor_dict.execute("""
        SELECT o.id, r.first_name, r.last_name, o.total_price, o.status, o.created_at 
        FROM orders o 
        JOIN register r ON o.user_id = r.id 
        WHERE o.status = 'Pending'
        ORDER BY o.created_at DESC
    """)
    pending_orders = cursor_dict.fetchall()
    
    # Fetch completed orders
    cursor_dict.execute("""
        SELECT o.id, r.first_name, r.last_name, o.total_price, o.status, o.created_at 
        FROM orders o 
        JOIN register r ON o.user_id = r.id 
        WHERE o.status = 'Completed'
        ORDER BY o.created_at DESC
    """)
    completed_orders = cursor_dict.fetchall()
    
    # Fetch payment data
    cursor_dict.execute("""
        SELECT p.id, p.order_id, r.first_name, r.last_name, 
               p.payment_method, p.payment_status, p.transaction_id, p.created_at
        FROM payments p
        JOIN orders o ON p.order_id = o.id
        JOIN register r ON o.user_id = r.id
        ORDER BY p.created_at DESC
    """)
    payments = cursor_dict.fetchall()
    
    # Fetch order count by date
    cursor_dict.execute("""
        SELECT DATE(created_at) AS order_date, COUNT(*) AS total_orders
        FROM orders
        GROUP BY DATE(created_at)
        ORDER BY order_date DESC;
    """)
    orders_by_date = cursor_dict.fetchall()

    cursor_dict.close()
    
    return render_template('admin.html', 
                         users=users,
                         pending_orders=pending_orders,
                         completed_orders=completed_orders,
                         payments=payments,
                         orders_by_date=orders_by_date)  # Include orders by date

# New route to handle order status updates
@app.route('/update_order_status', methods=['POST'])
def update_order_status():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'}), 401
        
    order_id = request.json.get('order_id')
    
    try:
        cursor.execute("UPDATE orders SET status = 'Completed' WHERE id = %s", (order_id,))
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500 
    

@app.route('/past_orders')
def past_orders():
    if 'user_id' not in session:
        return redirect(url_for('login_page'))
        
    cursor = db.cursor(dictionary=True)
    
    # Fetch orders with discount details
    cursor.execute("""
        SELECT o.id, o.total_price, o.discount_amount, o.discount_code, o.final_amount, 
               o.status, o.created_at, oi.item_name, oi.quantity, oi.price, (oi.quantity * oi.price) as subtotal
        FROM orders o
        LEFT JOIN order_items oi ON o.id = oi.order_id
        WHERE o.user_id = %s
        ORDER BY o.created_at DESC
    """, (session['user_id'],))
    
    results = cursor.fetchall()
    cursor.close()

    # Organize the data into a nested structure
    organized_orders = {}
    for row in results:
        order_id = row['id']
        if order_id not in organized_orders:
            organized_orders[order_id] = {
                'id': row['id'],
                'total_price': row['total_price'],
                'discount_amount': row['discount_amount'],
                'discount_code': row['discount_code'],
                'final_amount': row['final_amount'],
                'status': row['status'],
                'created_at': row['created_at'],
                'items': []
            }
        if row['item_name']:  # Only add if there are items
            organized_orders[order_id]['items'].append({
                'item_name': row['item_name'],
                'quantity': row['quantity'],
                'price': row['price'],
                'subtotal': row['subtotal']
            })

    # Convert the dictionary to a list for the template
    orders_list = list(organized_orders.values())
    
    return render_template('past_orders.html', orders=orders_list)


# Route to render the main page after successful login
@app.route('/mainpage')
def main_page():
    return render_template('mainpage.html')

#search to render to
@app.route('/menu')
def menu_page():
    search_query = request.args.get('search', '').strip().lower()  # Strip spaces and convert to lowercase

    cursor = db.cursor(dictionary=True)  # Ensure results are in dictionary format
    
    if search_query:
        query = "SELECT * FROM menu WHERE LOWER(name) LIKE %s"
        cursor.execute(query, (f"%{search_query}%",))  # Use SQL filtering
    else:
        query = "SELECT * FROM menu"
        cursor.execute(query)

    menu_items = cursor.fetchall()
    cursor.close()  # Always close the cursor after fetching

    return render_template("menu.html", menu_items=menu_items)

# Route to render cart page
@app.route('/cart')
def cart_page():
    return render_template('cart.html')

@app.route('/checkout', methods=['POST'])
def process_checkout():
    if 'user_id' not in session:
        return jsonify({"success": False, "message": "User not logged in"}), 401  # Check if user is logged in

    data = request.get_json()
    cart = data.get('cart', [])
    total_price = data.get('total', 0)

    if not cart:
        return jsonify({"success": False, "message": "Cart is empty"}), 400

    try:
        cursor = db.cursor()

        # 🛠 FIX: Make sure 'user_id' exists in the session
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({"success": False, "message": "User ID not found in session"}), 400

        # Insert order into database with status "Pending"
        cursor.execute("""
            INSERT INTO orders (user_id, total_price, status, created_at)
            VALUES (%s, %s, %s, NOW())
        """, (user_id, total_price, 'Pending'))
        db.commit()

        order_id = cursor.lastrowid  # Get last inserted order ID
        print(f"✅ New Order Created: Order ID = {order_id}") 
        
        print("User ID:", user_id)


        # Insert order items into order_items table
        order_items_query = """
            INSERT INTO order_items (order_id, item_name, quantity, price)
            VALUES (%s, %s, %s, %s)
        """
        order_items_values = [(order_id, item['name'], item.get('quantity', 1), item['price']) for item in cart]
        cursor.executemany(order_items_query, order_items_values)
        db.commit()

        return jsonify({"success": True, "message": "Order placed successfully", "order_id": order_id}), 200

    except Exception as e:
        db.rollback()
        print("❌ Error processing order:", str(e))
        return jsonify({"success": False, "message": f"Error processing order: {str(e)}"}), 500

@app.route('/pay', methods=['GET', 'POST'])
def pay_page():
    order_id = request.args.get('order_id') or request.form.get('order_id')

    if not order_id:
        return redirect(url_for('cart_page'))  # Redirect if order_id is missing

    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT total_price FROM orders WHERE id = %s", (order_id,))
    order_data = cursor.fetchone()
    order_total = order_data['total_price'] if order_data else 0

    if request.method == 'POST':
        try:
            payment_method = request.form.get('paymentMethod')
            discount_amount = float(request.form.get('discountAmount', 0))
            final_amount = float(request.form.get('finalAmount', order_total))
            discount_code = request.form.get('discountCode', '')

            transaction_id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))

            # Step 1: Update Order Discount & Final Price
            cursor.execute("""
                UPDATE orders 
                SET discount_amount = %s, final_amount = %s, discount_code = %s
                WHERE id = %s
            """, (discount_amount, final_amount, discount_code, order_id))
            db.commit()

            # Step 2: Process Payment Based on Method
            if payment_method == 'cod':
                cursor.execute("UPDATE orders SET status = 'Pending' WHERE id = %s", (order_id,))
            else:
                cursor.execute("""
                    INSERT INTO payments (order_id, payment_method, payment_status, transaction_id, amount)
                    VALUES (%s, %s, 'success', %s, %s)
                """, (order_id, payment_method, transaction_id, final_amount))
                cursor.execute("UPDATE orders SET status = 'Completed' WHERE id = %s", (order_id,))

            db.commit()

            # Return JSON response for JavaScript popup
            return jsonify({"success": True, "order_id": order_id})

        except Exception as e:
            db.rollback()
            return jsonify({"success": False, "message": str(e)})

    return render_template('pay.html', order_id=order_id, order_total=order_total)


@app.route('/bill/<int:order_id>')
def bill_page(order_id):
    if 'user_id' not in session:
        return redirect(url_for('login_page'))

    try:
        cursor = db.cursor(dictionary=True)
        cursor.execute("""
            SELECT id, user_id, total_price, status, created_at, discount_amount, discount_code, final_amount 
            FROM orders WHERE id = %s
        """, (order_id,))
        order = cursor.fetchone()

        if not order or order['user_id'] != session['user_id']:
            return redirect(url_for('cart_page'))

        cursor.execute("""
            SELECT item_name, quantity, price, (quantity * price) as subtotal 
            FROM order_items WHERE order_id = %s
        """, (order_id,))
        items = cursor.fetchall()

        return render_template('bill.html', order=order, items=items)

    except Exception as e:
        print(f"Error in bill_page: {str(e)}")
        return redirect(url_for('cart_page'))
    
@app.route('/orders_summary')
def orders_summary():
    try:
        cursor = db.cursor(dictionary=True)

        # Fetch total order count
        cursor.execute("SELECT COUNT(*) AS total_orders FROM orders;")
        total_orders = cursor.fetchone()['total_orders']

        # Fetch completed and pending orders count
        cursor.execute("SELECT status, COUNT(*) AS count FROM orders GROUP BY status;")
        order_counts = {row['status']: row['count'] for row in cursor.fetchall()}

        # Fetch full order details
        cursor.execute("""
            SELECT id, user_id, total_price, discount_amount, final_amount, status, created_at
            FROM orders ORDER BY created_at DESC;
        """)
        orders = cursor.fetchall()

        return jsonify({
            "total_orders": total_orders,
            "order_counts": order_counts,
            "orders": orders
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


    
@app.route('/logout')
def logout():
    return render_template('login.html')
    
if __name__ == '__main__':
    app.run(debug=True)
