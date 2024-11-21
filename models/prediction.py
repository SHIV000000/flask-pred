# models/prediction.py


from datetime import datetime
from application import db
import logging

logger = logging.getLogger(__name__)

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

    @property
    def home_probability(self):
        return self.prediction

    @property
    def away_probability(self):
        return 1 - self.prediction

    @property
    def predicted_winner(self):
        return 'Home' if self.prediction > 0.5 else 'Away'

    @property
    def confidence_level(self):
        diff = abs(self.prediction - 0.5)
        if diff > 0.2:
            return 'High'
        elif diff > 0.1:
            return 'Medium'
        return 'Low'

    def calculate_rewards(self, actual_score):
        """Calculate rewards based on prediction accuracy"""
        try:
            # Calculate score accuracy
            home_diff = abs(self.predicted_home_score - actual_score['home'])
            away_diff = abs(self.predicted_away_score - actual_score['away'])
            self.accuracy_score = 1 - ((home_diff + away_diff) / 200)  # Scale to 0-1

            # Store actual scores
            self.actual_home_score = actual_score['home']
            self.actual_away_score = actual_score['away']

            # Determine if prediction was correct
            actual_winner = 'Home' if actual_score['home'] > actual_score['away'] else 'Away'
            self.status = 'correct' if self.predicted_winner == actual_winner else 'incorrect'

            # Calculate rewards
            if self.status == 'correct':
                # Base reward is 2x wagered amount
                self.coins_won = self.coins_wagered * 2

                # Confidence bonus
                if self.confidence_level == 'High':
                    self.coins_won = int(self.coins_won * 1.5)
                elif self.confidence_level == 'Medium':
                    self.coins_won = int(self.coins_won * 1.2)

                # Accuracy bonus
                if self.accuracy_score >= 0.9:  # Highly accurate prediction
                    self.coins_won += 100
                    self.boost_points_earned = 3
                elif self.accuracy_score >= 0.8:  # Very good prediction
                    self.coins_won += 50
                    self.boost_points_earned = 2
                elif self.accuracy_score >= 0.7:  # Good prediction
                    self.coins_won += 25
                    self.boost_points_earned = 1

            return {
                'status': self.status,
                'coins_won': self.coins_won,
                'boost_points': self.boost_points_earned,
                'accuracy': self.accuracy_score,
                'actual_score': actual_score
            }

        except Exception as e:
            logger.error(f"Error calculating rewards: {str(e)}")
            return None

    def to_dict(self):
        """Convert prediction to dictionary"""
        return {
            'id': self.id,
            'game_id': self.game_id,
            'home_team': self.home_team,
            'away_team': self.away_team,
            'predicted_winner': self.predicted_winner,
            'confidence': self.confidence_level,
            'home_score_pred': self.predicted_home_score,
            'away_score_pred': self.predicted_away_score,
            'actual_home_score': self.actual_home_score,
            'actual_away_score': self.actual_away_score,
            'status': self.status,
            'coins_wagered': self.coins_wagered,
            'coins_won': self.coins_won,
            'boost_points_earned': self.boost_points_earned,
            'accuracy_score': self.accuracy_score,
            'created_at': self.timestamp.isoformat(),
            'game_date': self.game_date.isoformat() if self.game_date else None,
            'probabilities': {
                'home': self.home_probability,
                'away': self.away_probability
            }
        }

    def get_reward_summary(self):
        """Get summary of rewards earned"""
        if self.status != 'correct':
            return None

        return {
            'coins': self.coins_won,
            'boost_points': self.boost_points_earned,
            'accuracy': self.accuracy_score,
            'confidence_bonus': self.confidence_level == 'High',
            'accuracy_bonus': self.accuracy_score >= 0.8,
            'total_bonus': self.coins_won - (self.coins_wagered * 2)
        }

    def __repr__(self):
        return f'<Prediction {self.id}: {self.home_team} vs {self.away_team}>'

