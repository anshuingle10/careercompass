import pickle
import uuid
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_mail import Mail
from flask_mysqldb import MySQL
from werkzeug.security import generate_password_hash, check_password_hash
from flask import jsonify
import openai
import markdown
import base64
import sys
from datetime import datetime
import numpy as np
import sklearn
from http import client
from dotenv import load_dotenv
import re
import os
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from openai import OpenAI
import time
import traceback

app = Flask(__name__)

load_dotenv()  # Load environment variables from .env
# ✅ OpenRouter Configuration
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENAI_API_KEY"),
)

# Token that changes every time the server process restarts
app.config['SESSION_START_TOKEN'] = str(uuid.uuid4())

# secret key
app.secret_key = 'suraj'
# Mysql Connection
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = 'root'
app.config['MYSQL_DB'] = 'career_roadmap_db'

mysql = MySQL(app)

app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'dikshapardeshi086@gmail.com'
app.config['MAIL_PASSWORD'] = 'ykkdbswhatkntpog'  # app password (no spaces recommended)

mail = Mail(app)

# --- ML Model Loading ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(BASE_DIR, "models")
MODEL_PATH = os.path.join(MODEL_DIR, "admission_model.pkl")
ENCODER_PATH = os.path.join(MODEL_DIR, "label_encoders.pkl")
SCALER_PATH = os.path.join(MODEL_DIR, "scaler.pkl")

model = None
branch_encoder = None
college_encoder = None
scaler = None

try:
    with open(MODEL_PATH, "rb") as f:
        model = pickle.load(f)
    with open(ENCODER_PATH, "rb") as f:
        label_encoders = pickle.load(f)
        college_encoder = label_encoders.get("college")
        branch_encoder = label_encoders.get("branch")
    with open(SCALER_PATH, "rb") as f:
        scaler = pickle.load(f)
    print("✅ All ML Files Loaded Successfully")
except Exception as e:
    print("❌ ML Load Error:", e)

# Configure upload folder for avatars
UPLOAD_FOLDER = 'static/uploads/avatars'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE

# Create upload directory if it doesn't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.context_processor
def inject_current_user():
    user_info = None
    if 'user_id' in session:
        try:
            cur = mysql.connection.cursor()
            cur.execute("SELECT name, avatar FROM users WHERE id = %s", (session['user_id'],))
            row = cur.fetchone()
            cur.close()
            if row:
                user_info = {
                    'name': row[0],
                    'avatar': row[1]
                }
        except Exception:
            user_info = None

    return dict(current_user=user_info)

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    """Simple admin login with fixed credentials.

    Username: admin
    Password: super
    """
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        if username == 'admin' and password == 'super':
            session['is_admin'] = True
            flash('Admin login successful.', 'success')
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Invalid admin credentials.', 'danger')

    return render_template('admin/admin_login.html')

@app.route('/admin/dashboard')
def admin_dashboard():
    if not session.get('is_admin'):
        flash('Please log in as admin to access the admin dashboard.', 'warning')
        return redirect(url_for('admin_login'))

    cur = mysql.connection.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    total_users = cur.fetchone()[0]
    cur.close()

    return render_template(
        'admin/admin_dashboard.html',
        total_users=total_users
    )

@app.route('/admin/history')
def admin_history():
    """Admin history page: show list of registered users."""
    if not session.get('is_admin'):
        flash('Please log in as admin to access this page.', 'warning')
        return redirect(url_for('admin_login'))

    cur = mysql.connection.cursor()
    try:
        cur.execute("SELECT id, name, email FROM users ORDER BY id DESC")
        users = cur.fetchall()
    finally:
        cur.close()

    # users is a list of (id, name, email)
    return render_template('admin/admin_history.html', users=users)

@app.route('/admin/contacts')
def admin_contacts():
    """Show messages submitted by users via contact form."""
    if not session.get('is_admin'):
        flash('Please log in as admin to access this page.', 'warning')
        return redirect(url_for('admin_login'))

    cur = mysql.connection.cursor()
    try:
        cur.execute("""
            SELECT uc.id, u.name, u.email, uc.subject, uc.message, uc.created_at
            FROM user_contacts uc
            JOIN users u ON uc.user_id = u.id
            ORDER BY uc.created_at DESC
        """)
        contacts = cur.fetchall()
    finally:
        cur.close()

    return render_template('admin/admin_contacts.html', contacts=contacts)

@app.route('/roadmap')
def roadmap():
    return render_template('user/roadmap.html')


