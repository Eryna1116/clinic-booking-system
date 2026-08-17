import os
from flask import Flask, request, redirect, url_for, flash, get_flashed_messages
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

# =============================================
# STEP 1: Create the Flask app
# =============================================
app = Flask(__name__)
app.secret_key = "clinic_secret_key_2026"

# =============================================
# STEP 2: Connect to PostgreSQL (NOT SQLite!)
# =============================================
# These values come from AWS (R1 will give them to you)
# For now, we use fake values - we'll replace them later
DB_HOST = os.environ.get('DB_HOST', 'localhost')
DB_PORT = os.environ.get('DB_PORT', '5432')
DB_NAME = os.environ.get('DB_NAME', 'clinicdb')
DB_USER = os.environ.get('DB_USER', 'postgres')
DB_PASSWORD = os.environ.get('DB_PASSWORD', '')

# This creates the connection string for PostgreSQL
app.config['SQLALCHEMY_DATABASE_URI'] = (
    f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# =============================================
# STEP 3: Define what an "Appointment" looks like
# =============================================
class Appointment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_name = db.Column(db.String(100), nullable=False)
    patient_email = db.Column(db.String(100))
    doctor_name = db.Column(db.String(100), nullable=False)
    date = db.Column(db.String(50), nullable=False)
    time = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(20), default='confirmed')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# =============================================
# STEP 4: HEALTH CHECK - CRITICAL FOR AWS!
# =============================================
# The Load Balancer checks this to know if your app is alive
@app.route('/health')
def health_check():
    return 'OK', 200

# =============================================
# STEP 5: HTML HELPERS (same as your code)
# =============================================
def get_header():
    return '''<!DOCTYPE html>
<html>
<head>
    <title>Clinic Cloud</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        .container { max-width: 800px; }
        .flash-message { margin-top: 10px; }
        .navbar-brand { font-weight: bold; }
    </style>
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark bg-primary mb-4">
        <div class="container">
            <a class="navbar-brand" href="/">🏥 Clinic Cloud</a>
            <div class="navbar-nav">
                <a class="nav-link" href="/">Home</a>
                <a class="nav-link" href="/book">📅 Book</a>
                <a class="nav-link" href="/dashboard">📊 Dashboard</a>
            </div>
        </div>
    </nav>
    <div class="container">
'''

def get_footer():
    return '''    </div>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>'''

def get_flash_messages():
    messages = get_flashed_messages(with_categories=True)
    if not messages:
        return ''
    
    html = ''
    for category, message in messages:
        html += f'''
        <div class="alert alert-{category} alert-dismissible fade show flash-message" role="alert">
            {message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        </div>
        '''
    return html

# =============================================
# STEP 6: HOMEPAGE
# =============================================
@app.route('/')
def index():
    total = Appointment.query.count()
    html = get_header()
    html += f'''
    <div class="row">
        <div class="col-md-8 mx-auto">
            <div class="p-5 bg-white border rounded-3 text-center shadow-sm">
                <h1>🏥 Welcome to the Clinic Portal</h1>
                <p class="text-muted">Securely manage your appointments using Cloud Infrastructure.</p>
                <p><strong>Total Appointments:</strong> {total}</p>
                <div class="mt-4">
                    <a href="/book" class="btn btn-primary btn-lg me-2">📅 Book Now</a>
                    <a href="/dashboard" class="btn btn-outline-secondary btn-lg">📊 View Schedule</a>
                </div>
            </div>
        </div>
    </div>
    '''
    html += get_footer()
    return html

