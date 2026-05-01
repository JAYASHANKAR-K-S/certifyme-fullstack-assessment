import os
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_cors import CORS
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
import uuid
from datetime import datetime, timedelta

app = Flask(__name__)

basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'database.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JWT_SECRET_KEY'] = 'secretkey123'

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
CORS(app)
jwt = JWTManager(app)

class Admin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100))
    email = db.Column(db.String(100), unique=True)
    password = db.Column(db.String(200))

class PasswordResetToken(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, db.ForeignKey('admin.id'))
    token = db.Column(db.String(100), unique=True)
    expires_at = db.Column(db.DateTime)

class Opportunity(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200))
    duration = db.Column(db.String(50))
    start_date = db.Column(db.String(50))
    description = db.Column(db.Text)
    skills = db.Column(db.String(200))
    category = db.Column(db.String(50))
    future_opportunities = db.Column(db.Text)
    max_applicants = db.Column(db.Integer)

    admin_id = db.Column(db.Integer, db.ForeignKey('admin.id'))

@app.route('/signup', methods=['POST'])
def signup():
    data = request.json

    import re
    if not re.match(r"[^@]+@[^@]+\.[^@]+", data['email']):
        return {"error": "Invalid email format"}, 400

    if data['password'] != data['confirm_password']:
        return {"error": "Passwords do not match"}, 400

    if len(data['password']) < 8:
        return {"error": "Password must be at least 8 characters"}, 400

    if Admin.query.filter_by(email=data['email']).first():
        return {"error": "Account already exists"}, 400

    hashed_password = bcrypt.generate_password_hash(data['password']).decode('utf-8')

    new_admin = Admin(
        full_name=data['full_name'],
        email=data['email'],
        password=hashed_password
    )

    db.session.add(new_admin)
    db.session.commit()

    return {"message": "Signup successful"}

@app.route('/login', methods=['POST'])
def login():
    data = request.json

    admin = Admin.query.filter_by(email=data['email']).first()

    if not admin or not bcrypt.check_password_hash(admin.password, data['password']):
        return {"error": "Invalid email or password"}, 401

    remember_me = data.get('remember_me', False)
    if remember_me:
        token = create_access_token(identity=str(admin.id), expires_delta=timedelta(days=30))
    else:
        # Shorter default token for non-remembered sessions
        token = create_access_token(identity=str(admin.id), expires_delta=timedelta(hours=1))

    return {
    "token": token,
    "email": admin.email,
    "full_name": admin.full_name,
    "admin_id": admin.id
}

@app.route('/opportunities', methods=['POST'])
@jwt_required()
def add_opportunity():
    admin_id = int(get_jwt_identity())
    data = request.json

    opp = Opportunity(
        name=data.get('name'),
        duration=data.get('duration'),
        start_date=data.get('start_date'),
        description=data.get('description'),
        skills=','.join(data['skills']) if isinstance(data.get('skills'), list) else data.get('skills', ''),
        category=data.get('category'),
        future_opportunities=data.get('future_opportunities'),
        max_applicants=data.get('max_applicants'),
        admin_id=admin_id
    )

    db.session.add(opp)
    db.session.commit()

    return {"message": "Opportunity added"}

@app.route('/opportunities', methods=['GET'])
@jwt_required()
def get_opportunities():
    admin_id = int(get_jwt_identity())

    opps = Opportunity.query.filter_by(admin_id=admin_id).all()

    result = []
    for o in opps:
        result.append({
            "id": o.id,
            "name": o.name,
            "duration": o.duration,
            "start_date": o.start_date,
            "description": o.description,
            "skills": o.skills,
            "category": o.category,
            "future_opportunities": o.future_opportunities,
            "max_applicants": o.max_applicants
        })

    return jsonify(result)

@app.route('/opportunities/<int:id>', methods=['DELETE'])
@jwt_required()
def delete_opportunity(id):
    admin_id = int(get_jwt_identity())

    opp = Opportunity.query.get(id)

    if not opp or opp.admin_id != admin_id:
        return {"error": "Unauthorized"}, 403

    db.session.delete(opp)
    db.session.commit()

    return {"message": "Deleted successfully"}

@app.route('/opportunities/<int:id>', methods=['PUT'])
@jwt_required()
def update_opportunity(id):
    admin_id = int(get_jwt_identity())
    data = request.json

    opp = Opportunity.query.get(id)

    if not opp or opp.admin_id != admin_id:
        return {"error": "Unauthorized"}, 403

    # update fields
    opp.name = data['name']
    opp.duration = data['duration']
    opp.start_date = data['start_date']
    opp.description = data['description']
    
    # handle skills (list → string)
    if isinstance(data['skills'], list):
        opp.skills = ','.join(data['skills'])
    else:
        opp.skills = data['skills']

    opp.category = data['category']
    opp.future_opportunities = data['future_opportunities']
    opp.max_applicants = data.get('max_applicants')

    db.session.commit()

    return {"message": "Opportunity updated successfully"}

@app.route('/forgot-password', methods=['POST'])
def forgot_password():
    data = request.json
    email = data.get('email')

    admin = Admin.query.filter_by(email=email).first()
    if admin:
        token = str(uuid.uuid4())
        expires = datetime.utcnow() + timedelta(hours=1)
        reset_token = PasswordResetToken(admin_id=admin.id, token=token, expires_at=expires)
        db.session.add(reset_token)
        db.session.commit()
        print(f"Internal Reset Link: http://127.0.0.1:5000/reset-password/{token}")

    # Always return same message (security)
    return {"message": "If the email exists, a reset link has been sent."}

@app.route('/reset-password/<token>', methods=['GET'])
def verify_reset_link(token):
    reset_token = PasswordResetToken.query.filter_by(token=token).first()
    if not reset_token or reset_token.expires_at < datetime.utcnow():
        return {"error": "Link expired or invalid"}, 400
    
    return {"message": "Link is valid. You can reset your password."}

if __name__ == "__main__":
    with app.app_context():
        db.create_all()

    app.run(debug=True)