@app.route('/roadmap_details')
def roadmap_details():
    category = request.args.get('category', '').lower()

    if category == 'polytechnic':
        return redirect(url_for('polytechnic'))  # <-- use 'polytechnic', not 'polytechnic_streams'
    if category == 'iti':
        return redirect(url_for('iti_trades'))
    if category == 'paramedical':
        return redirect(url_for('paramedical_categories'))

    career_data = {'iti': {
    'title': 'ITI Trades',
    'icon': 'fa-tools',
    'courses': '4 Trades',
    'description': 'Vocational training in technical trades after 10th.',
    'duration': '1 Year',
    'exam': ['ITI Entrance'],
    'degree': ['ITI Certificate'],
    'available_courses': []  # optional
},'polytechnic': {
    'title': 'Polytechnic Diploma',
    'icon': 'fa-cogs',
    'courses': '5 Streams',
    'description': 'Diploma courses after 10th for technical careers.',
    'duration': '3 Years',
    'exam': ['State CET / Polytechnic Entrance'],
    'degree': ['Direct 2nd Year Engineering'],

    'available_courses': [
        {
            'name': 'Mechanical Diploma',
            'skills': ['Machines', 'Production'],
            'jobs': ['Technician', 'Supervisor'],
            'higher': ['BE Mechanical']
        },
        {
            'name': 'Civil Diploma',
            'skills': ['Construction', 'Design'],
            'jobs': ['Site Engineer'],
            'higher': ['BE Civil']
        },
        {
            'name': 'Electrical Diploma',
            'skills': ['Circuits', 'Power'],
            'jobs': ['Electrical Technician'],
            'higher': ['BE Electrical']
        },
        {
            'name': 'Computer Diploma',
            'skills': ['Programming', 'Networking'],
            'jobs': ['IT Support'],
            'higher': ['BE IT']
        },
    ]
},'engineering': {'title': 'Engineering Courses', 'icon': 'fa-cogs', 'courses': '11 Courses',
                                   'description': 'Most popular career path for PCM students. Engineering offers diverse specializations.',
                                   'duration': '4 Years (B.Tech/B.E)',
                                   'exam': ['JEE Main', 'JEE Advanced', 'MHT-CET', 'BITSAT', 'VITEEE'],
                                   'degree': ['M.Tech/ME', 'MBA', 'MS Abroad', 'PhD'], 'available_courses': [
            {'name': 'B.Tech/BE Computer Engineering', 'skills': ['Programming', 'Problem Solving', 'Algorithms'],
             'jobs': ['Software Developer', 'Data Scientist', 'Web Developer'],
             'higher': ['M.Tech CS', 'MS Computer Science', 'MBA IT']},
            {'name': 'B.Tech/BE Mechanical Engineering', 'skills': ['Design', 'Thermodynamics', 'CAD'],
             'jobs': ['Mechanical Engineer', 'Automobile Engineer'], 'higher': ['M.Tech Mechanical', 'MBA']},
            {'name': 'B.Tech/BE Civil Engineering', 'skills': ['Construction Planning', 'Surveying', 'Design'],
             'jobs': ['Civil Engineer', 'Site Engineer'], 'higher': ['M.Tech Civil', 'Structural Engineering']},
            {'name': 'B.Tech/BE Electrical Engineering', 'skills': ['Circuit Analysis', 'Power Systems'],
             'jobs': ['Electrical Engineer', 'Power Plant Engineer'], 'higher': ['M.Tech Electrical']}]},
                   'architecture-design': {'title': 'Architecture & Design', 'icon': 'fa-building',
                                           'courses': '4 Courses',
                                           'description': 'Creative field combining art, engineering and technology to design buildings, interiors, and products.',
                                           'duration': '4-5 Years', 'exam': ['NATA', 'JEE Paper 2', 'UCEED', 'NID DAT'],
                                           'degree': ['M.Arch', 'M.Des', 'Urban Planning',
                                                      'MBA Construction Management'], 'available_courses': [
                           {'name': 'B.Arch (Bachelor of Architecture)',
                            'skills': ['Architectural Drawing', '3D Modeling', 'Creativity', 'Structural Design'],
                            'jobs': ['Architect', 'Urban Designer', 'Landscape Architect', 'Project Architect'],
                            'higher': ['M.Arch', 'Urban Planning', 'Sustainable Architecture']},
                           {'name': 'B.Des (Interior Design)',
                            'skills': ['Creativity', 'Space Planning', 'Color Theory', '3D Visualization'],
                            'jobs': ['Interior Designer', 'Space Planner', 'Furniture Designer'],
                            'higher': ['M.Des Interior Design', 'MBA Design Management']},
                           {'name': 'B.Des (Industrial Design)',
                            'skills': ['Product Design', 'Sketching', 'Innovation', 'Prototyping'],
                            'jobs': ['Industrial Designer', 'Product Designer', 'Automobile Designer'],
                            'higher': ['M.Des Industrial Design', 'Product Design Specialization']},
                           {'name': 'B.Plan (Urban Planning)',
                            'skills': ['City Planning', 'GIS Mapping', 'Urban Development', 'Data Analysis'],
                            'jobs': ['Urban Planner', 'Town Planner', 'City Development Consultant'],
                            'higher': ['M.Plan', 'Urban Development', 'Smart City Planning']}]},
                   'computer-technology': {'title': 'Computer & Technology', 'icon': 'fa-laptop-code',
                                           'courses': '5 Courses',
                                           'description': 'Alternative computer science courses apart from engineering for careers in software, AI, and IT industries.',
                                           'duration': '3 Years', 'exam': ['University Entrance', 'CUET'],
                                           'degree': ['MCA', 'MSc Computer Science', 'MSc AI', 'MBA IT'],
                                           'available_courses': [{'name': 'BCA (Bachelor of Computer Applications)',
                                                                  'skills': ['Programming', 'Web Development',
                                                                             'Database Management'],
                                                                  'jobs': ['Software Developer', 'Web Developer',
                                                                           'Application Developer'],
                                                                  'higher': ['MCA', 'MSc Computer Science']},
                                                                 {'name': 'BSc Computer Science',
                                                                  'skills': ['Programming', 'Algorithms',
                                                                             'Data Structures'],
                                                                  'jobs': ['Software Engineer', 'Data Analyst',
                                                                           'System Developer'],
                                                                  'higher': ['MSc Computer Science', 'MCA']},
                                                                 {'name': 'BSc Artificial Intelligence',
                                                                  'skills': ['Python', 'Machine Learning',
                                                                             'AI Algorithms'],
                                                                  'jobs': ['AI Engineer', 'Machine Learning Engineer',
                                                                           'AI Researcher'],
                                                                  'higher': ['MSc Artificial Intelligence',
                                                                             'MSc Data Science']},
                                                                 {'name': 'BSc Information Technology',
                                                                  'skills': ['Networking', 'Database Management',
                                                                             'System Administration'],
                                                                  'jobs': ['IT Specialist', 'System Administrator',
                                                                           'Network Engineer'],
                                                                  'higher': ['MSc Information Technology', 'MBA IT']},
                                                                 {'name': 'BSc Data Science',
                                                                  'skills': ['Python', 'Statistics', 'Data Analysis'],
                                                                  'jobs': ['Data Scientist', 'Data Analyst',
                                                                           'Business Intelligence Analyst'],
                                                                  'higher': ['MSc Data Science', 'MSc AI']}]},
                   'defense-aviation': {'title': 'Defense & Aviation', 'icon': 'fa-fighter-jet', 'courses': '3 Courses',
                                        'description': 'Careers in Indian Armed Forces and aviation sector.',
                                        'duration': '3-4 Years', 'exam': ['NDA', 'CDS', 'AFCAT'],
                                        'degree': ['Defense Staff College', 'MSc Aviation'], 'available_courses': [
                           {'name': 'NDA Entry', 'skills': ['Leadership', 'Physical Fitness'],
                            'jobs': ['Army Officer', 'Navy Officer', 'Air Force Officer'],
                            'higher': ['Defense Staff College']},
                           {'name': 'Commercial Pilot Training', 'skills': ['Navigation', 'Aircraft Systems'],
                            'jobs': ['Commercial Pilot', 'Airline Pilot'], 'higher': ['Advanced Pilot Training']},
                           {'name': 'Aircraft Maintenance Engineering',
                            'skills': ['Mechanical Systems', 'Aircraft Maintenance'],
                            'jobs': ['Aircraft Engineer', 'Maintenance Engineer'], 'higher': ['MSc Aviation']}]},
                   'medical': {'title': 'Medical Courses', 'icon': 'fa-user-doctor', 'courses': '5 Courses',
                               'description': 'Become a doctor and work in hospitals, clinics, and healthcare sector.',
                               'duration': '5.5 Years', 'exam': ['NEET'], 'degree': ['MD', 'MS', 'DM'],
                               'available_courses': [{'name': 'MBBS', 'skills': ['Patient Care', 'Medical Diagnosis',
                                                                                 'Clinical Knowledge'],
                                                      'jobs': ['Doctor', 'Medical Officer', 'Surgeon'],
                                                      'higher': ['MD', 'MS', 'DM']},
                                                     {'name': 'BDS', 'skills': ['Dental Surgery', 'Patient Care'],
                                                      'jobs': ['Dentist', 'Dental Surgeon'], 'higher': ['MDS']},
                                                     {'name': 'BAMS', 'skills': ['Ayurvedic Medicine', 'Diagnosis'],
                                                      'jobs': ['Ayurvedic Doctor'], 'higher': ['MD Ayurveda']},
                                                     {'name': 'BHMS',
                                                      'skills': ['Homeopathy Treatment', 'Patient Analysis'],
                                                      'jobs': ['Homeopathic Doctor'], 'higher': ['MD Homeopathy']},
                                                     {'name': 'BUMS', 'skills': ['Unani Medicine', 'Herbal Treatment'],
                                                      'jobs': ['Unani Doctor'], 'higher': ['MD Unani']}]},
                   'life-science': {
                       'title': 'Life Science & Research',
                       'icon': 'fa-dna',
                       'courses': '4 Courses',
                       'description': 'Biology and research-related careers.',
                       'duration': '3 Years',
                       'exam': ['CUET'],
                       'degree': ['MSc', 'PhD'],

                       'available_courses': [

                           {'name': 'BSc Biotechnology',
                            'skills': ['Lab Techniques', 'Genetics', 'Research'],
                            'jobs': ['Biotechnologist', 'Research Scientist'],
                            'higher': ['MSc Biotechnology', 'PhD']},

                           {'name': 'BSc Microbiology',
                            'skills': ['Microbial Analysis', 'Lab Work'],
                            'jobs': ['Microbiologist', 'Lab Technician'],
                            'higher': ['MSc Microbiology']},

                           {'name': 'BSc Genetics',
                            'skills': ['DNA Analysis', 'Genetic Engineering'],
                            'jobs': ['Geneticist', 'Research Assistant'],
                            'higher': ['MSc Genetics', 'PhD']},

                           {'name': 'BSc Zoology',
                            'skills': ['Animal Biology', 'Research'],
                            'jobs': ['Zoologist', 'Wildlife Biologist'],
                            'higher': ['MSc Zoology']}
                       ]
                   },
                   'government': {'title': 'Government & Exams', 'icon': 'fa-building-columns',
                                  'fields': ['UPSC', 'MPSC', 'SSC', 'Banking', 'Defence', 'Police', 'Railways'],
                                  'jobs': ['IAS Officer', 'IPS Officer', 'IFS Officer', 'Bank PO', 'Army Officer',
                                           'Police Officer', 'Railway Officer']},
                   'commerce': {'title': 'Commerce & Management', 'icon': 'fa-chart-line',
                                'fields': ['CA', 'CS', 'CMA', 'B.Com', 'M.Com', 'BBA', 'MBA'],
                                'jobs': ['Chartered Accountant', 'Company Secretary', 'Cost Accountant', 'Accountant',
                                         'Financial Analyst', 'Business Manager', 'CEO']},
                   'creative': {'title': 'Creative & Design', 'icon': 'fa-palette',
                                'fields': ['Graphic Design', 'UI/UX Design', 'Fashion Design', 'Interior Design',
                                           'Animation', 'Photography'],
                                'jobs': ['Graphic Designer', 'UI/UX Designer', 'Fashion Designer', 'Interior Designer',
                                         'Animator', 'Photographer']},
                   'media': {'title': 'Media & Communication', 'icon': 'fa-microphone',
                             'fields': ['Journalism', 'Digital Marketing', 'PR', 'Content Writing', 'Video Production',
                                        'Radio'],
                             'jobs': ['Journalist', 'Digital Marketer', 'PR Manager', 'Content Writer',
                                      'Video Producer', 'Radio Jockey']},
                   'law': {'title': 'Law & Legal', 'icon': 'fa-gavel',
                           'fields': ['LLB', 'LLM', 'Corporate Law', 'Criminal Law', 'Civil Law', 'International Law'],
                           'jobs': ['Lawyer', 'Judge', 'Legal Advisor', 'Corporate Lawyer', 'Criminal Lawyer',
                                    'Legal Consultant']},
                   'aviation': {'title': 'Aviation & Travel', 'icon': 'fa-plane-departure',
                                'fields': ['Pilot Training', 'Air Hostess', 'Airport Management',
                                           'Aircraft Maintenance', 'Aviation Safety'],
                                'jobs': ['Pilot', 'Air Hostess', 'Airport Manager', 'Aircraft Technician',
                                         'Aviation Safety Officer']},
                   'teaching': {'title': 'Teaching & Academia', 'icon': 'fa-chalkboard-teacher',
                                'fields': ['B.Ed', 'M.Ed', 'PhD', 'School Teaching', 'College Teaching', 'Research'],
                                'jobs': ['School Teacher', 'College Professor', 'Research Scholar', 'Principal',
                                         'Education Consultant', 'Academic Writer']},'allied-health': {'title':'Allied Health / Paramedical','icon':'fa-user-nurse','courses':'4 Courses',
'description':'Support roles in healthcare like lab technicians, radiology, physiotherapy etc.',
'duration':'3-4 Years','exam':['NEET','State CET'],'degree':['BSc','Diploma'],
                                                                                                       'available_courses': [
                                                                                                           {
                                                                                                               'name': 'BSc Nursing',
                                                                                                               'skills': [
                                                                                                                   'Patient Care',
                                                                                                                   'Medical Knowledge'],
                                                                                                               'jobs': [
                                                                                                                   'Nurse',
                                                                                                                   'Healthcare Assistant'],
                                                                                                               'higher': [
                                                                                                                   'MSc Nursing']},

                                                                                                           {
                                                                                                               'name': 'BPT (Physiotherapy)',
                                                                                                               'skills': [
                                                                                                                   'Rehabilitation',
                                                                                                                   'Anatomy'],
                                                                                                               'jobs': [
                                                                                                                   'Physiotherapist'],
                                                                                                               'higher': [
                                                                                                                   'MPT']},

                                                                                                           {
                                                                                                               'name': 'BSc Dialysis Technology',
                                                                                                               'skills': [
                                                                                                                   'Dialysis Procedures',
                                                                                                                   'Patient Monitoring'],
                                                                                                               'jobs': [
                                                                                                                   'Dialysis Technician'],
                                                                                                               'higher': [
                                                                                                                   'MSc Dialysis Technology']},

                                                                                                           {
                                                                                                               'name': 'BSc Radiology',
                                                                                                               'skills': [
                                                                                                                   'Imaging Techniques',
                                                                                                                   'X-Ray',
                                                                                                                   'MRI'],
                                                                                                               'jobs': [
                                                                                                                   'Radiology Technician'],
                                                                                                               'higher': [
                                                                                                                   'MSc Radiology']},

                                                                                                           {
                                                                                                               'name': 'BSc Operation Theater Technology',
                                                                                                               'skills': [
                                                                                                                   'Surgical Assistance',
                                                                                                                   'OT Equipment'],
                                                                                                               'jobs': [
                                                                                                                   'OT Technician'],
                                                                                                               'higher': [
                                                                                                                   'MSc OTT']}
                                                                                  ]
                                                                                                       },
                   'pharmacy': {
                       'title': 'Pharmacy', 'icon': 'fa-pills', 'courses': '2 Courses',
                       'description': 'Medicine and drug-related careers.', 'duration': '4 Years',
                       'exam': ['NEET', 'MHT-CET'], 'degree': ['M.Pharm'],
                       'available_courses': [

                           {'name': 'B.Pharm (Bachelor of C)', 'skills': ['Chemistry', 'Drug Analysis'],
                            'jobs': ['Pharmacist', 'Drug Inspector'], 'higher': ['M.Pharm']},

                           {'name': 'Pharm.D (Doctor of Pharmacy )', 'skills': ['Clinical Pharmacy', 'Patient Care', 'Drug Therapy'],
                            'jobs': ['Clinical Pharmacist', 'Hospital Pharmacist'],
                            'higher': ['Pharm.D (Post Baccalaureate)', 'Research']}
                       ]
                   },

                   'agriculture': {
                       'title': 'Agriculture & Environmental Science',
                       'icon': 'fa-seedling',
                       'courses': '4 Courses',  # total courses
                       'description': 'Farming, environment, and sustainability careers.',
                       'duration': '4 Years',
                       'exam': ['ICAR'],
                       'degree': ['MSc Agriculture', 'PhD'],
                       'available_courses': [
                           {
                               'name': 'BSc Agriculture',
                               'skills': ['Soil Science', 'Farming Tech'],
                               'jobs': ['Agriculture Officer'],
                               'higher': ['MSc Agriculture']
                           },
                           {
                               'name': 'BSc Horticulture',
                               'skills': ['Plant Cultivation', 'Gardening Techniques'],
                               'jobs': ['Horticulturist', 'Agriculture Consultant'],
                               'higher': ['MSc Horticulture']
                           },
                           {
                               'name': 'BSc Forestry',
                               'skills': ['Forest Management', 'Wildlife Conservation'],
                               'jobs': ['Forester', 'Environmental Scientist'],
                               'higher': ['MSc Forestry']
                           },
                           {
                               'name': 'BSc Environmental Science',
                               'skills': ['Ecology', 'Sustainability', 'Pollution Management'],
                               'jobs': ['Environmental Analyst', 'Sustainability Consultant'],
                               'higher': ['MSc Environmental Science', 'PhD']
                           }
                       ]

                   },# ← Add Class 10 here
                   'class10': {
                       'title': 'Job Opportunities after Class 10',
                       'icon': 'fa-briefcase',
                       'description': 'Explore jobs you can pursue immediately after class 10.',

                       # TOP CARDS (same rahenge)
                       'cards': [
                           {'heading': '12+ Government Jobs', 'details': 'Various state and central government jobs.'},
                           {'heading': '12+ Private Jobs', 'details': 'Entry-level jobs in private companies.'},
                           {'heading': '15k–30k Salary Range',
                            'details': 'Jobs offering monthly salary between 15k to 30k.'},
                           {'heading': '50k+ Openings', 'details': 'Jobs with high demand and multiple openings.'}
                       ],

                       # ✅ ADD THIS
                       'government_jobs': [
                           {
                               'icon': 'fa-user-shield',
                               'job': 'Soldier (GD)',
                               'dept': 'Indian Army',
                               'salary': '₹21,700 - ₹69,100',
                               'exam': 'Physical + Written'
                           },
                           {
                               'icon': 'fa-envelope',
                               'job': 'Gramin Dak Sevak',
                               'dept': 'India Post',
                               'salary': '₹18,000 - ₹28,000',
                               'exam': 'Merit'
                           },
                           {
                               'icon': 'fa-shield-halved',
                               'job': 'Constable',
                               'dept': 'Police / CRPF',
                               'salary': '₹21,700+',
                               'exam': 'Physical + Written'
                           }
                       ],

                       'private_jobs': [
                           {
                               'icon': 'fa-laptop',
                               'job': 'Data Entry Operator',
                               'dept': 'Private Company',
                               'salary': '₹10k-20k',
                               'exam': 'No Exam'
                           },
                           {
                               'icon': 'fa-motorcycle',
                               'job': 'Delivery Executive',
                               'dept': 'Zomato / Swiggy',
                               'salary': '₹12k-25k',
                               'exam': 'No Exam'
                           },
                           {
                               'icon': 'fa-phone',
                               'job': 'Call Center Executive',
                               'dept': 'BPO',
                               'salary': '₹12k-25k',
                               'exam': 'Interview'
                           }
                       ]
                   }
                   }
    career = career_data.get(category)
    career_info = career_data.get(category, {'title': 'Unknown Career', 'icon': 'fa-compass', 'fields': [], 'jobs': []})
    return render_template('user/roadmap_details.html', career=career_info, category=category)

