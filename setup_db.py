# setup_db.py
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os

# Delete existing database file if it exists
if os.path.exists('instance/nba_predictions.db'):
    os.remove('instance/nba_predictions.db')

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///nba_predictions.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Define models
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    coins = db.Column(db.Integer, default=1000)
    boost_points = db.Column(db.Integer, default=0)

class Prediction(db.Model):
    __tablename__ = 'predictions'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    game_id = db.Column(db.String(80), nullable=False)
    home_team = db.Column(db.String(80), nullable=False)
    away_team = db.Column(db.String(80), nullable=False)
    predicted_winner = db.Column(db.String(80), nullable=False)
    confidence = db.Column(db.String(20), nullable=False)
    home_score_pred = db.Column(db.Integer)
    away_score_pred = db.Column(db.Integer)
    actual_winner = db.Column(db.String(80))
    home_score_actual = db.Column(db.Integer)
    away_score_actual = db.Column(db.Integer)
    coins_wagered = db.Column(db.Integer, default=0)
    coins_won = db.Column(db.Integer, default=0)
    boost_points_earned = db.Column(db.Integer, default=0)
    accuracy_score = db.Column(db.Float, default=0.0)
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    game_date = db.Column(db.DateTime, nullable=False)

def setup_database():
    with app.app_context():
        # Create all tables
        db.create_all()
        
        print("Database tables created successfully!")
        
        # Verify tables exist
        tables = db.engine.table_names()
        print(f"Created tables: {tables}")
        
        # Create a test user
        try:
            test_user = User(
                username='test',
                email='test@example.com',
                password_hash='test123',
                coins=1000,
                boost_points=0
            )
            db.session.add(test_user)
            db.session.commit()
            print("Test user created successfully!")
        except Exception as e:
            print(f"Error creating test user: {str(e)}")
            db.session.rollback()

if __name__ == '__main__':
    setup_database()
