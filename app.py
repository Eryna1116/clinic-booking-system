import os
from flask import Flask, request, redirect, url_for, flash, get_flashed_messages, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import boto3
from botocore.exceptions import ClientError
import uuid
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'clinic_secret_key_2026')

# Create uploads folder if it doesn't exist
UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

class MockS3Client:
    def __init__(self):
        self.files = {}
        print("✅ Mock S3 client initialized (files saved locally)")
    
    def upload_fileobj(self, fileobj, bucket, key, ExtraArgs=None):
        file_path = os.path.join(UPLOAD_FOLDER, key)
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'wb') as f:
            fileobj.seek(0)
            f.write(fileobj.read())
        self.files[key] = file_path
        print(f"✅ Mock upload: {key}")
        return True
    
    def generate_presigned_url(self, ClientMethod, Params, ExpiresIn):
        key = Params['Key']
        return f"/local_file/{key}"

#DATABASE SETUP 
#Check if running on EC2
if os.environ.get('RUNNING_ON_EC2'):
    # Use RDS PostgreSQL
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
        'DATABASE_URL',
        'postgresql://username:password@rds-endpoint:5432/clinic_db'
    )
else:
    # Use SQLite for local development
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///clinic.db'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# AWS S3 SETUP (FOR DOCUMENT STORAGE)
# S3 client (use Mock S3 if no AWS credentials)
if os.environ.get('AWS_ACCESS_KEY') and os.environ.get('AWS_SECRET_KEY'):
    s3_client = boto3.client(
        's3',
        aws_access_key_id=os.environ.get('AWS_ACCESS_KEY'),
        aws_secret_access_key=os.environ.get('AWS_SECRET_KEY'),
        region_name=os.environ.get('AWS_REGION', 'us-east-1')
    )
    print("✅ S3 client initialized!")
else:
    s3_client = MockS3Client()

S3_BUCKET = os.environ.get('S3_BUCKET', 'clinic-booking-app')

#database
class Appointment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_name = db.Column(db.String(100), nullable=False)
    patient_email = db.Column(db.String(100))
    doctor_name = db.Column(db.String(100), nullable=False)
    date = db.Column(db.String(50), nullable=False)
    time = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(20), default='confirmed')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    document_key = db.Column(db.String(500), nullable=True)  # S3 key
    document_name = db.Column(db.String(255), nullable=True)  # Original filename
    
    def to_dict(self):
        return {
            'id': self.id,
            'patient_name': self.patient_name,
            'patient_email': self.patient_email,
            'doctor_name': self.doctor_name,
            'date': self.date,
            'time': self.time,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'document_name': self.document_name,
            'document_url': f"https://{S3_BUCKET}.s3.amazonaws.com/{self.document_key}" if self.document_key else None
        }