@app.route('/resources')
def resources():
    return render_template('user/resources.html')

@app.route('/about')
def about():
    return render_template('user/about.html')
@app.route('/contact')
def contact():
    return render_template('user/contact.html')

@app.route('/user/roadmap')
def user_roadmap():
    if 'user_id' not in session:
        flash('Please log in to access this page.', 'warning')
        return redirect(url_for('login'))

    return render_template('user/roadmap.html')

@app.route('/user/roadmap_details')
def user_roadmap_details():
    if 'user_id' not in session:
        flash('Please log in to access this page.', 'warning')
        return redirect(url_for('login'))

    category = request.args.get('category', '').lower()

    career_data = {'engineering': {'title': 'Engineering Courses', 'icon': 'fa-cogs', 'courses': '6 Courses',
                                   'description': 'Most popular career path for PCM students. Engineering offers diverse specializations.',
                                   'duration': '4 Years (B.Tech/B.E)',
                                   'exam': ['JEE Main', 'JEE Advanced', 'MHT-CET', 'BITSAT', 'VITEEE'],
                                   'degree': ['M.Tech', 'MBA', 'MS Abroad', 'PhD'], 'available_courses': [
            {'name': 'B.Tech / B.E Computer Engineering', 'skills': ['Programming', 'Problem Solving','Data Structures','Algorithms'],
             'jobs': ['Software Developer', 'Data Scientist', 'Web Developer'],
             'higher': ['M.Tech CS', 'MS Computer Science', 'MBA ']},
            {'name': 'B.Tech / B.E Electronics Engineering', 'skills': ['Circuit Design', 'Embedded Systems', 'Signal Processing'],
             'jobs': ['Electronics Engineer', 'VLSI Designer', 'Embedded Systems Engineer'],
             'higher': ['M.Tech VLSI', 'M.Tech Embedded', 'MBA IT']},
            {'name': 'B.Tech / B.E Mechanical Engineering', 'skills': ['Design', 'Thermodynamics', 'CAD'],
             'jobs': ['Mechanical Engineer', 'Automobile Engineer'], 'higher': ['M.Tech Mechanical', 'MBA']},
            {'name': 'B.Tech Civil Engineering', 'skills': ['Construction Planning', 'Surveying', 'Design'],
             'jobs': ['B.Tech / B.E Civil Engineering', 'Site Engineer'], 'higher': ['M.Tech Civil', 'Structural Engineering']},
            {'name': 'B.Tech / B.E Electrical Engineering', 'skills': ['Circuit Analysis', 'Power Systems'],
             'jobs': ['Electrical Engineer', 'Power Plant Engineer'], 'higher': ['M.Tech Electrical']}]},

                   'architecture-design': {'title': 'Architecture & Design', 'icon': 'fa-building',
                                           'courses': '4 Courses',
                                           'description': 'Creative field combining art, engineering and technology to design buildings, interiors, and products.',
                                           'duration': '4-5 Years', 'exam': ['NATA', 'JEE Paper 2', 'UCEED', 'NID DAT'],
                                           'degree': ['M.Arch', 'M.Des', 'Urban Planning',
                                                      'MBA Construction Management'], 'available_courses': [
                           {'name': 'B.Arch (Bachelor of Architecture)',
                            'skills': ['Architectural Drawing', '3D Modeling', 'Creativity', 'Structural Design'],
                            'jobs': ['Architect', 'Urban Designer', 'Landscape Architect', 'Project Architect'],
                            'higher': ['M.Arch', 'Urban Planning', 'Sustainable Architecture']},
                           {'name': 'B.Des (Interior Design)',
                            'skills': ['Creativity', 'Space Planning', 'Color Theory', '3D Visualization'],
                            'jobs': ['Interior Designer', 'Space Planner', 'Furniture Designer'],
                            'higher': ['M.Des Interior Design', 'MBA Design Management']},
                           {'name': 'B.Des (Industrial Design)',
                            'skills': ['Product Design', 'Sketching', 'Innovation', 'Prototyping'],
                            'jobs': ['Industrial Designer', 'Product Designer', 'Automobile Designer'],
                            'higher': ['M.Des Industrial Design', 'Product Design Specialization']},
                           {'name': 'B.Plan (Urban Planning)',
                            'skills': ['City Planning', 'GIS Mapping', 'Urban Development', 'Data Analysis'],
                            'jobs': ['Urban Planner', 'Town Planner', 'City Development Consultant'],
                            'higher': ['M.Plan', 'Urban Development', 'Smart City Planning']}]},
                   'computer-technology': {'title': 'Computer & Technology', 'icon': 'fa-laptop-code',
                                           'courses': '5 Courses',
                                           'description': 'Alternative computer science courses apart from engineering for careers in software, AI, and IT industries.',
                                           'duration': '3 Years', 'exam': ['University Entrance', 'CUET'],
                                           'degree': ['MCA', 'MSc Computer Science', 'MSc AI', 'MBA IT'],
                                           'available_courses': [{'name': 'BCA (Bachelor of Computer Applications)',
                                                                  'skills': ['Programming', 'Web Development',
                                                                             'Database Management'],
                                                                  'jobs': ['Software Developer', 'Web Developer',
                                                                           'Application Developer'],
                                                                  'higher': ['MCA', 'MSc Computer Science']},
                                                                 {'name': 'BSc Computer Science',
                                                                  'skills': ['Programming', 'Algorithms',
                                                                             'Data Structures'],
                                                                  'jobs': ['Software Engineer', 'Data Analyst',
                                                                           'System Developer'],
                                                                  'higher': ['MSc Computer Science', 'MCA']},
                                                                 {'name': 'BSc Artificial Intelligence',
                                                                  'skills': ['Python', 'Machine Learning',
                                                                             'AI Algorithms'],
                                                                  'jobs': ['AI Engineer', 'Machine Learning Engineer',
                                                                           'AI Researcher'],
                                                                  'higher': ['MSc Artificial Intelligence',
                                                                             'MSc Data Science']},
                                                                 {'name': 'BSc Information Technology',
                                                                  'skills': ['Networking', 'Database Management',
                                                                             'System Administration'],
                                                                  'jobs': ['IT Specialist', 'System Administrator',
                                                                           'Network Engineer'],
                                                                  'higher': ['MSc Information Technology', 'MBA IT']},
                                                                 {'name': 'BSc Data Science',
                                                                  'skills': ['Python', 'Statistics', 'Data Analysis'],
                                                                  'jobs': ['Data Scientist', 'Data Analyst',
                                                                           'Business Intelligence Analyst'],
                                                                  'higher': ['MSc Data Science', 'MSc AI']}]},
                   'defense-aviation': {'title': 'Defense & Aviation', 'icon': 'fa-fighter-jet', 'courses': '3 Courses',
                                        'description': 'Careers in Indian Armed Forces and aviation sector.',
                                        'duration': '3-4 Years', 'exam': ['NDA', 'CDS', 'AFCAT'],
                                        'degree': ['Defense Staff College', 'MSc Aviation'], 'available_courses': [
                           {'name': 'NDA Entry', 'skills': ['Leadership', 'Physical Fitness'],
                            'jobs': ['Army Officer', 'Navy Officer', 'Air Force Officer'],
                            'higher': ['Defense Staff College']},
                           {'name': 'Commercial Pilot Training', 'skills': ['Navigation', 'Aircraft Systems'],
                            'jobs': ['Commercial Pilot', 'Airline Pilot'], 'higher': ['Advanced Pilot Training']},
                           {'name': 'Aircraft Maintenance Engineering',
                            'skills': ['Mechanical Systems', 'Aircraft Maintenance'],
                            'jobs': ['Aircraft Engineer', 'Maintenance Engineer'], 'higher': ['MSc Aviation']}]},
                   'medical': {'title': 'Medical Courses', 'icon': 'fa-user-doctor', 'courses': '5 Courses',
                               'description': 'Become a doctor and work in hospitals, clinics, and healthcare sector.',
                               'duration': '5.5 Years', 'exam': ['NEET'], 'degree': ['MD', 'MS', 'DM'],
                               'available_courses': [{'name': 'MBBS', 'skills': ['Patient Care', 'Medical Diagnosis',
                                                                                 'Clinical Knowledge'],
                                                      'jobs': ['Doctor', 'Medical Officer', 'Surgeon'],
                                                      'higher': ['MD', 'MS', 'DM']},
                                                     {'name': 'BDS', 'skills': ['Dental Surgery', 'Patient Care'],
                                                      'jobs': ['Dentist', 'Dental Surgeon'], 'higher': ['MDS']},
                                                     {'name': 'BAMS', 'skills': ['Ayurvedic Medicine', 'Diagnosis'],
                                                      'jobs': ['Ayurvedic Doctor'], 'higher': ['MD Ayurveda']},
                                                     {'name': 'BHMS',
                                                      'skills': ['Homeopathy Treatment', 'Patient Analysis'],
                                                      'jobs': ['Homeopathic Doctor'], 'higher': ['MD Homeopathy']},
                                                     {'name': 'BUMS', 'skills': ['Unani Medicine', 'Herbal Treatment'],
                                                      'jobs': ['Unani Doctor'], 'higher': ['MD Unani']}]},
                   'government': {'title': 'Government & Exams', 'icon': 'fa-building-columns',
                                  'fields': ['UPSC', 'MPSC', 'SSC', 'Banking', 'Defence', 'Police', 'Railways'],
                                  'jobs': ['IAS Officer', 'IPS Officer', 'IFS Officer', 'Bank PO', 'Army Officer',
                                           'Police Officer', 'Railway Officer']},
                   'commerce': {'title': 'Commerce & Management', 'icon': 'fa-chart-line',
                                'fields': ['CA', 'CS', 'CMA', 'B.Com', 'M.Com', 'BBA', 'MBA'],
                                'jobs': ['Chartered Accountant', 'Company Secretary', 'Cost Accountant', 'Accountant',
                                         'Financial Analyst', 'Business Manager', 'CEO']},
                   'creative': {'title': 'Creative & Design', 'icon': 'fa-palette',
                                'fields': ['Graphic Design', 'UI/UX Design', 'Fashion Design', 'Interior Design',
                                           'Animation', 'Photography'],
                                'jobs': ['Graphic Designer', 'UI/UX Designer', 'Fashion Designer', 'Interior Designer',
                                         'Animator', 'Photographer']},
                   'media': {'title': 'Media & Communication', 'icon': 'fa-microphone',
                             'fields': ['Journalism', 'Digital Marketing', 'PR', 'Content Writing', 'Video Production',
                                        'Radio'],
                             'jobs': ['Journalist', 'Digital Marketer', 'PR Manager', 'Content Writer',
                                      'Video Producer', 'Radio Jockey']},
                   'law': {'title': 'Law & Legal', 'icon': 'fa-gavel',
                           'fields': ['LLB', 'LLM', 'Corporate Law', 'Criminal Law', 'Civil Law', 'International Law'],
                           'jobs': ['Lawyer', 'Judge', 'Legal Advisor', 'Corporate Lawyer', 'Criminal Lawyer',
                                    'Legal Consultant']},
                   'aviation': {'title': 'Aviation & Travel', 'icon': 'fa-plane-departure',
                                'fields': ['Pilot Training', 'Air Hostess', 'Airport Management',
                                           'Aircraft Maintenance', 'Aviation Safety'],
                                'jobs': ['Pilot', 'Air Hostess', 'Airport Manager', 'Aircraft Technician',
                                         'Aviation Safety Officer']},
                   'teaching': {'title': 'Teaching & Academia', 'icon': 'fa-chalkboard-teacher',
                                'fields': ['B.Ed', 'M.Ed', 'PhD', 'School Teaching', 'College Teaching', 'Research'],
                                'jobs': ['School Teacher', 'College Professor', 'Research Scholar', 'Principal',
                                         'Education Consultant', 'Academic Writer']},'pharmacy': {
    'title': 'Pharmacy',
    'icon': 'fa-pills',
    'courses': '2 Courses',
    'description': 'Pharmaceutical and medicine-related careers.',
    'duration': '4 Years',
    'exam': ['NEET', 'MHT-CET'],
    'degree': ['M.Pharm'],
    'available_courses': [
        {
            'name': 'B.Pharm',
            'skills': ['Pharmacology', 'Chemistry'],
            'jobs': ['Pharmacist', 'Drug Inspector'],
            'higher': ['M.Pharm']
        }
    ]
},  'life-science': {
                       'title': 'Life Science & Research ',
                       'icon': 'fa-dna',
                       'courses': '4 Courses',
                       'description': 'Biology and research-related careers.',
                       'duration': '3 Years',
                       'exam': ['CUET'],
                       'degree': ['MSc', 'PhD'],

                       'available_courses': [

                           {'name': 'BSc Biotechnology',
                            'skills': ['Lab Techniques', 'Genetics', 'Research'],
                            'jobs': ['Biotechnologist', 'Research Scientist'],
                            'higher': ['MSc Biotechnology', 'PhD']},

                           {'name': 'BSc Microbiology',
                            'skills': ['Microbial Analysis', 'Lab Work'],
                            'jobs': ['Microbiologist', 'Lab Technician'],
                            'higher': ['MSc Microbiology']},

                           {'name': 'BSc Genetics',
                            'skills': ['DNA Analysis', 'Genetic Engineering'],
                            'jobs': ['Geneticist', 'Research Assistant'],
                            'higher': ['MSc Genetics', 'PhD']},

                           {'name': 'BSc Zoology',
                            'skills': ['Animal Biology', 'Research'],
                            'jobs': ['Zoologist', 'Wildlife Biologist'],
                            'higher': ['MSc Zoology']}
                       ]
                   },

'agriculture': {
    'title': 'Agriculture',
    'icon': 'fa-seedling',
    'courses': '3 Courses',
    'description': 'Agriculture and environmental science careers.',
    'duration': '4 Years',
    'exam': ['ICAR'],
    'degree': ['MSc Agriculture'],
    'available_courses': [
        {
            'name': 'BSc Agriculture',
            'skills': ['Farming Tech', 'Soil Science'],
            'jobs': ['Agriculture Officer'],
            'higher': ['MSc Agriculture']
        }
    ]
}}


    career = career_data.get(category)

    career_info = career_data.get(category, {'title': 'Unknown Career', 'icon': 'fa-compass', 'fields': [], 'jobs': []})
    return render_template(
        'user/roadmap_details.html',
        career=career_info,
        category=category
    )
