from flask import Flask, request, jsonify
from flask_jwt_extended import (
    JWTManager, create_access_token, create_refresh_token,
    jwt_required, get_jwt_identity, get_jwt
)
from flask_migrate import Migrate
from extensions import db, bcrypt, jwt
from config import SQLALCHEMY_DATABASE_URI, SQLALCHEMY_TRACK_MODIFICATIONS
from datetime import timedelta, datetime
from models import User, Task, Company

# Initialize Flask app
app = Flask(__name__)

# Configure database
app.config['SQLALCHEMY_DATABASE_URI'] = SQLALCHEMY_DATABASE_URI
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = SQLALCHEMY_TRACK_MODIFICATIONS
app.config['JWT_SECRET_KEY'] = 'your_secret_key'

# Set Token Expiry Times
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(minutes=50)
app.config['JWT_REFRESH_TOKEN_EXPIRES'] = timedelta(days=30)

#Initialize Extensions
db.init_app(app)
bcrypt.init_app(app)
jwt.init_app(app)
migrate = Migrate(app, db)  #Database migration setup

blacklisted_tokens = set()

#User Registration
import re

@app.route('/register', methods=['POST'])
def register():
    try:
        username = request.form.get('username')
        mobile_no = request.form.get('mobile_no')
        password = request.form.get('password')
        profile_pic = request.files.get('profile_pic')
        company_name = request.form.get('company_name')  # Accept company name

        if not username or not mobile_no or not password or not company_name:
            return jsonify({"error": "Missing required fields"}), 400

        #Check if the company exists, otherwise create it
        company = Company.query.filter_by(name=company_name).first()
        if not company:
            company = Company(name=company_name)  # Create new company
            db.session.add(company)
            db.session.commit()

        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')

        profile_pic_path = None
        if profile_pic:
            profile_pic_path = f"uploads/{profile_pic.filename}"
            profile_pic.save(profile_pic_path)

        new_user = User(username=username, mobile_no=mobile_no, password=hashed_password, profile_pic=profile_pic_path, company_id=company.id)
        db.session.add(new_user)
        db.session.commit()

        return jsonify({"message": f"User registered successfully in company '{company.name}'!"}), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500

#User Login
@app.route('/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')

        user = User.query.filter_by(username=username).first()

        if user and bcrypt.check_password_hash(user.password, password):
            access_token = create_access_token(identity=user.id)
            refresh_token = create_refresh_token(identity=user.id)
            return jsonify({
                "message": "Login successful!",
                "access_token": access_token,
                "refresh_token": refresh_token
            }), 200
        else:
            return jsonify({"error": "Invalid username or password"}), 401

    except Exception as e:
        return jsonify({"error": str(e)}), 500

#Profile Picture Update Route
@app.route('/profile/update', methods=['PUT'])
@jwt_required()
def update_profile():
    try:
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)

        if not user:
            return jsonify({"error": "User not found"}), 404

        profile_pic = request.files.get('profile_pic')

        if profile_pic:
            profile_pic_path = f"uploads/{profile_pic.filename}"
            profile_pic.save(profile_pic_path)
            user.profile_pic = profile_pic_path

        db.session.commit()
        return jsonify({"message": "Profile picture updated successfully!", "profile_pic": user.profile_pic}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

#Fetch a Particular User’s Complete Details
@app.route('/user/<int:user_id>', methods=['GET'])
@jwt_required()
def get_user_details(user_id):
    user = User.query.get(user_id)

    if not user:
        return jsonify({"error": "User not found"}), 404

    company_details = None
    if user.company:
        company_details = {"company_id": user.company.id, "company_name": user.company.name}

    tasks = Task.query.filter_by(user_id=user.id).all()
    task_list = [{
        "task_id": task.id,
        "description": task.description,
        "is_completed": task.is_completed,
        "created_at": task.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        "completed_at": task.completed_at.strftime("%Y-%m-%d %H:%M:%S") if task.completed_at else None
    } for task in tasks]

    return jsonify({
        "user_id": user.id,
        "username": user.username,
        "mobile_no": user.mobile_no,
        "profile_pic": user.profile_pic,
        "company": company_details,
        "tasks": task_list
    }), 200

@app.route('/users', methods=['GET'])
@jwt_required()
def get_all_users():
    users = db.session.query(
        User.id,
        User.username,
        User.mobile_no,
        User.profile_pic,
        Company.name.label("company_name")  # Fetch company name using JOIN
    ).join(Company, User.company_id == Company.id).all()

    user_list = [{
        "id": user.id,
        "username": user.username,
        "mobile_no": user.mobile_no,
        "profile_pic": user.profile_pic,
        "company_name": user.company_name  # Now includes company name
    } for user in users]

    return jsonify({"users": user_list}), 200

#Fetch Company Progress (Cumulative Completed Tasks)
@app.route('/companies', methods=['GET'])
@jwt_required()
def get_company_progress():
    companies = Company.query.all()
    company_list = []

    for company in companies:
        users = User.query.filter_by(company_id=company.id).all()
        total_completed_tasks = sum(Task.query.filter_by(user_id=user.id, is_completed=True).count() for user in users)

        company_list.append({
            "company_id": company.id,
            "company_name": company.name,
            "total_completed_tasks": total_completed_tasks
        })

    return jsonify({"companies": company_list}), 200

#Create Task
@app.route('/tasks', methods=['POST'])
@jwt_required()
def create_task():
    data = request.get_json()
    description = data.get('description')

    if not description:
        return jsonify({"error": "Task description is required"}), 400

    user_id = get_jwt_identity()
    new_task = Task(user_id=user_id, description=description, created_at=datetime.utcnow())
    db.session.add(new_task)
    db.session.commit()

    return jsonify({"message": "Task created successfully!"}), 201

#Mark Task as Completed
@app.route('/tasks/<int:task_id>/complete', methods=['PUT'])
@jwt_required()
def complete_task(task_id):
    user_id = get_jwt_identity()
    task = Task.query.filter_by(id=task_id, user_id=user_id).first()

    if not task:
        return jsonify({"error": "Task not found or you don't have access"}), 404

    if task.is_completed:
        return jsonify({"message": "Task is already completed"}), 400

    task.is_completed = True
    task.completed_at = datetime.utcnow()
    db.session.commit()

    return jsonify({"message": "Task marked as completed!"}), 200

# ✅ Delete a Task
@app.route('/tasks/<int:task_id>', methods=['DELETE'])
@jwt_required()
def delete_task(task_id):
    user_id = get_jwt_identity()
    task = Task.query.filter_by(id=task_id, user_id=user_id).first()

    if not task:
        return jsonify({"error": "Task not found or you don't have access"}), 404

    db.session.delete(task)
    db.session.commit()

    return jsonify({"message": "Task deleted successfully!"}), 200

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)