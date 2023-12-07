from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_bcrypt import Bcrypt
from datetime import datetime


app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///maintenance.db'
app.config['SECRET_KEY'] = 'password'

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)

# Setup Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    role = db.Column(db.String(20))  # 'tenant', 'staff', 'maintenance'

class Tenant(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone_number = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(100), nullable=False)
    check_in_date = db.Column(db.DateTime, nullable=False)
    check_out_date = db.Column(db.DateTime, nullable=True)  # This can be null if the tenant hasn't checked out.
    apartment_number = db.Column(db.String(20), nullable=False)
    # ... rest of your model definitions

class MaintenanceRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=False)
    apartment_number = db.Column(db.String(20), nullable=False)
    area = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    request_date = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='pending')
    photo = db.Column(db.String(300))

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


@app.route('/', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        print("User is authenticated, redirecting to hub")
        return redirect(url_for('hub'))

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and bcrypt.check_password_hash(user.password_hash, password):
            login_user(user)
            print("Login successful, redirecting to hub")
            return redirect(url_for('hub'))
        else:
            print("Login failed")
            return 'Invalid username or password'
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/hub')
@login_required
def hub():
    return render_template('hub.html')

@app.route('/submit-request', methods=['GET', 'POST'])
@login_required
def submit_request():
    if request.method == 'POST':
        # Extract data from form
        tenant_id = request.form.get('tenant_id')
        apartment_number = request.form.get('apartment_number')
        area = request.form.get('area')
        description = request.form.get('description')
        photo = request.form.get('photo')  # URL or path to the photo

        # Create new MaintenanceRequest
        new_request = MaintenanceRequest(
            tenant_id=tenant_id,
            apartment_number=apartment_number,
            area=area,
            description=description,
            request_date=datetime.now(),  # Corrected here
            photo=photo
        )

        # Add to database and commit
        db.session.add(new_request)
        db.session.commit()

        return redirect(url_for('submit_request'))

    return render_template('submit_request.html')


@app.route('/update-request/<int:request_id>', methods=['GET', 'POST'])
@login_required
def update_request(request_id):
    maintenance_request = MaintenanceRequest.query.get_or_404(request_id)
    if request.method == 'POST':
        maintenance_request.status = 'completed'  # Update status to completed
        db.session.commit()
        return redirect(url_for('browse_requests'))

    return render_template('update_request.html', request=maintenance_request)

@app.route('/browse-requests')
@login_required
def browse_requests():
    if current_user.role != 'maintenance':
        return "Access denied", 403

    # Retrieve query parameters
    apartment_number = request.args.get('apartment_number')
    area = request.args.get('area')
    status = request.args.get('status')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    # Build the query
    query = MaintenanceRequest.query
    if apartment_number:
        query = query.filter(MaintenanceRequest.apartment_number == apartment_number)
    if area:
        query = query.filter(MaintenanceRequest.area == area)
    if status:
        query = query.filter(MaintenanceRequest.status == status)
    if start_date and end_date:
        start = datetime.strptime(start_date, '%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y-%m-%d')
        query = query.filter(MaintenanceRequest.request_date.between(start, end))

    requests = query.all()
    return render_template('browse_requests.html', requests=requests)


@app.route('/add-tenant', methods=['GET', 'POST'])
@login_required
def add_tenant():
    if current_user.role != 'manager':
        return "Access denied", 403

    if request.method == 'POST':
        name = request.form['name']
        phone_number = request.form['phone_number']
        email = request.form['email']
        check_in_date = request.form['check_in_date']
        check_out_date = request.form['check_out_date'] or None  # Allow None if not provided
        apartment_number = request.form['apartment_number']

        if not (name and phone_number and email and check_in_date and apartment_number):
            # Handle the error appropriately, e.g., return an error message
            return "All fields except check-out date are required", 400

        # Convert dates from string to datetime objects
        check_in_date = datetime.strptime(check_in_date, '%Y-%m-%d')
        check_out_date = datetime.strptime(check_out_date, '%Y-%m-%d') if check_out_date else None

        new_tenant = Tenant(
            name=name,
            phone_number=phone_number,
            email=email,
            check_in_date=check_in_date,
            check_out_date=check_out_date,
            apartment_number=apartment_number
        )

        db.session.add(new_tenant)
        db.session.commit()

        return redirect(url_for('view_tenants'))

    return render_template('add_tenant.html')


@app.route('/move-tenant/<int:tenant_id>', methods=['GET', 'POST'])
@login_required
def move_tenant(tenant_id):
    if current_user.role != 'manager':
        return "Access denied", 403
    tenant = Tenant.query.get_or_404(tenant_id)
    if request.method == 'POST':
        tenant.apartment_number = request.form.get('apartment_number')
        db.session.commit()
        return redirect(url_for('home'))

    return render_template('move_tenant.html', tenant=tenant)

@app.route('/delete-tenant/<int:tenant_id>')
@login_required
def delete_tenant(tenant_id):
    if current_user.role != 'manager':
        return "Access denied", 403
    tenant = Tenant.query.get_or_404(tenant_id)
    db.session.delete(tenant)
    db.session.commit()
    return redirect(url_for('home'))

@app.route('/view-tenants')
@login_required
def view_tenants():
    if current_user.role != 'manager':
        return "Access denied", 403
    tenants = Tenant.query.all()
    return render_template('view_tenants.html', tenants=tenants)

@app.route('/manager')
@login_required
def manager_dashboard():
    if current_user.role != 'manager':
        return "Access denied", 403
    return render_template('manager_dashboard.html')


@app.route('/edit-tenant/<int:tenant_id>', methods=['GET', 'POST'])
@login_required
def edit_tenant(tenant_id):
    tenant = Tenant.query.get_or_404(tenant_id)
    if request.method == 'POST':
        tenant.name = request.form['name']
        tenant.apartment_number = request.form['apartment_number']
        db.session.commit()
        return redirect(url_for('view_tenants'))
    return render_template('edit_tenant.html', tenant=tenant)



@app.route('/')
def home():
    return "Welcome to the Maintenance Request App!"

if __name__ == "__main__":
    with app.app_context():
        db.create_all()


        roles = ['tenant', 'maintenance', 'manager']
        for role in roles:
            username = f'test_{role}'
            user = User.query.filter_by(username=username).first()
            if not user:
                hashed_password = bcrypt.generate_password_hash(f'password_{role}').decode('utf-8')
                new_user = User(username=username, password_hash=hashed_password, role=role)
                db.session.add(new_user)
                print(f"User created: {username} with role: {role}")
            else:
                print(f"User already exists: {username} with role: {role}")

        db.session.commit()
    app.run(debug=True)