@app.route('/user/resources')
def user_resources():
    if 'user_id' not in session:
        flash('Please log in to access this page.', 'warning')
        return redirect(url_for('login'))

    return render_template('user/resources.html')

@app.route('/user/about')
def user_about():
    if 'user_id' not in session:
        flash('Please log in to access this page.', 'warning')
        return redirect(url_for('login'))

    return render_template('user/about.html')

@app.route('/user/contact')
def user_contact():
    if 'user_id' not in session:
        flash('Please log in to access this page.', 'warning')
        return redirect(url_for('login'))

    return render_template('user/contact.html')

@app.route('/submit_contact', methods=['POST'])
def submit_contact():
    if 'user_id' not in session:
        flash('Please log in to send a message.', 'warning')
        return redirect(url_for('login'))

    name = request.form.get('name')
    email = request.form.get('email')
    subject = request.form.get('subject')
    message = request.form.get('message')
    user_id = session.get('user_id')

    if not name or not email or not message:
        flash('Please fill all required fields.', 'danger')
        return redirect(url_for('user_contact'))

    try:
        cur = mysql.connection.cursor()
        cur.execute(
            "INSERT INTO user_contacts (user_id, name, email, subject, message) VALUES (%s, %s, %s, %s, %s)",
            (user_id, name, email, subject, message)
        )
        mysql.connection.commit()
        cur.close()
        flash('Message sent successfully!', 'success')
    except Exception as e:
        print("Error submitting contact form:", e)
        flash('Something went wrong. Please try again later.', 'danger')

    return redirect(url_for('user_contact'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        if not email or not password:
            flash('Please enter both email and password.', 'danger')
            return redirect(url_for('login'))

        try:
            cur = mysql.connection.cursor()
            cur.execute("SELECT id, password_hash, name FROM users WHERE email = %s", (email,))
            user = cur.fetchone()
            cur.close()

            if user and check_password_hash(user[1], password):
                session.permanent = True
                session['user_id'] = user[0]
                session['user_name'] = user[2]
                flash('Logged in successfully.', 'success')
                return redirect(url_for('user_dashboard'))

            else:
                flash('Invalid email or password.', 'danger')
                return redirect(url_for('login'))
        except Exception:
            flash('An error occurred while logging in.', 'danger')
            return redirect(url_for('login'))

    return render_template('login.html')

from flask_mail import Message

def send_otp_email(to_email, otp):
    msg = Message(
        subject="Password Reset OTP",
        sender=app.config['MAIL_USERNAME'],
        recipients=[to_email]
    )

    msg.body = f"""
Hello,

Your OTP for password reset is: {otp}

This OTP is valid for 10 minutes.
Do not share this OTP with anyone.

Thanks,
Career Roadmap Team
"""

    mail.send(msg)

import random
from datetime import datetime, timedelta

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email')

        cur = mysql.connection.cursor()
        cur.execute("SELECT id FROM users WHERE email=%s", (email,))
        user = cur.fetchone()

        if not user:
            flash("Email not registered", "danger")
            return redirect(url_for('forgot_password'))

        otp = str(random.randint(100000, 999999))
        expires_at = datetime.now() + timedelta(minutes=10)

        cur.execute(
            "INSERT INTO password_reset_otp (user_id, otp, expires_at) VALUES (%s,%s,%s)",
            (user[0], otp, expires_at)
        )
        mysql.connection.commit()
        cur.close()

        send_otp_email(email, otp)
        session['reset_user_id'] = user[0]

        flash("OTP sent to your email", "success")
        return redirect(url_for('verify_otp'))

    return render_template('forgot_password.html')

@app.route('/verify-otp', methods=['GET', 'POST'])
def verify_otp():
    if request.method == 'POST':
        otp_entered = request.form.get('otp')
        user_id = session.get('reset_user_id')

        cur = mysql.connection.cursor()
        cur.execute("""
            SELECT id FROM password_reset_otp
            WHERE user_id=%s AND otp=%s AND expires_at > NOW()
        """, (user_id, otp_entered))
        record = cur.fetchone()

        if not record:
            flash("Invalid or expired OTP", "danger")
            return redirect(url_for('verify_otp'))

        flash("OTP verified", "success")
        return redirect(url_for('reset_password'))

    return render_template('verify_otp.html')

@app.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    if request.method == 'POST':
        new_password = request.form.get('password')
        confirm = request.form.get('confirm_password')

        if new_password != confirm:
            flash("Passwords do not match", "danger")
            return redirect(url_for('reset_password'))

        password_hash = generate_password_hash(new_password)
        user_id = session.get('reset_user_id')

        cur = mysql.connection.cursor()
        cur.execute("UPDATE users SET password_hash=%s WHERE id=%s",
                    (password_hash, user_id))
        cur.execute("DELETE FROM password_reset_otp WHERE user_id=%s", (user_id,))
        mysql.connection.commit()
        cur.close()

        session.pop('reset_user_id', None)
        flash("Password reset successful. Please login.", "success")
        return redirect(url_for('login'))

    return render_template('reset_password.html')

@app.route('/resend-otp', methods=['POST'])
def resend_otp():
    user_id = session.get('reset_user_id')

    if not user_id:
        flash("Session expired. Please try again.", "danger")
        return redirect(url_for('forgot_password'))

    cur = mysql.connection.cursor()
    cur.execute("SELECT email FROM users WHERE id=%s", (user_id,))
    user = cur.fetchone()

    if not user:
        cur.close()
        flash("User not found.", "danger")
        return redirect(url_for('forgot_password'))

    email = user[0]

    # नया OTP generate
    otp = str(random.randint(100000, 999999))
    expires_at = datetime.now() + timedelta(minutes=10)

    # old OTP delete
    cur.execute("DELETE FROM password_reset_otp WHERE user_id=%s", (user_id,))

    # new OTP insert
    cur.execute(
        "INSERT INTO password_reset_otp (user_id, otp, expires_at) VALUES (%s,%s,%s)",
        (user_id, otp, expires_at)
    )
    mysql.connection.commit()
    cur.close()

    send_otp_email(email, otp)

    flash("New OTP sent to your email", "success")
    return redirect(url_for('verify_otp'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        # 1️⃣ Check empty fields
        if not name or not email or not password or not confirm_password:
            flash('Please fill in all fields.', 'danger')
            return redirect(url_for('register'))

        # 2️⃣ Password match check
        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return redirect(url_for('register'))

        try:
            cur = mysql.connection.cursor()

            # 3️⃣ Email already exists check
            cur.execute("SELECT id FROM users WHERE email = %s", (email,))
            existing_user = cur.fetchone()

            if existing_user:
                flash('Email already registered. Please login.', 'danger')
                cur.close()
                return redirect(url_for('register'))

            # 4️⃣ Insert new user
            password_hash = generate_password_hash(password)

            cur.execute(
                "INSERT INTO users (name, email, password_hash) VALUES (%s, %s, %s)",
                (name, email, password_hash)
            )
            mysql.connection.commit()
            cur.close()

            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('login'))

        except Exception as e:
            flash('Something went wrong. Please try again.', 'danger')
            return redirect(url_for('register'))

    return render_template('register.html')


@app.route('/user/dashboard')
def user_dashboard():
    if 'user_id' not in session:
        flash('Please log in to access the dashboard.', 'warning')
        return redirect(url_for('login'))

    user_id = session['user_id']
    cur = mysql.connection.cursor()

    # Get user data including avatar
    cur.execute("SELECT name, avatar FROM users WHERE id = %s", (user_id,))
    user_data = cur.fetchone()
    cur.close()

    if user_data:
        user_info = {
            'name': user_data[0],
            'avatar': user_data[1]
        }
        return render_template('user/dashboard.html', user_name=user_data[0], user=user_info)
    else:
        return render_template('user/dashboard.html', user_name=session.get('user_name'))


@app.route('/user/career-path')
def user_career_path():
    if 'user_id' not in session:
        flash('Please log in to access this page.', 'warning')
        return redirect(url_for('login'))

    return render_template('user/career_path.html')


# --- HSC Roadmap Multi‑Step Flow ---

@app.route('/roadmap/hsc')
def public_roadmap_hsc():
    """Public HSC stream selection page (no login required)."""
    return render_template('user/roadmap_hsc.html')



@app.route('/roadmap/hsc/<stream>')
def public_roadmap_hsc_stream(stream):
    """Public field selection page for a chosen HSC stream (no login required)."""
    # Define fields per stream
    stream_fields = {
        'science': ['PCM', 'PCB', 'PCMB'],
        'commerce': ['Accounts', 'Business Studies', 'Economics'],
        'arts': ['History', 'Geography', 'Political Science', 'Literature'],
        'diploma': ['diploma']
    }

    fields = stream_fields.get(stream.lower(), [])
    if not fields:
        flash('Invalid stream selected.', 'danger')
        return redirect(url_for('public_roadmap_hsc'))

    return render_template('user/roadmap_hsc_stream.html', stream=stream.title(), fields=fields)



@app.route('/roadmap/hsc/<stream>/<field>')
def public_roadmap_hsc_field(stream, field):
    """Public career paths page for a chosen stream and field (no login required)."""

    career_mapping = {'diploma': [
    {
        'slug': 'mechanical-diploma',
        'title': 'Mechanical & Production',
        'courses': 'Diploma Stream',
        'description': 'Covers machines, manufacturing and production systems.',
        'duration': '3 Years',
        'exam': ['State CET / Polytechnic Entrance'],
        'degree': ['Direct 2nd Year Engineering']
    },
    {
        'slug': 'civil-diploma',
        'title': 'Civil & Construction',
        'courses': 'Diploma Stream',
        'description': 'Focus on construction, buildings and infrastructure.',
        'duration': '3 Years',
        'exam': ['State CET'],
        'degree': ['BE Civil (Direct 2nd Year)']
    },
    {
        'slug': 'electrical-diploma',
        'title': 'Electrical & Electronics',
        'courses': 'Diploma Stream',
        'description': 'Study electrical systems, circuits and electronics.',
        'duration': '3 Years',
        'exam': ['Polytechnic Entrance'],
        'degree': ['BE Electrical']
    },
    {
        'slug': 'computer-diploma',
        'title': 'Computer & IT',
        'courses': 'Diploma Stream',
        'description': 'Programming, networking and IT systems.',
        'duration': '3 Years',
        'exam': ['State CET'],
        'degree': ['BE IT / CS']
    },
    {
        'slug': 'agriculture-diploma',
        'title': 'Agriculture & Environmental',
        'courses': 'Diploma Stream',
        'description': 'Focus on farming, environment and sustainability.',
        'duration': '3 Years',
        'exam': ['State Entrance'],
        'degree': ['BSc Agriculture']
    }
],'pcm': [{'slug': 'engineering', 'title': 'Engineering Courses', 'courses': '4 Courses',
                               'description': 'Most popular career path for PCM students.',
                               'duration': '4 Years (B.Tech/B.E)', 'exam': ['JEE Main', 'JEE Advanced', 'MHT-CET'],
                               'degree': ['M.Tech', 'MBA', 'MS']},
                              {'slug': 'architecture-design', 'title': 'Architecture & Design', 'courses': '4 Courses',
                               'description': 'Creative field combining art and technology.', 'duration': '4-5 Years',
                               'exam': ['NATA', 'JEE Paper 2'], 'degree': ['M.Arch']},

                              {'slug': 'computer-technology', 'title': 'Computer & Technology Courses',
                               'courses': '5 Courses',
                               'description': 'Alternative paths to engineering for computer science careers.',
                               'duration': '3 Years', 'exam': ['University Entrance'],
                               'degree': ['MCA', 'MSc Computer Science']},
                              {'slug': 'defense-aviation', 'title': 'Defense & Aviation', 'courses': '3 Courses',
                               'description': 'Careers in armed forces and aviation industry.', 'duration': '3-4 Years',
                               'exam': ['NDA', 'CDS', 'AFCAT'], 'degree': ['Defense Staff College']}],
                      'pcb': [{'slug': 'medical', 'title': 'Medical Courses', 'courses': '5 Courses',
                               'description': 'Become a doctor and work in hospitals and healthcare sector.',
                               'duration': '5.5 Years', 'exam': ['NEET'], 'degree': ['MD', 'MS', 'DM']},
                              {'slug': 'allied-health', 'title': 'Allied Health / Paramedical', 'courses': '6 Courses',
                               'description': 'Healthcare support careers like physiotherapy and radiology.',
                               'duration': '3-4 Years', 'exam': ['NEET', 'University Entrance'],
                               'degree': ['MSc Allied Health']},
                              {'slug': 'pharmacy', 'title': 'Pharmacy', 'courses': '2 Courses',
                               'description': 'Medicine research and pharmaceutical industry careers.',
                               'duration': '4 Years', 'exam': ['NEET', 'MHT-CET'], 'degree': ['M.Pharm']},
                              {'slug': 'life-science', 'title': 'Life Science & Research', 'courses': '6 Courses',
                               'description': 'Biology research careers.', 'duration': '3 Years', 'exam': ['CUET'],
                               'degree': ['MSc', 'PhD']},
                              {'slug': 'agriculture', 'title': 'Agriculture & Environmental Science',
                               'courses': '5 Courses',
                               'description': 'Careers in agriculture, forestry and environment.',
                               'duration': '3-4 Years', 'exam': ['ICAR', 'CUET'], 'degree': ['MSc Agriculture']}],
                      'pcmb': [{'slug': 'engineering', 'title': 'Engineering Courses', 'courses': '11 Courses',
                                'description': 'Engineering career options.', 'duration': '4 Years', 'exam': ['JEE'],
                                'degree': ['M.Tech']},
                               {'slug': 'medical', 'title': 'Medical Courses', 'courses': '5 Courses',
                                'description': 'Doctor and healthcare careers.', 'duration': '5.5 Years',
                                'exam': ['NEET'], 'degree': ['MD']},
                               {'slug': 'computer-technology', 'title': 'Computer & Technology', 'courses': '5 Courses',
                                'description': 'IT and software careers.', 'duration': '3 Years', 'exam': ['CUET'],
                                'degree': ['MCA']},
                               {'slug': 'architecture-design', 'title': 'Architecture & Design', 'courses': '4 Courses',
                                'description': 'Creative + technical field.', 'duration': '5 Years', 'exam': ['NATA'],
                                'degree': ['B.Arch']}],
                      'accounts': ['ca', 'cs', 'cma', 'finance'],
                      'business-studies': ['mba', 'marketing', 'hr', 'entrepreneurship'],
                      'economics': ['economics', 'banking', 'insurance', 'actuarial']}
    careers = career_mapping.get(field.lower(), [])

    if not careers:
        flash('No career paths found for this field.', 'warning')
        return redirect(url_for('public_roadmap_hsc_stream', stream=stream))

    return render_template(
        'user/roadmap_hsc_field.html',
        stream=stream.title(),
        field=field,
        careers=careers
    )


@app.route('/user/roadmap/hsc')
def roadmap_hsc():
    """HSC stream selection page (Science, Commerce, Arts, Diploma)."""
    if 'user_id' not in session:
        flash('Please log in to access this page.', 'warning')
        return redirect(url_for('login'))
    return render_template('user/roadmap_hsc.html')


@app.route('/user/roadmap/hsc/<stream>')
def roadmap_hsc_stream(stream):
    """Field selection page for a chosen HSC stream."""
    if 'user_id' not in session:
        flash('Please log in to access this page.', 'warning')
        return redirect(url_for('login'))

    # Define fields per stream
    stream_fields = {
        'science': ['PCM', 'PCB', 'PCMB'],
        'commerce': ['Accounts', 'Business Studies', 'Economics'],
        'arts': ['History', 'Geography', 'Political Science', 'Literature'],
        'diploma': ['Engineering', 'Pharmacy', 'Management', 'Computer Applications']
    }

    fields = stream_fields.get(stream.lower(), [])
    if not fields:
        flash('Invalid stream selected.', 'danger')
        return redirect(url_for('roadmap_hsc'))

    return render_template('user/roadmap_hsc_stream.html', stream=stream.title(), fields=fields)



@app.route('/user/roadmap/hsc/<stream>/<field>')
def roadmap_hsc_field(stream, field):
    """Roadmap details page for a chosen stream and field."""
    if 'user_id' not in session:
        flash('Please log in to access this page.', 'warning')
        return redirect(url_for('login'))

    # Map HSC fields to actual career roadmaps
    career_mapping = {'diploma': [
    {
        'slug': 'mechanical-diploma',
        'title': 'Mechanical & Production',
        'courses': '5 Streams',
        'description': 'Covers machines, manufacturing and production systems.',
        'duration': '3 Years',
        'exam': ['Polytechnic Entrance', 'State CET'],
        'degree': ['Direct 2nd Year Engineering'],
    },
    {
        'slug': 'civil-diploma',
        'title': 'Civil & Construction',
        'courses': '4 Streams',
        'description': 'Focus on construction, buildings and infrastructure.',
        'duration': '3 Years',
        'exam': ['State CET'],
        'degree': ['BE Civil (Direct 2nd Year)'],
    },
    {
        'slug': 'electrical-diploma',
        'title': 'Electrical & Electronics',
        'courses': '4 Streams',
        'description': 'Study electrical systems, circuits and electronics.',
        'duration': '3 Years',
        'exam': ['Polytechnic Entrance'],
        'degree': ['BE Electrical'],
    },
    {
        'slug': 'computer-diploma',
        'title': 'Computer & IT',
        'courses': '5 Streams',
        'description': 'Programming, networking and IT systems.',
        'duration': '3 Years',
        'exam': ['State CET'],
        'degree': ['BE IT / CS'],
    },
    {
        'slug': 'agriculture-diploma',
        'title': 'Agriculture & Environmental',
        'courses': '3 Streams',
        'description': 'Focus on farming, environment and sustainability.',
        'duration': '3 Years',
        'exam': ['State Entrance'],
        'degree': ['BSc Agriculture'],
    }
],

        'pcm': [
            {
                'slug': 'engineering',
                'title': 'Engineering Courses',
                'courses': '4 Courses',
                'description': 'Most popular career path for PCM students.',
                'duration': '4 Years (B.Tech/B.E)',
                'exam': ['JEE Main', 'JEE Advanced', 'MHT-CET'],
                'degree': ['M.Tech', 'MBA', 'MS']
            },

            {
                'slug': 'architecture-design',
                'title': 'Architecture & Design',
                'courses': '4 Courses',
                'description': 'Creative field combining art and technology.',
                'duration': '4-5 Years',
                'exam': ['NATA', 'JEE Paper 2'],
                'degree': ['M.Arch']
            },
            {
                'slug': 'computer-technology',
                'title': 'Computer & Technology Courses',
                'courses': '5 Courses',
                'description': 'Alternative paths to engineering.',
                'duration': '3 Years',
                'exam': ['University Entrance'],
                'degree': ['MCA', 'MSc Computer Science']
            },
            {
                'slug': 'defense-aviation',
                'title': 'Defense & Aviation',
                'courses': '3 Courses',
                'description': 'Careers in armed forces and aviation.',
                'duration': '3-4 Years',
                'exam': ['NDA', 'CDS', 'AFCAT'],
                'degree': ['Defense Staff College']
            }
        ],

        'pcb': [
            {
                'slug': 'medical',
                'title': 'Medical Courses',
                'courses': '5 Courses',
                'description': 'Doctor and healthcare careers.',
                'duration': '5.5 Years',
                'exam': ['NEET'],
                'degree': ['MD', 'MS']
            },
            {
                'slug': 'pharmacy',
                'title': 'Pharmacy',
                'courses': '1 Courses',
                'description': 'Medicine and pharma industry.',
                'duration': '4 Years',
                'exam': ['NEET', 'MHT-CET'],
                'degree': ['M.Pharm']
            },
            {
                'slug': 'life-science',
                'title': 'Life Science',
                'courses': '4 Courses',
                'description': 'Biology research careers.',
                'duration': '3 Years',
                'exam': ['CUET'],
                'degree': ['MSc', 'PhD']
            },
            {
                'slug': 'agriculture',
                'title': 'Agriculture',
                'courses': '1 Courses',
                'description': 'Farming & environment careers.',
                'duration': '3-4 Years',
                'exam': ['ICAR'],
                'degree': ['MSc Agriculture']
            }
        ],

        'pcmb': [
            {
                'slug': 'engineering',
                'title': 'Engineering Courses',
                'courses': '4 Courses',
                'description': 'Engineering options.',
                'duration': '4 Years',
                'exam': ['JEE'],
                'degree': ['M.Tech']
            },
            {
                'slug': 'medical',
                'title': 'Medical Courses',
                'courses': '5 Courses',
                'description': 'Doctor career.',
                'duration': '5.5 Years',
                'exam': ['NEET'],
                'degree': ['MD']
            },
            {
                'slug': 'computer-technology',
                'title': 'Computer & Technology',
                'courses': '5 Courses',
                'description': 'IT careers.',
                'duration': '3 Years',
                'exam': ['CUET'],
                'degree': ['MCA']
            },
            {
                'slug': 'architecture-design',
                'title': 'Architecture & Design',
                'courses': '4 Courses',
                'description': 'Creative + technical.',
                'duration': '5 Years',
                'exam': ['NATA'],
                'degree': ['B.Arch']
            }
        ], # Add new Class 10 category
        'class10': [
            {
                'slug': 'class10',
                'title': 'Job Opportunities after Class 10',
                'description': 'Explore jobs you can pursue immediately after completing class 10.',
                'cards': [
                    {'heading': '12+ Government Jobs', 'details': 'Various state and central government jobs.'},
                    {'heading': '12+ Private Jobs', 'details': 'Entry-level jobs in private companies.'},
                    {'heading': '15k–30k Salary Range', 'details': 'Jobs offering monthly salary between 15k to 30k.'},
                    {'heading': '50k+ Openings', 'details': 'Jobs with high demand and multiple openings.'}
                ]
            }
        ]
    }
    careers = career_mapping.get(field.lower(), [])
    if not careers:
        flash('No career paths found for this field.', 'warning')
        return redirect(url_for('roadmap_hsc_stream', stream=stream))

    return render_template('user/roadmap_hsc_field.html', stream=stream.title(), field=field, careers=careers)



@app.route('/user/cet-score')
def user_cet_score():
    if 'user_id' not in session:
        flash('Please log in first.', 'warning')
        return redirect(url_for('login'))

    return render_template('user/cet_score.html')

@app.route('/user/profile', methods=['GET', 'POST'])
def user_profile():
    if 'user_id' not in session:
        flash('Please log in to access your profile.', 'warning')
        return redirect(url_for('login'))

    user_id = session['user_id']
    cur = mysql.connection.cursor()

    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')

        # Handle avatar upload
        if 'avatar' in request.files:
            avatar_file = request.files['avatar']
            if avatar_file and avatar_file.filename != '':
                if allowed_file(avatar_file.filename):
                    filename = secure_filename(f"user_{user_id}_{avatar_file.filename}")
                    avatar_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)

                    # Remove old avatar if exists
                    cur.execute("SELECT avatar FROM users WHERE id = %s", (user_id,))
                    old_avatar = cur.fetchone()
                    if old_avatar and old_avatar[0]:
                        old_avatar_path = os.path.join(app.config['UPLOAD_FOLDER'], old_avatar[0])
                        if os.path.exists(old_avatar_path):
                            os.remove(old_avatar_path)

                    # Save new avatar
                    avatar_file.save(avatar_path)

                    # Update database with new avatar
                    cur.execute("UPDATE users SET avatar = %s WHERE id = %s", (filename, user_id))
                    mysql.connection.commit()
                    flash('Avatar updated successfully!', 'success')
                else:
                    flash('Invalid file type. Please upload PNG, JPG, JPEG, or GIF.', 'danger')

        if not name or not email:
            flash('Name and email are required.', 'danger')
        else:
            try:
                cur.execute("UPDATE users SET name = %s, email = %s WHERE id = %s", (name, email, user_id))
                mysql.connection.commit()
                session['user_name'] = name
                flash('Profile updated successfully!', 'success')
            except Exception as e:
                flash('An error occurred while updating your profile.', 'danger')

    cur.execute("SELECT name, email, avatar FROM users WHERE id = %s", (user_id,))
    user = cur.fetchone()
    cur.close()

    if user:
        user_data = {
            'name': user[0],
            'email': user[1],
            'avatar': user[2]
        }
        return render_template('user/profile.html', user=user_data)
    else:
        flash('User not found.', 'danger')
        return redirect(url_for('user_dashboard'))


@app.route('/user/change-password', methods=['GET', 'POST'])
def user_change_password():
    if 'user_id' not in session:
        flash('Please log in to access this page.', 'warning')
        return redirect(url_for('login'))
    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        if not current_password or not new_password or not confirm_password:
            flash('Please fill in all password fields.', 'danger')
            return redirect(url_for('user_profile'))

        if new_password != confirm_password:
            flash('New passwords do not match.', 'danger')
            return redirect(url_for('user_profile'))

        if len(new_password) < 6:
            flash('New password must be at least 6 characters long.', 'danger')
            return redirect(url_for('user_profile'))

        try:
            cur = mysql.connection.cursor()
            cur.execute("SELECT password_hash FROM users WHERE id = %s", (session['user_id'],))
            user = cur.fetchone()

            if user and check_password_hash(user[0], current_password):
                new_password_hash = generate_password_hash(new_password)
                cur.execute("UPDATE users SET password_hash = %s WHERE id = %s",
                            (new_password_hash, session['user_id']))
                mysql.connection.commit()
                cur.close()
                flash('Password changed successfully!', 'success')
            else:
                cur.close()
                flash('Current password is incorrect.', 'danger')
        except Exception as e:
            flash('An error occurred while changing your password.', 'danger')

        return redirect(url_for('user_profile'))

    return redirect(url_for('user_profile'))


@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully.', 'success')
    return redirect(url_for('index'))

@app.route('/api/analyze-career', methods=['POST'])
def analyze_career():
    if 'user_id' not in session:
        return jsonify({"success": False, "error": "Unauthorized"}), 401

    data = request.json or {}
    name = data.get("name", "")
    user_class = data.get("class", "")
    gender = data.get("gender", "")
    favorite_subject = data.get("favorite_subject", "")
    dream_career = data.get("dream_career", "")
    career_field = data.get("career_field", "")
    degree_course = data.get("degree_course", "")
    future_preference = data.get("future_preference", "")
    multiple_subjects = data.get("multiple_subjects", [])

    if not os.getenv("OPENAI_API_KEY"):
        return jsonify({
            "success": False,
            "error": "AI key is not configured. Please set OPENAI_API_KEY in .env"
        }), 500

    # ===================== COMPLETE CAREER GUIDANCE PROMPT =====================
    prompt = f"""
You are a highly experienced Career Guidance AI and industry mentor with 15+ years of experience.

Based on the detailed user profile below, provide COMPREHENSIVE career guidance with MULTIPLE suitable career paths.

User Profile:
Name: {name}
Class: {user_class}
Gender: {gender}
Favorite Subject: {favorite_subject}
Dream Career: {dream_career}
Career Field Interest: {career_field}
Degree Course Goal: {degree_course}
Future Study Preference: {future_preference}
Multiple Subjects: {', '.join(multiple_subjects) if multiple_subjects else 'None'}

TASK:
1. Analyze the user's complete profile comprehensively
2. Suggest 4 to 6 BEST-FIT career roles based on their interests, class, and goals
3. For EACH career role, provide the following COMPLETE details:

## Career Option <Number>: <Career Title>

### 🎯 Why This Career Fits You
Personalized explanation based on their profile, interests, and goals

### 📋 Detailed Role Description
Comprehensive explanation including:
- What this role involves day-to-day
- Key responsibilities and duties
- Industries and companies where this role is in demand
- Career growth opportunities and progression path
- Salary expectations and job market trends
- Work environment and culture
- Why this specifically matches their profile

### 🛠️ Essential Skills to Learn
**Technical Skills:**
- List all required technical competencies
- Software tools and platforms needed
- Programming languages or specialized knowledge

**Soft Skills:**
- Communication and interpersonal abilities
- Leadership and teamwork skills
- Problem-solving and analytical thinking

### 📚 Complete Learning Path
**Educational Requirements:**
- Required degrees and certifications
- Best colleges/institutions for this field
- Entrance exams and admission process

**Step-by-Step Learning Journey:**
- Foundation skills to build first
- Intermediate skills to develop
- Advanced skills for expertise
- Practical experience requirements

### 💼 Career Opportunities
**Job Roles Available:**
- Entry-level positions
- Mid-career opportunities
- Senior roles and specializations

**Top Companies:**
- Leading employers in this field
- Startups and innovative companies
- Government and public sector opportunities

### 🚀 Growth & Advancement
**Career Progression:**
- Typical career ladder
- Timeframes for promotions
- Salary growth potential

**Further Education:**
- Postgraduate opportunities
- Specialized certifications
- International career options

### 🎯 Success Tips
- Industry insights and secrets
- Common mistakes to avoid
- Networking strategies
- Portfolio building advice

FORMAT IN CLEAN MARKDOWN with proper headings, bullet points, and professional formatting.
Make it comprehensive, practical, and inspiring for the user.
"""

    try:
        response = client.chat.completions.create(
            model="google/gemini-2.0-flash-001",
            messages=[
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
        )

        # Content extract karna
        roadmap_text = response.choices[0].message.content
        
        # Extract career titles for recommended careers list
        import re
        career_pattern = r'## Career Option \d+: (.+)'
        career_matches = re.findall(career_pattern, roadmap_text)
        
        html_output = markdown.markdown(roadmap_text, extensions=['extra'])

        return jsonify({
            "success": True,
            "roadmap": html_output,
            "recommended_careers": career_matches
        })

    except Exception as e:
        print("Detailed Error:", traceback.format_exc())
        return jsonify({
            "success": False,
            "error": f"⚠️ AI Error: {str(e)}"
        }), 500




@app.route('/jobs/<category>')
def jobs_page(category):
    category = category.lower()

    career_data = {  # SAME DATA (copy from your existing)
        'class10': {
            'title': 'Jobs after Class 10',

            'government_jobs': [

                {
                    'icon': 'fa-briefcase',
                    'job': 'Group D Staff',
                    'dept': 'Railway / SSC',
                    'salary': '₹18,000 - ₹25,000',
                    'exam': 'SSC / Railway Exam'
                },

                {
                    'icon': 'fa-tasks',
                    'job': 'Multi Tasking Staff (MTS)',
                    'dept': 'Central Government',
                    'salary': '₹18,000 - ₹25,000',
                    'exam': 'SSC MTS'
                },

                {
                    'icon': 'fa-envelope',
                    'job': 'Gramin Dak Sevak',
                    'dept': 'India Post',
                    'salary': '₹18,000 - ₹28,000',
                    'exam': 'Merit'
                },

                {
                    'icon': 'fa-shield-halved',
                    'job': 'Constable',
                    'dept': 'Police / CRPF',
                    'salary': '₹21,700+',
                    'exam': 'Physical + Written'
                }
            ],

            'private_jobs': [

                {
                    'icon': 'fa-laptop',
                    'job': 'Data Entry Operator',
                    'dept': 'Private Company',
                    'salary': '₹10k-20k',
                    'exam': 'No Exam Required'
                },

                {
                    'icon': 'fa-motorcycle',
                    'job': 'Delivery Executive',
                    'dept': 'Zomato / Swiggy',
                    'salary': '₹12k-25k',
                    'exam': 'No Exam Required'
                },

                {
                    'icon': 'fa-car',
                    'job': 'Driver',
                    'dept': 'Transport / Cab Services',
                    'salary': '₹15k-30k',
                    'exam': 'Driving Test'
                },

                {
                    'icon': 'fa-desktop',
                    'job': 'Computer Operator',
                    'dept': 'Office / Company',
                    'salary': '₹10k-22k',
                    'exam': 'Basic Computer Test'
                },

                {
                    'icon': 'fa-user-shield',
                    'job': 'Security Guard',
                    'dept': 'Security Agency',
                    'salary': '₹12k-20k',
                    'exam': 'Physical Test'
                }
            ]
        }
    }

    career = career_data.get(category)

    return render_template('user/jobs.html', career=career)



# ---------------- POLYTECHNIC DATA ----------------
polytechnic_streams = {
    'mechanical': {
        'title': 'Mechanical & Production Stream',
        'overview': {
            'description': 'Study of mechanical systems, manufacturing, and production processes.',
            'duration': '3 Years',
            'exam': 'Polytechnic Entrance',
            'degree': 'B.Tech Mechanical',
            'higher': 'M.Tech Mechanical'
        }
    },
    'civil': {
        'title': 'Civil & Construction Stream',
        'overview': {
            'description': 'Study of civil engineering, construction techniques and surveying.',
            'duration': '3 Years',
            'exam': 'Polytechnic Entrance',
            'degree': 'B.Tech Civil',
            'higher': 'M.Tech Civil'
        }
    },
    'electrical': {
        'title': 'Electrical & Electronics Stream',
        'overview': {
            'description': 'Study of electrical systems, electronics, and automation.',
            'duration': '3 Years',
            'exam': 'Polytechnic Entrance',
            'degree': 'B.Tech Electrical',
            'higher': 'M.Tech Electrical'
        }
    },
    'computer': {
        'title': 'Computer & IT Stream',
        'overview': {
            'description': 'Study of computer systems, software, networking and AI.',
            'duration': '3 Years',
            'exam': 'Polytechnic Entrance',
            'degree': 'B.Tech CSE/IT (Lateral)',
            'higher': 'BE CSE / IT'
        }
    },
    'chemical': {
        'title': 'Chemical & Material Stream',
        'overview': {
            'description': 'Chemical processes and material science.',
            'duration': '3 Years',
            'exam': 'Polytechnic Entrance',
            'degree': 'B.Tech Chemical',
            'higher': 'M.Tech Chemical'
        }
    },
    'agriculture': {
        'title': 'Agriculture & Environmental Stream',
        'overview': {
            'description': 'Agriculture technology and environment.',
            'duration': '3 Years',
            'exam': 'Polytechnic Entrance',
            'degree': 'B.Tech Agriculture',
            'higher': 'MSc Agriculture'
        }
    }
}

# ---------------- POLYTECHNIC ROUTES ----------------
@app.route('/polytechnic')
def polytechnic():
    # Convert dict to list for template
    streams_list = []
    for slug, stream in polytechnic_streams.items():
        stream_copy = stream.copy()
        stream_copy['slug'] = slug
        stream_copy['description'] = stream['overview']['description']
        stream_copy['duration'] = stream['overview']['duration']
        stream_copy['exam'] = stream['overview']['exam']
        stream_copy['degree'] = stream['overview']['degree']
        streams_list.append(stream_copy)
    return render_template('user/polytechnic_streams.html', streams=streams_list)

@app.route('/polytechnic/<stream_slug>')
def polytechnic_stream_detail(stream_slug):
    stream_data = polytechnic_streams.get(stream_slug)
    if not stream_data:
        return "Stream not found", 404

    # ---------------- COURSES DATA ----------------
    polytechnic_courses = {

        'mechanical': [
            {
                'title': 'Mechanical Engineering',
                'description': 'Design, manufacturing and maintenance of machines.',
                'skills': ['CAD', 'Thermodynamics', 'Problem Solving'],
                'jobs': [
                    {'role': 'Mechanical Engineer', 'salary': '₹3-6 LPA'},
                    {'role': 'Design Engineer', 'salary': '₹4-7 LPA'}
                ],
                'higher': ['M.Tech Mechanical', 'MBA Operations']
            },
            {
                'title': 'Automobile Engineering',
                'description': 'Vehicle design and automotive systems.',
                'skills': ['Automotive Design', 'Engine Systems'],
                'jobs': [
                    {'role': 'Automobile Engineer', 'salary': '₹3-6 LPA'}
                ],
                'higher': ['M.Tech Automobile']
            },
            {
                'title': 'Industrial Engineering',
                'description': 'Optimization of production and operations.',
                'skills': ['Production Planning', 'Management'],
                'jobs': [
                    {'role': 'Production Manager', 'salary': '₹4-8 LPA'}
                ],
                'higher': ['MBA Operations']
            },
            {
                'title': 'Tool & Die Engineering',
                'description': 'Tool design and manufacturing.',
                'skills': ['Tool Design', 'Precision Engineering'],
                'jobs': [
                    {'role': 'Tool Engineer', 'salary': '₹3-5 LPA'}
                ],
                'higher': ['Specialization Courses']
            }
        ],

        'civil': [
            {
                'title': 'Civil Engineering',
                'description': 'Infrastructure and construction projects.',
                'skills': ['Surveying', 'AutoCAD'],
                'jobs': [{'role': 'Civil Engineer', 'salary': '₹3-6 LPA'}],
                'higher': ['M.Tech Civil']
            },
            {
                'title': 'Construction Engineering',
                'description': 'Construction management and planning.',
                'skills': ['Project Management'],
                'jobs': [{'role': 'Site Engineer', 'salary': '₹3-5 LPA'}],
                'higher': ['MBA Construction']
            },
            {
                'title': 'Environmental Engineering',
                'description': 'Environmental protection and sustainability.',
                'skills': ['Waste Management'],
                'jobs': [{'role': 'Environmental Engineer', 'salary': '₹4-7 LPA'}],
                'higher': ['M.Tech Environmental']
            },
            {
                'title': 'Survey Engineering',
                'description': 'Land surveying and mapping.',
                'skills': ['GPS Survey', 'Mapping'],
                'jobs': [{'role': 'Surveyor', 'salary': '₹2-5 LPA'}],
                'higher': ['Diploma Specialization']
            }
        ],

        'electrical': [
            {
                'title': 'Electrical Engineering',
                'description': 'Power systems and electrical machines.',
                'skills': ['Circuit Analysis'],
                'jobs': [{'role': 'Electrical Engineer', 'salary': '₹3-6 LPA'}],
                'higher': ['M.Tech Electrical']
            },
            {
                'title': 'Electronics Engineering',
                'description': 'Electronic circuits and devices.',
                'skills': ['PCB Design'],
                'jobs': [{'role': 'Electronics Engineer', 'salary': '₹3-6 LPA'}],
                'higher': ['M.Tech Electronics']
            },
            {
                'title': 'Electronics & Telecommunication',
                'description': 'Communication systems and networks.',
                'skills': ['Networking'],
                'jobs': [{'role': 'Telecom Engineer', 'salary': '₹3-6 LPA'}],
                'higher': ['M.Tech E&TC']
            },
            {
                'title': 'Instrumentation Engineering',
                'description': 'Measurement and control systems.',
                'skills': ['Automation'],
                'jobs': [{'role': 'Instrumentation Engineer', 'salary': '₹4-7 LPA'}],
                'higher': ['M.Tech Instrumentation']
            }
        ],

        'computer': [
            {
                'title': 'Computer Engineering',
                'description': 'Software and system development.',
                'skills': ['Programming', 'Algorithms'],
                'jobs': [{'role': 'Software Developer', 'salary': '₹4-10 LPA'}],
                'higher': ['M.Tech CS', 'MS CS']
            },
            {
                'title': 'Artificial Intelligence',
                'description': 'AI and machine learning systems.',
                'skills': ['ML', 'Python'],
                'jobs': [{'role': 'AI Engineer', 'salary': '₹6-12 LPA'}],
                'higher': ['MS AI']
            },
            {
                'title': 'Data Science',
                'description': 'Data analysis and insights.',
                'skills': ['Python', 'Statistics'],
                'jobs': [{'role': 'Data Scientist', 'salary': '₹6-15 LPA'}],
                'higher': ['MS Data Science']
            },
            {
                'title': 'Cyber Security',
                'description': 'Security systems and ethical hacking.',
                'skills': ['Ethical Hacking'],
                'jobs': [{'role': 'Security Analyst', 'salary': '₹5-10 LPA'}],
                'higher': ['Cyber Security Certification']
            }
        ],

        'chemical': [
            {
                'title': 'Chemical Engineering',
                'description': 'Chemical processes and production.',
                'skills': ['Process Design'],
                'jobs': [{'role': 'Chemical Engineer', 'salary': '₹4-8 LPA'}],
                'higher': ['M.Tech Chemical']
            },
            {
                'title': 'Plastic Engineering',
                'description': 'Polymer and plastic technology.',
                'skills': ['Polymer Science'],
                'jobs': [{'role': 'Plastic Engineer', 'salary': '₹3-6 LPA'}],
                'higher': ['Specialization']
            },
            {
                'title': 'Metallurgy Engineering',
                'description': 'Metal extraction and processing.',
                'skills': ['Material Science'],
                'jobs': [{'role': 'Metallurgical Engineer', 'salary': '₹4-7 LPA'}],
                'higher': ['M.Tech Metallurgy']
            },
            {
                'title': 'Petroleum Engineering',
                'description': 'Oil and gas exploration.',
                'skills': ['Drilling'],
                'jobs': [{'role': 'Petroleum Engineer', 'salary': '₹6-12 LPA'}],
                'higher': ['M.Tech Petroleum']
            }
        ],

        'agriculture': [
            {
                'title': 'Agriculture Engineering',
                'description': 'Farm machinery and irrigation.',
                'skills': ['Irrigation'],
                'jobs': [{'role': 'Agri Engineer', 'salary': '₹3-6 LPA'}],
                'higher': ['MSc Agriculture']
            },
            {
                'title': 'Dairy Technology',
                'description': 'Milk processing and dairy products.',
                'skills': ['Food Processing'],
                'jobs': [{'role': 'Dairy Technologist', 'salary': '₹3-5 LPA'}],
                'higher': ['MSc Dairy']
            },
            {
                'title': 'Food Technology',
                'description': 'Food production and safety.',
                'skills': ['Food Safety'],
                'jobs': [{'role': 'Food Technologist', 'salary': '₹3-6 LPA'}],
                'higher': ['MSc Food Tech']
            },
            {
                'title': 'Environmental Engineering',
                'description': 'Environmental protection systems.',
                'skills': ['Sustainability'],
                'jobs': [{'role': 'Environmental Engineer', 'salary': '₹4-7 LPA'}],
                'higher': ['M.Tech Environmental']
            }
        ]
    }
    courses = polytechnic_courses.get(stream_slug, [])

    return render_template(
        'user/polytechnic_stream_detail.html',
        stream_title=stream_data['title'],
        overview=stream_data.get('overview', {}),
        courses=courses  # ✅ IMPORTANT FIX
    )

# ---------------- ITI Trades ----------------

trade_info = {
        'mechanical_manufacturing': {
            'description': 'Mechanical systems, manufacturing and maintenance.',
            'duration': '1-2 Years',
            'exam': 'ITI Entrance',
            'higher': 'Diploma / Advanced Courses'
        },
        'automobile_transport': {
            'description': 'Vehicle repair and transport systems.',
            'duration': '1-2 Years',
            'exam': 'ITI Entrance',
            'higher': 'Diploma in Automobile'
        },
        'electrical_electronics': {
            'description': 'Electrical wiring, electronics and automation.',
            'duration': '1-2 Years',
            'exam': 'ITI Entrance',
            'higher': 'Diploma in Electrical'
        },
        'computer_it_modern_tech': {
            'description': 'Computer, IT and modern technologies.',
            'duration': '1-2 Years',
            'exam': 'ITI Entrance',
            'higher': 'Diploma / Certifications'
        },
        'civil_construction_surveying': {
            'description': 'Construction, surveying and civil work.',
            'duration': '1-2 Years',
            'exam': 'ITI Entrance',
            'higher': 'Diploma in Civil'
        }
    }
@app.route('/iti')
def iti_trades():
    trades = []

    for slug, info in trade_info.items():
        trades.append({
            'slug': slug,
            'title': slug.replace('_', ' ').title(),
            'description': info['description'],
            'duration': info['duration'],
            'exam': info['exam'],
            'degree': 'ITI Certificate'
        })

    return render_template('user/iti_trades.html', trades=trades)
# ---------------- ITI Trade Detail ----------------
@app.route('/iti/<trade>')
def iti_trade_detail(trade):
    data = {
    'mechanical_manufacturing': [
        {
            'name': 'Fitter',
            'skills': ['Assembly', 'Measurement', 'Tool Handling'],
            'jobs': [{'role': 'Fitter', 'salary': '3-5 LPA'}],
            'higher': ['Advanced Fitting Course']
        },
        {
            'name': 'Turner',
            'skills': ['Lathe Operation', 'Precision Turning', 'Tool Setup'],
            'jobs': [{'role': 'Turner', 'salary': '4-6 LPA'}],
            'higher': ['Diploma in Mechanical Engineering']
        },
        {
            'name': 'Machinist',
            'skills': ['Milling', 'Grinding', 'Machine Programming'],
            'jobs': [{'role': 'Machinist', 'salary': '4-7 LPA'}],
            'higher': ['Diploma in Machining Technology']
        },
        {
            'name': 'Welder',
            'skills': ['Arc Welding', 'Gas Welding', 'Metal Fabrication'],
            'jobs': [{'role': 'Welder', 'salary': '4-7 LPA'}],
            'higher': ['Advanced Welding Course']
        }
    ],
        'automobile_transport': [
            {
                'name': 'Mechanic - Motor Vehicle',
                'skills': ['Engine Repair', 'Diagnostics', 'Vehicle Maintenance'],
                'jobs': [{'role': 'Motor Vehicle Mechanic', 'salary': '3-5 LPA'}],
                'higher': ['Advanced Automobile Course']
            },
            {
                'name': 'Auto Electrician',
                'skills': ['Sensors', 'ECU Programming', 'Electrical Systems'],
                'jobs': [{'role': 'Auto Electrician', 'salary': '4-6 LPA'}],
                'higher': ['Diploma in Automobile Engineering']
            },
            {
                'name': 'Mechanic - Diesel Engine',
                'skills': ['Diesel Engine Repair', 'Fuel System Maintenance'],
                'jobs': [{'role': 'Diesel Engine Mechanic', 'salary': '4-6 LPA'}],
                'higher': ['Diploma in Diesel Technology']
            },
            {
                'name': 'EV Technician',
                'skills': ['Battery Management', 'Electric Vehicle Systems', 'Diagnostics'],
                'jobs': [{'role': 'EV Technician', 'salary': '4-7 LPA'}],
                'higher': ['Advanced EV Technology Course']
            }
        ],
        'electrical_electronics': [
            {
                'name': 'Electrician',
                'skills': ['Wiring', 'Circuit Testing', 'Safety Procedures'],
                'jobs': [{'role': 'Electrician', 'salary': '3-5 LPA'}],
                'higher': ['Diploma in Electrical Engineering']
            },
            {
                'name': 'Electronics Mechanic',
                'skills': ['Soldering', 'Circuit Assembly', 'Component Testing'],
                'jobs': [{'role': 'Electronics Mechanic', 'salary': '4-6 LPA'}],
                'higher': ['Advanced Electronics Course']
            },
            {
                'name': 'Instrument Mechanic',
                'skills': ['Calibration', 'Measuring Instruments', 'Troubleshooting'],
                'jobs': [{'role': 'Instrument Mechanic', 'salary': '4-7 LPA'}],
                'higher': ['Diploma in Instrumentation']
            },
            {
                'name': 'Electrical Installation',
                'skills': ['Panel Wiring', 'Load Testing', 'Safety Compliance'],
                'jobs': [{'role': 'Electrical Installer', 'salary': '4-6 LPA'}],
                'higher': ['Advanced Electrical Installation Course']
            }
        ],
        'computer_it_modern_tech': [
            {
                'name': 'COPA (Computer Operator & Programming Assistant)',
                'skills': ['Typing', 'Office Tools', 'Basic Programming'],
                'jobs': [{'role': 'COPA', 'salary': '3-5 LPA'}],
                'higher': ['Diploma in Computer Applications']
            },
            {
                'name': 'Computer Hardware & Network Maintenance',
                'skills': ['Hardware Assembly', 'Troubleshooting', 'Network Setup'],
                'jobs': [{'role': 'Hardware & Network Technician', 'salary': '4-6 LPA'}],
                'higher': ['Diploma in IT Hardware & Networking']
            },
            {
                'name': 'IoT Technician',
                'skills': ['IoT Devices', 'Automation', 'Sensor Integration'],
                'jobs': [{'role': 'IoT Technician', 'salary': '4-7 LPA'}],
                'higher': ['Advanced IoT Course']
            },
            {
                'name': 'AI Programming Assistant',
                'skills': ['Python', 'Machine Learning Basics', 'Data Handling'],
                'jobs': [{'role': 'AI Assistant', 'salary': '4-7 LPA'}],
                'higher': ['Advanced AI Programming Course']
            }
        ],
        'civil_construction_surveying': [
            {
                'name': 'Draughtsman (Civil)',
                'skills': ['Technical Drawing', 'Blueprint Reading', 'AutoCAD'],
                'jobs': [{'role': 'Civil Draughtsman', 'salary': '3-5 LPA'}],
                'higher': ['Diploma in Civil Drafting']
            },
            {
                'name': 'Surveyor',
                'skills': ['Land Measurement', 'Topography', 'Survey Instruments'],
                'jobs': [{'role': 'Surveyor', 'salary': '4-6 LPA'}],
                'higher': ['Advanced Surveying Diploma']
            },
            {
                'name': 'Plumber',
                'skills': ['Pipe Fitting', 'Water Systems', 'Leak Repair'],
                'jobs': [{'role': 'Plumber', 'salary': '3-5 LPA'}],
                'higher': ['Advanced Plumbing Course']
            },
            {
                'name': 'Carpenter',
                'skills': ['Woodwork', 'Furniture Making', 'Joinery'],
                'jobs': [{'role': 'Carpenter', 'salary': '3-5 LPA'}],
                'higher': ['Diploma in Carpentry and Woodwork']
            }
        ]
    }

    trade_title_map = {
        'mechanical_manufacturing':'Mechanical & Manufacturing',
        'automobile_transport':'Automobile & Transport',
        'electrical_electronics':'Electrical & Electronics',
        'computer_it_modern_tech':'Computer / IT & Modern Tech',
        'civil_construction_surveying':'Civil / Construction / Surveying'
    }

    courses = data.get(trade, [])
    trade_title = trade_title_map.get(trade, 'Unknown Trade')
    overview = trade_info.get(trade, {})

    return render_template('user/iti_trades_detail.html', courses=courses, trade_title=trade_title, overview=overview  )



@app.route('/paramedical')
def paramedical_categories():
    categories = [
        {
            'slug': 'lab',
            'title': 'Laboratory / Diagnostic',
            'description': 'Medical lab testing and diagnostics.',
            'duration': '6 months - 2 Years',
            'exam': 'State Paramedical Entrance',
            'degree': 'DMLT / BMLT'
        },
        {
            'slug': 'radiology',
            'title': 'Radiology / Imaging',
            'description': 'X-ray, CT, MRI imaging technology.',
            'duration': '6 months - 2 Years',
            'exam': 'State Paramedical Entrance',
            'degree': 'BSc Radiology'
        },
        {
            'slug': 'ot',
            'title': 'Operation Theatre & Critical Care',
            'description': 'Surgical and ICU support.',
            'duration': '6 months - 1 Year',
            'exam': 'State Paramedical Entrance',
            'degree': 'BSc OT Technology'
        },
        {
            'slug': 'dialysis',
            'title': 'Dialysis & Cardiology',
            'description': 'Kidney and heart care support.',
            'duration': '6 months - 1 Year',
            'exam': 'State Paramedical Entrance',
            'degree': 'BSc Dialysis'
        },
        {
            'slug': 'nursing',
            'title': 'Nursing & Midwifery',
            'description': 'Patient care and nursing.',
            'duration': '6 months - 2 Years',
            'exam': 'Nursing Entrance',
            'degree': 'GNM / BSc Nursing'
        }
    ]

    return render_template('user/paramedical_categories.html', categories=categories)

@app.route('/paramedical/<category>')
def paramedical_detail(category):

    data = {
        # ✅ OT CATEGORY
        'ot': {
            'title': 'Operation Theatre & Critical Care',
            'description': 'Surgical and ICU support.',
            'duration': '6 months - 1 Year',
            'courses': [
                {
                    'short': 'OT Tech',
                    'name': 'Diploma in Operation Theatre Technology',
                    'skills': ['Surgery Assistance', 'Sterilization'],
                    'jobs': ['OT Technician'],
                    'salary': '₹2-4 LPA'
                },
                {
                    'short': 'ICU Tech',
                    'name': 'Certificate in ICU Technology',
                    'skills': ['Critical Care', 'Monitoring'],
                    'jobs': ['ICU Technician'],
                    'salary': '₹3-5 LPA'
                },
                {
                    'short': 'Anesthesia',
                    'name': 'Diploma in Anesthesia Technology',
                    'skills': ['Anesthesia Support'],
                    'jobs': ['Anesthesia Technician'],
                    'salary': '₹3-6 LPA'
                },
                {
                    'short': 'BSc OT',
                    'name': 'BSc in Operation Theatre Technology',
                    'skills': ['Advanced Surgical Support'],
                    'jobs': ['Senior OT Technician'],
                    'salary': '₹5-8 LPA'
                }
            ]
        },

        # ✅ DIALYSIS CATEGORY
        'dialysis': {
            'title': 'Dialysis & Cardiology',
            'description': 'Kidney and heart care support.',
            'duration': '6 months - 1 Year',
            'courses': [
                {
                    'short': 'Dialysis',
                    'name': 'Diploma in Dialysis Technology',
                    'skills': ['Dialysis Machine', 'Patient Care'],
                    'jobs': ['Dialysis Technician'],
                    'salary': '₹2-5 LPA'
                },
                {
                    'short': 'Cardio',
                    'name': 'Diploma in Cardiology Technology',
                    'skills': ['ECG', 'Heart Monitoring'],
                    'jobs': ['Cardiology Technician'],
                    'salary': '₹3-6 LPA'
                },
                {
                    'short': 'ECG Tech',
                    'name': 'Certificate in ECG Technology',
                    'skills': ['ECG Analysis'],
                    'jobs': ['ECG Technician'],
                    'salary': '₹2-4 LPA'
                },
                {
                    'short': 'BSc Dialysis',
                    'name': 'BSc in Dialysis Technology',
                    'skills': ['Advanced Renal Care'],
                    'jobs': ['Senior Dialysis Technician'],
                    'salary': '₹5-8 LPA'
                }
            ]
        },

        # ✅ NURSING CATEGORY
        'nursing': {
            'title': 'Nursing & Midwifery',
            'description': 'Patient care and nursing.',
            'duration': '6 months - 2 Years',
            'courses': [
                {
                    'short': 'ANM',
                    'name': 'Auxiliary Nursing Midwifery',
                    'skills': ['Basic Nursing', 'Patient Care'],
                    'jobs': ['Nurse Assistant'],
                    'salary': '₹2-4 LPA'
                },
                {
                    'short': 'GNM',
                    'name': 'General Nursing and Midwifery',
                    'skills': ['Clinical Care', 'Ward Management'],
                    'jobs': ['Staff Nurse'],
                    'salary': '₹3-6 LPA'
                },
                {
                    'short': 'BSc Nursing',
                    'name': 'Bachelor of Science in Nursing',
                    'skills': ['Advanced Nursing'],
                    'jobs': ['Registered Nurse'],
                    'salary': '₹4-8 LPA'
                },
                {
                    'short': 'Post Basic',
                    'name': 'Post Basic BSc Nursing',
                    'skills': ['Specialized Nursing'],
                    'jobs': ['Senior Nurse'],
                    'salary': '₹5-9 LPA'
                }
            ]
        },


        'lab': {
            'title': 'Laboratory / Diagnostic',
            'description': 'Courses focused on medical lab testing and diagnostics.',
            'duration': '6 months - 2 Years',
            'courses': [
                {
                    'short': 'DMLT',
                    'name': 'Diploma in Medical Laboratory Technology',
                    'skills': ['Blood Testing', 'Microscopy'],
                    'jobs': ['Lab Technician'],
                    'salary': '₹2-5 LPA'
                },
                {
                    'short': 'BMLT',
                    'name': 'Bachelor of Medical Laboratory Technology',
                    'skills': ['Biochemistry', 'Microbiology'],
                    'jobs': ['Lab Technologist'],
                    'salary': '₹3-6 LPA'
                },
                {
                    'short': 'Phlebotomy',
                    'name': 'Certificate Course in Phlebotomy',
                    'skills': ['Sample Collection'],
                    'jobs': ['Phlebotomist'],
                    'salary': '₹2-4 LPA'
                },
                {
                    'short': 'Pathology',
                    'name': 'Diploma in Pathology Technology',
                    'skills': ['Diagnostics'],
                    'jobs': ['Pathology Technician'],
                    'salary': '₹3-5 LPA'
                }
            ]
        },

        'radiology': {
            'title': 'Radiology / Imaging',
            'description': 'X-ray, CT, MRI imaging technology.',
            'duration': '6 months - 2 Years',
            'courses': [
                {
                    'short': 'X-Ray',
                    'name': 'Diploma in X-Ray Technology',
                    'skills': ['X-Ray', 'Patient Positioning'],
                    'jobs': ['Radiology Technician'],
                    'salary': '₹2-4 LPA'
                },
                {
                    'short': 'CT Scan',
                    'name': 'Certificate in CT Scan Technology',
                    'skills': ['CT Scan', 'Imaging'],
                    'jobs': ['CT Technician'],
                    'salary': '₹3-5 LPA'
                },
                {
                    'short': 'MRI',
                    'name': 'Certificate in MRI Technology',
                    'skills': ['MRI', 'Imaging'],
                    'jobs': ['MRI Technician'],
                    'salary': '₹4-6 LPA'
                },
                {
                    'short': 'BSc Radio',
                    'name': 'BSc in Radiology and Imaging Technology',
                    'skills': ['Advanced Imaging'],
                    'jobs': ['Radiologist Assistant'],
                    'salary': '₹5-8 LPA'
                }
            ]
        }

    }

    selected = data.get(category)

    return render_template(
        'user/paramedical_detail.html',
        category=selected
    )
if __name__ == '__main__':
    app.run(debug=True)