#HTML templates
def get_header():
    return '''<!DOCTYPE html>
<html>
<head>
    <title>Clinic Cloud</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        .container { max-width: 800px; }
        .flash-message { margin-top: 10px; }
        .status-confirmed { color: #0d6efd; }
        .status-cancelled { color: #dc3545; }
        .status-completed { color: #198754; }
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

#routes
@app.route('/')
def index():
    total = Appointment.query.count()
    html = get_header()
    html += '''
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
    '''.format(total=total)
    html += get_footer()
    return html

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
            
            #check for duplicate booking
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
    
    #GET request - show form
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
                            <th>Document</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
        '''

        for idx, appt in enumerate(all_appts, 1):
            status_badge = f'<span class="badge bg-{"primary" if appt.status == "confirmed" else "danger" if appt.status == "cancelled" else "success"}">{appt.status}</span>'
            
            # Document section - shows Upload button AND View button if document exists
            if appt.document_key:
                doc_section = f'''
                    <div class="btn-group btn-group-sm">
                        <a href="/download/{appt.id}" class="btn btn-info btn-sm">📄 View</a>
                    </div>
                '''
            else:
                doc_section = f'''
                    <div class="btn-group btn-group-sm">
                        <a href="/upload/{appt.id}" class="btn btn-warning btn-sm">📤 Upload</a>
                    </div>
                '''

            table_html += f'''
                        <tr>
                            <td>{idx}</td>
                            <td>{appt.patient_name}</td>
                            <td>{appt.doctor_name}</td>
                            <td>{appt.date}</td>
                            <td>{appt.time}</td>
                            <td>{status_badge}</td>
                            <td>{doc_section}</td>
                            <td>
                                <div class="btn-group btn-group-sm">
                                    <a href="/cancel/{appt.id}" class="btn btn-outline-danger" onclick="return confirm('Cancel this appointment?')">❌ Cancel</a>
                                    <a href="/complete/{appt.id}" class="btn btn-outline-success" onclick="return confirm('Mark as completed?')">✅ Complete</a>
                                </div>
                            </td>
                        </tr>
            '''

        table_html += f'''
                    </tbody>
                    <tfoot class="table-light">
                        <tr>
                            <td colspan="8" class="text-center text-muted">
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

@app.route('/upload/<int:appt_id>', methods=['GET', 'POST'])
def upload_document(appt_id):
    """Upload a document for an appointment to S3"""
    appt = Appointment.query.get(appt_id)
    if not appt:
        flash('Appointment not found!', 'danger')
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file selected!', 'danger')
            return redirect(request.url)
        
        file = request.files['file']
        if file.filename == '':
            flash('No file selected!', 'danger')
            return redirect(request.url)
        
        if not s3_client:
            flash('S3 is not configured!', 'danger')
            return redirect(request.url)
        
        try:
            #generate unique filename
            filename = secure_filename(file.filename)
            file_extension = filename.rsplit('.', 1)[1].lower() if '.' in filename else 'pdf'
            s3_key = f"appointments/{appt_id}/{uuid.uuid4()}.{file_extension}"
            
            #upload to S3
            s3_client.upload_fileobj(
                file,
                S3_BUCKET,
                s3_key,
                ExtraArgs={'ContentType': file.content_type or 'application/octet-stream'}
            )
            
            #update appointment with document info
            appt.document_key = s3_key
            appt.document_name = filename
            db.session.commit()
            
            flash(f'✅ Document "{filename}" uploaded successfully!', 'success')
            return redirect(url_for('dashboard'))
            
        except ClientError as e:
            flash(f'❌ S3 Upload Error: {str(e)}', 'danger')
        except Exception as e:
            flash(f'❌ Error: {str(e)}', 'danger')
    
#GET request - show upload form
    html = get_header()
    html += get_flash_messages()
    html += f'''
    <div class="row">
        <div class="col-md-6 mx-auto">
            <div class="card shadow p-4">
                <h3 class="mb-3">📄 Upload Document</h3>
                <p><strong>Patient:</strong> {appt.patient_name}</p>
                <p><strong>Doctor:</strong> {appt.doctor_name}</p>
                <p><strong>Date:</strong> {appt.date} at {appt.time}</p>
                
                <form method="POST" enctype="multipart/form-data">
                    <div class="mb-3">
                        <label class="form-label fw-bold">Choose File</label>
                        <input type="file" name="file" class="form-control" accept=".pdf,.doc,.docx,.jpg,.png" required>
                        <small class="text-muted">Allowed: PDF, DOC, DOCX, JPG, PNG</small>
                    </div>
                    
                    <button type="submit" class="btn btn-primary w-100">📤 Upload Document</button>
                    <a href="/dashboard" class="btn btn-outline-secondary w-100 mt-2">Cancel</a>
                </form>
            </div>
        </div>
    </div>
    '''
    html += get_footer()
    return html

@app.route('/download/<int:appt_id>')
def download_document(appt_id):
    """Download document from S3"""
    appt = Appointment.query.get(appt_id)
    if not appt or not appt.document_key:
        flash('No document found for this appointment!', 'warning')
        return redirect(url_for('dashboard'))
    
    if not s3_client:
        flash('S3 is not configured!', 'danger')
        return redirect(url_for('dashboard'))
    
    try:
        # Check if using Mock S3 (local file)
        if S3_BUCKET == 'clinic-booking-app' and not os.environ.get('AWS_ACCESS_KEY'):
            # For Mock S3 - serve local file
            file_path = os.path.join(UPLOAD_FOLDER, appt.document_key)
            if os.path.exists(file_path):
                return send_file(file_path, as_attachment=True, download_name=appt.document_name)
            else:
                flash('File not found!', 'danger')
                return redirect(url_for('dashboard'))
        
        # Real S3 - generate pre-signed URL
        url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': S3_BUCKET, 'Key': appt.document_key},
            ExpiresIn=60
        )
        return redirect(url)
        
    except ClientError as e:
        flash(f'❌ Download Error: {str(e)}', 'danger')
        return redirect(url_for('dashboard'))

#API endpoints
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
                'patient_email': a.patient_email,
                'doctor_name': a.doctor_name,
                'date': a.date,
                'time': a.time,
                'status': a.status,
                'document_name': a.document_name,
                'document_url': f"https://{S3_BUCKET}.s3.amazonaws.com/{a.document_key}" if a.document_key else None
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

@app.route('/api/health')
def health_check():
    """Health check endpoint for load balancer"""
    return jsonify({
        'status': 'healthy',
        'database': 'connected',
        's3': 'configured' if s3_client else 'not configured'
    })

#environment variable check
@app.route('/api/env')
def env_check():
    """Check environment variables (for debugging)"""
    return {
        'running_on_ec2': os.environ.get('RUNNING_ON_EC2', 'false'),
        'database_url': 'configured' if os.environ.get('DATABASE_URL') else 'not configured',
        's3_bucket': os.environ.get('S3_BUCKET', 'not configured'),
        'aws_region': os.environ.get('AWS_REGION', 'not configured')
    }

#run
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        
        #to check if running on EC2
        if os.environ.get('RUNNING_ON_EC2'):
            print("=" * 50)
            print("🚀 RUNNING ON EC2")
            print("=" * 50)
        else:
            print("=" * 50)
            print("💻 RUNNING LOCALLY")
            print("=" * 50)
        
        print("✅ Database created successfully!")
        print("🌐 Server running at: http://localhost:5000")
        print("📊 Dashboard: http://localhost:5000/dashboard")
        print("📅 Book: http://localhost:5000/book")
        print("🔌 API: http://localhost:5000/api/appointments")
        print("📄 Upload: http://localhost:5000/upload/<appt_id>")
        print("=" * 50)
    
    app.run(debug=True, host='0.0.0.0', port=5000)