# =============================================
# STEP 7: BOOKING PAGE
# =============================================
@app.route('/book', methods=['GET', 'POST'])
def book():
    if request.method == 'POST':
        try:
            name = request.form.get('name', '').strip()
            doctor = request.form.get('doctor', '').strip()
            date = request.form.get('date', '').strip()
            time = request.form.get('time', '').strip()
            email = request.form.get('email', '').strip()
            
            if not all([name, doctor, date, time]):
                flash('All fields are required!', 'danger')
                return redirect(url_for('book'))
            
            # Check for duplicate booking
            existing = Appointment.query.filter_by(
                doctor_name=doctor,
                date=date,
                time=time,
                status='confirmed'
            ).first()
            
            if existing:
                flash('This time slot is already booked!', 'warning')
                return redirect(url_for('book'))
            
            new_appt = Appointment(
                patient_name=name,
                patient_email=email,
                doctor_name=doctor,
                date=date,
                time=time,
                status='confirmed'
            )
            
            db.session.add(new_appt)
            db.session.commit()
            
            flash(f'✅ Appointment booked successfully for {name}!', 'success')
            return redirect(url_for('dashboard'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error: {str(e)}', 'danger')
            return redirect(url_for('book'))
    
    # GET request - show form
    html = get_header()
    html += get_flash_messages()
    html += '''
    <div class="row">
        <div class="col-md-6 mx-auto">
            <div class="card shadow p-4">
                <h3 class="mb-3">📅 New Appointment</h3>
                <form method="POST">
                    <div class="mb-3">
                        <label class="form-label fw-bold">Patient Name</label>
                        <input type="text" name="name" class="form-control" placeholder="Enter full name" required>
                    </div>
                    
                    <div class="mb-3">
                        <label class="form-label fw-bold">Email (optional)</label>
                        <input type="email" name="email" class="form-control" placeholder="patient@email.com">
                    </div>
                    
                    <div class="mb-3">
                        <label class="form-label fw-bold">Select Doctor</label>
                        <select name="doctor" class="form-select" required>
                            <option value="">-- Choose a doctor --</option>
                            <option value="Dr. Aris (General)">Dr. Aris - General Medicine</option>
                            <option value="Dr. Siti (Pediatric)">Dr. Siti - Pediatric</option>
                            <option value="Dr. Ahmad (Cardiology)">Dr. Ahmad - Cardiology</option>
                            <option value="Dr. Murni (Orthopedic)">Dr. Murni - Orthopedic</option>
                        </select>
                    </div>
                    
                    <div class="row mb-3">
                        <div class="col">
                            <label class="form-label fw-bold">Date</label>
                            <input type="date" name="date" class="form-control" required>
                        </div>
                        <div class="col">
                            <label class="form-label fw-bold">Time</label>
                            <input type="time" name="time" class="form-control" required>
                        </div>
                    </div>
                    
                    <button type="submit" class="btn btn-success w-100">✅ Confirm Appointment</button>
                    <a href="/dashboard" class="btn btn-outline-secondary w-100 mt-2">View All Appointments</a>
                </form>
            </div>
        </div>
    </div>
    '''
    html += get_footer()
    return html

# =============================================
# STEP 8: DASHBOARD
# =============================================
@app.route('/dashboard')
def dashboard():
    all_appts = Appointment.query.order_by(Appointment.date, Appointment.time).all()

    content_template = '''
    <div class="row">
        <div class="col-12">
            <div class="d-flex justify-content-between align-items-center mb-3">
                <h2>📊 Scheduled Appointments</h2>
                <a href="/book" class="btn btn-primary btn-sm">+ New Booking</a>
            </div>

            {table}
        </div>
    </div>
    '''

    if all_appts:
        table_html = '''
            <div class="table-responsive">
                <table class="table table-striped bg-white shadow-sm">
                    <thead class="table-primary">
                        <tr>
                            <th>#</th>
                            <th>Patient</th>
                            <th>Doctor</th>
                            <th>Date</th>
                            <th>Time</th>
                            <th>Status</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
        '''

        for idx, appt in enumerate(all_appts, 1):
            status_badge = f'<span class="badge bg-{"primary" if appt.status == "confirmed" else "danger" if appt.status == "cancelled" else "success"}">{appt.status}</span>'

            table_html += f'''
                        <tr>
                            <td>{idx}</td>
                            <td>{appt.patient_name}</td>
                            <td>{appt.doctor_name}</td>
                            <td>{appt.date}</td>
                            <td>{appt.time}</td>
                            <td>{status_badge}</td>
                            <td>
                                <div class="btn-group btn-group-sm">
                                    <a href="/cancel/{appt.id}" class="btn btn-outline-danger" onclick="return confirm('Cancel this appointment?')">Cancel</a>
                                    <a href="/complete/{appt.id}" class="btn btn-outline-success" onclick="return confirm('Mark as completed?')">Complete</a>
                                </div>
                            </td>
                        </tr>
            '''

        table_html += f'''
                    </tbody>
                    <tfoot class="table-light">
                        <tr>
                            <td colspan="7" class="text-center text-muted">
                                Total: {len(all_appts)} appointment(s)
                            </td>
                        </tr>
                    </tfoot>
                </table>
            </div>
        '''
    else:
        table_html = '''
            <div class="alert alert-info text-center">
                <h4>No appointments yet!</h4>
                <p>Book your first appointment <a href="/book">here</a>.</p>
            </div>
        '''
    content = content_template.format(table=table_html)

    html = get_header()
    html += get_flash_messages()
    html += content
    html += get_footer()
    return html

# =============================================
# STEP 9: CANCEL APPOINTMENT
# =============================================
@app.route('/cancel/<int:appt_id>')
def cancel_appointment(appt_id):
    try:
        appt = Appointment.query.get(appt_id)
        if not appt:
            flash('Appointment not found!', 'danger')
            return redirect(url_for('dashboard'))
        
        if appt.status == 'cancelled':
            flash('Appointment is already cancelled!', 'warning')
            return redirect(url_for('dashboard'))
        
        appt.status = 'cancelled'
        db.session.commit()
        flash(f'❌ Appointment for {appt.patient_name} has been cancelled.', 'warning')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'danger')
    
    return redirect(url_for('dashboard'))

# =============================================
# STEP 10: COMPLETE APPOINTMENT
# =============================================
@app.route('/complete/<int:appt_id>')
def complete_appointment(appt_id):
    try:
        appt = Appointment.query.get(appt_id)
        if not appt:
            flash('Appointment not found!', 'danger')
            return redirect(url_for('dashboard'))
        
        if appt.status == 'cancelled':
            flash('Cannot complete a cancelled appointment!', 'warning')
            return redirect(url_for('dashboard'))
        
        appt.status = 'completed'
        db.session.commit()
        flash(f'✅ Appointment for {appt.patient_name} marked as completed.', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'danger')
    
    return redirect(url_for('dashboard'))

# =============================================
# STEP 11: API ENDPOINTS (for monitoring)
# =============================================
@app.route('/api/appointments')
def api_get_appointments():
    appointments = Appointment.query.all()
    return {
        'success': True,
        'count': len(appointments),
        'appointments': [
            {
                'id': a.id,
                'patient_name': a.patient_name,
                'doctor_name': a.doctor_name,
                'date': a.date,
                'time': a.time,
                'status': a.status
            } for a in appointments
        ]
    }

@app.route('/api/stats')
def api_stats():
    total = Appointment.query.count()
    confirmed = Appointment.query.filter_by(status='confirmed').count()
    cancelled = Appointment.query.filter_by(status='cancelled').count()
    completed = Appointment.query.filter_by(status='completed').count()
    
    return {
        'success': True,
        'total': total,
        'confirmed': confirmed,
        'cancelled': cancelled,
        'completed': completed
    }

# =============================================
# STEP 12: RUN THE APP
# =============================================
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        print("=" * 50)
        print("✅ Database tables created!")
        print("🌐 Server running on port 5000")
        print("❤️ Health check: /health")
        print("=" * 50)
    
    app.run(debug=False, host='0.0.0.0', port=5000)
