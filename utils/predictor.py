# utils/predictor.py

# Standard library imports
import os
from datetime import datetime
import logging

# Third-party imports
import numpy as np
import pandas as pd
import tensorflow as tf
import joblib
from sklearn.preprocessing import StandardScaler

# Configure logging
logger = logging.getLogger(__name__)

# Import caching logic
from utils.cache_manager import cache_manager



class Predictor:
    def __init__(self, api_client):
        """Initialize predictor with models, API client, and cache."""
        self.api_client = api_client
        self.models = {}
        self._load_models()


    def _load_models(self):
        """Load all required models from disk."""
        try:
            models_dir = os.path.join('models', 'saved_models')
            if not os.path.exists(models_dir):
                raise FileNotFoundError(f"Models directory not found: {models_dir}")
            
            model_configs = {
                'gru': {'file': 'gru_20241111_040330.h5', 'type': 'keras'},
                'lstm': {'file': 'lstm_20241111_040330.h5', 'type': 'keras'},
                'rf': {'file': 'random_forest_20241111_040330.joblib', 'type': 'sklearn'},
                'svm': {'file': 'svm_20241111_040330.joblib', 'type': 'sklearn'},
                'xgb': {'file': 'xgboost_20241111_040330.joblib', 'type': 'sklearn'},
                'scaler': {'file': 'scaler_20241111_040330.joblib', 'type': 'sklearn'}
            }
            
            for model_name, config in model_configs.items():
                self._load_single_model(model_name, config, models_dir)
                
            logger.info("All models loaded successfully")
            
        except Exception as e:
            logger.error(f"Error during model initialization: {str(e)}")
            self.models = None
            raise

    def _load_single_model(self, model_name, config, models_dir):
        """Load a single model with error handling."""
        file_path = os.path.join(models_dir, config['file'])
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Model file not found: {file_path}")
        
        try:
            self.models[model_name] = (
                tf.keras.models.load_model(file_path) 
                if config['type'] == 'keras'
                else joblib.load(file_path)
            )
            logger.debug(f"Successfully loaded {model_name} model")
        except Exception as model_error:
            logger.error(f"Failed to load {model_name} model: {str(model_error)}")
            raise

    def predict_game(self, home_team_id, visitors_team_id, game_id=None):
        """Make prediction for a scheduled game with consistent 'visitors' terminology"""
        try:
            # Check cache first
            if game_id:
                cached_prediction = self._get_cached_prediction(game_id)
                if cached_prediction:
                    logger.info(f"Using cached prediction for game {game_id}")
                    return cached_prediction

            # Get team statistics with caching
            home_stats = self._get_cached_team_stats(home_team_id)
            if not home_stats:
                home_stats = self.api_client.get_team_stats(home_team_id)
                if home_stats:
                    self._cache_team_stats(home_team_id, home_stats)

            visitors_stats = self._get_cached_team_stats(visitors_team_id)
            if not visitors_stats:
                visitors_stats = self.api_client.get_team_stats(visitors_team_id)
                if visitors_stats:
                    self._cache_team_stats(visitors_team_id, visitors_stats)

            # Get team names (these are usually quick calls, so no caching needed)
            home_team_name = self.api_client.get_team_name(home_team_id)
            visitors_team_name = self.api_client.get_team_name(visitors_team_id)
            
            if not home_stats or not visitors_stats:
                return None
                
            # Your existing prediction logic
            features = self._prepare_features(home_stats, visitors_stats)
            scaled_features = self.models['scaler'].transform(features)
            predictions = self._get_model_predictions(scaled_features)
            home_prob = self._calculate_ensemble_prediction(predictions)
            
            # Generate prediction structure
            prediction = {
                'home_probability': home_prob,
                'visitors_probability': 1 - home_prob,
                'predicted_winner': {
                    'team': 'Home' if home_prob >= 0.5 else 'Visitors',
                    'name': home_team_name if home_prob >= 0.5 else visitors_team_name,
                    'probability': max(home_prob, 1 - home_prob) * 100
                },
                'predicted_scores': self._predict_score_ranges(home_stats, visitors_stats, home_prob),
                'confidence_level': self._calculate_confidence(max(home_prob, 1 - home_prob)),
                'teams': {
                    'home': {'name': home_team_name, 'id': home_team_id},
                    'visitors': {'name': visitors_team_name, 'id': visitors_team_id}
                }
            }
            
            # Cache the prediction
            if game_id:
                self._cache_prediction(game_id, prediction)
                
            return prediction

        except Exception as e:
            logger.error(f"Error in predict_game: {str(e)}")
            return None

    def predict_live_game(self, game_data):
        """Make prediction for a live game with current scores"""
        try:
            game_id = str(game_data.get('id'))
            
            # Use very short cache for live games
            cached_prediction = self._get_cached_prediction(f'live_{game_id}')
            if cached_prediction:
                return cached_prediction

            # Your existing live prediction logic
            base_prediction = self.predict_game(
                game_data['teams']['home']['id'],
                game_data['teams']['away']['id']
            )
            
            if not base_prediction:
                return None
                
            # Rest of your existing logic
            home_score = game_data['teams']['home']['score']
            away_score = game_data['teams']['away']['score']
            score_diff = home_score - away_score
            
            minutes, seconds = map(int, game_data['clock'].split(':'))
            period = game_data['period']
            total_seconds = 48 * 60
            elapsed_seconds = ((period - 1) * 12 * 60) + ((12 * 60) - (minutes * 60 + seconds))
            time_remaining_pct = max(0, min(1, (total_seconds - elapsed_seconds) / total_seconds))
            
            score_impact = score_diff * (1 - time_remaining_pct) * 0.05
            adjusted_home_prob = max(0.01, min(0.99, base_prediction['home_probability'] + score_impact))
            
            live_prediction = {
                'home_probability': adjusted_home_prob,
                'away_probability': 1 - adjusted_home_prob,
                'predicted_winner': 'Home' if adjusted_home_prob > 0.5 else 'Away',
                'confidence_level': self._calculate_confidence(adjusted_home_prob),
                'time_remaining': f"{minutes}:{seconds:02d}",
                'period': period
            }
            
            # Cache live prediction for a very short time
            self._cache_prediction(f'live_{game_id}', live_prediction, duration=1)
            
            return live_prediction
            
        except Exception as e:
            logger.error(f"Error predicting live game: {str(e)}")
            return None

    def predict_live_game_realtime(self, game_data):
        """Generate real-time prediction for live game"""
        try:
            logger.debug(f"Processing live game data: {game_data}")
            
            # Get base prediction
            base_prediction = self.predict_game(
                game_data['teams']['home']['id'],
                game_data['teams']['visitors']['id']
            )
            
            if not base_prediction:
                return None
                
            # Get current game state - handle nested dictionaries safely
            home_score = int(game_data.get('teams', {}).get('home', {}).get('score', 0))
            visitors_score = int(game_data.get('teams', {}).get('visitors', {}).get('score', 0))
            period = int(game_data.get('period', 1))
            
            # Parse clock time safely
            clock = game_data.get('clock', '0:00')
            try:
                minutes, seconds = map(int, clock.split(':'))
            except (ValueError, AttributeError):
                minutes, seconds = 0, 0
            
            # Calculate time remaining and score impact
            total_seconds = 48 * 60
            elapsed_seconds = ((period - 1) * 12 * 60) + ((12 * 60) - (minutes * 60 + seconds))
            time_remaining_pct = max(0, min(1, (total_seconds - elapsed_seconds) / total_seconds))
            
            score_diff = home_score - visitors_score
            score_impact = score_diff * (1 - time_remaining_pct) * 0.1
            
            # Adjust probabilities
            adjusted_home_prob = max(0.01, min(0.99, base_prediction['home_probability'] + score_impact))
            
            return {
                'game_id': str(game_data.get('id', '')),
                'win_probability': {
                    'home': adjusted_home_prob,
                    'visitors': 1 - adjusted_home_prob
                },
                'predicted_winner': 'Home' if adjusted_home_prob > 0.5 else 'Visitors',
                'confidence': self._calculate_confidence(max(adjusted_home_prob, 1 - adjusted_home_prob)),
                'current_score': {
                    'home': home_score,
                    'visitors': visitors_score
                }
            }
            
        except Exception as e:
            logger.error(f"Error in real-time prediction: {str(e)}")
            logger.debug(f"Game data structure: {game_data}")
            return None

    def _get_cached_prediction(self, game_id):
        """Get cached prediction if available"""
        try:
            if not game_id:
                return None
            cache_key = f'prediction_{game_id}'
            return cache_manager.get(cache_key)
        except Exception as e:
            logger.error(f"Error getting cached prediction: {str(e)}")
            return None

    def _cache_prediction(self, game_id, prediction, duration=30):
        """Cache prediction with specified duration"""
        try:
            if not game_id or not prediction:
                return
            cache_key = f'prediction_{game_id}'
            cache_manager.set(cache_key, prediction, expires_in_minutes=duration)
        except Exception as e:
            logger.error(f"Error caching prediction: {str(e)}")

    def _get_cached_team_stats(self, team_id):
        """Get cached team statistics"""
        try:
            cache_key = f'team_stats_{team_id}'
            return cache_manager.get(cache_key)
        except Exception as e:
            logger.error(f"Error getting cached team stats: {str(e)}")
            return None

    def _cache_team_stats(self, team_id, stats):
        """Cache team statistics"""
        try:
            if not team_id or not stats:
                return
            cache_key = f'team_stats_{team_id}'
            cache_manager.set(cache_key, stats, expires_in_minutes=60)
        except Exception as e:
            logger.error(f"Error caching team stats: {str(e)}")

    def _generate_prediction(self, home_team_id, away_team_id):
        """Internal method to generate new prediction."""

        try:
            # Get team statistics and names
            home_stats = self.api_client.get_team_stats(home_team_id)
            away_stats = self.api_client.get_team_stats(away_team_id)
            home_team_name = self.api_client.get_team_name(home_team_id)
            away_team_name = self.api_client.get_team_name(away_team_id)
            
            if not home_stats or not away_stats:
                return None
                
            # Calculate prediction
            features = self._prepare_features(home_stats, away_stats)
            scaled_features = self.models['scaler'].transform(features)
            predictions = self._get_model_predictions(scaled_features)
            home_prob = self._calculate_ensemble_prediction(predictions)
            
            # Determine winner
            if home_prob >= 0.5:
                winner_team = 'Home'
                winner_prob = home_prob
            else:
                winner_team = 'Away'
                winner_prob = 1 - home_prob
            
            # Calculate predicted scores
            predicted_scores = self._predict_score_ranges(home_stats, away_stats, winner_prob)
            
            # Return prediction data
            return {
                'home_probability': home_prob,
                'away_probability': 1 - home_prob,
                'predicted_winner': {
                    'team': winner_team,
                    'name': home_team_name if winner_team == 'Home' else away_team_name,
                    'probability': winner_prob * 100
                },
                'predicted_scores': predicted_scores,
                'confidence_level': self._calculate_confidence(winner_prob),
                'teams': {
                    'home': {'name': home_team_name, 'id': home_team_id},
                    'away': {'name': away_team_name, 'id': away_team_id}
                }
            }
            
        except Exception as e:
            logger.error(f"Error in _generate_prediction: {str(e)}")
            return None

    def _prepare_features(self, home_stats, away_stats):
        """Prepare comprehensive feature vector for prediction"""
        try:
            # Initialize feature array
            features = np.zeros((1, 103))
            
            # Define comprehensive feature mapping
            feature_mapping = {
                # Offensive Stats (0-19)
                'points_per_game': 0,
                'field_goal_pct': 1,
                'three_point_pct': 2,
                'free_throw_pct': 3,
                'offensive_rebounds_per_game': 4,
                'assists_per_game': 5,
                'field_goals_made_per_game': 6,
                'field_goals_attempted_per_game': 7,
                'three_pointers_made_per_game': 8,
                'three_pointers_attempted_per_game': 9,
                # Defensive Stats (20-39)
                'defensive_rebounds_per_game': 20,
                'steals_per_game': 21,
                'blocks_per_game': 22,
                'fouls_per_game': 23,
                'points_allowed_per_game': 24,
                # Advanced Stats (40-49)
                'effective_fg_pct': 40,
                'true_shooting_pct': 41,
                'offensive_rating': 42,
                'net_rating': 43,
                'pace': 44,
                # Team Success Metrics (50-51)
                'win_percentage': 50,
                'games_played': 51
            }
            
            # Fill home team features (0-51)
            for stat_name, position in feature_mapping.items():
                home_value = home_stats.get(stat_name, 0.0)
                features[0, position] = self._normalize_stat(stat_name, home_value)
            
            # Fill away team features (52-102)
            for stat_name, position in feature_mapping.items():
                away_value = away_stats.get(stat_name, 0.0)
                features[0, position + 51] = self._normalize_stat(stat_name, away_value)
            
            if not self._validate_features(features):
                raise ValueError("Feature validation failed")
                
            return features
            
        except Exception as e:
            logger.error(f"Error preparing features: {str(e)}")
            raise

    def _normalize_stat(self, stat_name, value):
        """Normalize statistics to a common scale"""
        try:
            normalization_ranges = {
                'percentage': (0, 100),
                'per_game': (0, 150),
                'rating': (-30, 30),
                'rank': (1, 30),
                'impact': (-10, 10)
            }
            
            stat_types = {
                'field_goal_pct': 'percentage',
                'three_point_pct': 'percentage',
                'points_per_game': 'per_game',
                'offensive_rating': 'rating',
                # ... more stat type mappings ...
            }
            
            stat_type = stat_types.get(stat_name, 'per_game')
            min_val, max_val = normalization_ranges[stat_type]
            
            normalized = (float(value) - min_val) / (max_val - min_val)
            return max(0, min(1, normalized))
            
        except Exception as e:
            logger.error(f"Error normalizing stat {stat_name}: {str(e)}")
            return 0.0

    def _validate_features(self, features):
        """Validate feature array dimensions and values"""
        try:
            expected_shape = (1, 103)
            if features.shape != expected_shape:
                logger.error(f"Invalid feature shape: {features.shape}, expected {expected_shape}")
                return False
                
            if np.isnan(features).any():
                logger.error("Features contain NaN values")
                return False
                
            if (features < 0).any() or (features > 1).any():
                logger.error("Features contain values outside normalized range")
                return False
                
            return True
            
        except Exception as e:
            logger.error(f"Error validating features: {str(e)}")
            return False

    def _get_model_predictions(self, features):
        """Get predictions from all models"""
        predictions = {}
        
        try:
            # Neural network predictions
            nn_features = features.reshape(1, 1, -1)
            predictions['gru'] = float(self.models['gru'].predict(nn_features)[0][0])
            predictions['lstm'] = float(self.models['lstm'].predict(nn_features)[0][0])
            
            # Traditional ML predictions
            predictions['rf'] = float(self.models['rf'].predict_proba(features)[0][1])
            predictions['xgb'] = float(self.models['xgb'].predict_proba(features)[0][1])
            
            return predictions
            
        except Exception as e:
            logger.error(f"Error getting model predictions: {str(e)}")
            raise

    def _calculate_ensemble_prediction(self, predictions):
        """Calculate weighted ensemble prediction with proper scaling"""
        try:
            # Normalize predictions to proper probability range
            normalized_predictions = {}
            for model, pred in predictions.items():
                # Ensure prediction is between 0.01 and 0.99
                normalized_predictions[model] = max(0.01, min(0.99, pred))
            
            # Updated weights favoring more accurate models
            weights = {
                'gru': 0.35,    # Increased weight for GRU
                'lstm': 0.35,   # Increased weight for LSTM
                'rf': 0.20,     # Reduced weight for RF
                'xgb': 0.10     # Reduced weight for XGB
            }
            
            # Calculate weighted average
            weighted_pred = sum(
                normalized_predictions[model] * weights[model]
                for model in weights.keys()
            )
            
            # Apply sigmoid-like scaling to emphasize differences
            # This will push predictions away from 0.5 towards more decisive values
            scaled_pred = 1 / (1 + np.exp(-12 * (weighted_pred - 0.5)))
            
            # Ensure winner has >50% probability
            if scaled_pred < 0.5:
                return 1 - scaled_pred  # Flip probability to favor the other team
            
            return scaled_pred
            
        except Exception as e:
            logger.error(f"Error in ensemble prediction: {str(e)}")
            return 0.5

    def _predict_score_ranges(self, home_stats, visitors_stats, win_prob):
        """Enhanced score range prediction using 'visitors' terminology"""
        try:
            # Base scores from season averages
            home_base = home_stats['points_per_game']
            visitors_base = visitors_stats['points_per_game']  # Changed from away_base
            
            # Defensive adjustment
            home_defense = home_stats['points_allowed_per_game']
            visitors_defense = visitors_stats['points_allowed_per_game']  # Changed from away_defense
            
            # Pace adjustment
            pace_factor = (home_stats['pace'] + visitors_stats['pace']) / 200
            
            # Win probability adjustment
            prob_adjustment = (win_prob - 0.5) * 15
            
            # Calculate adjusted scores
            home_score = (home_base * 0.6 + (100 - visitors_defense) * 0.4) * pace_factor
            visitors_score = (visitors_base * 0.6 + (100 - home_defense) * 0.4) * pace_factor  # Changed from away_score
            
            # Apply win probability adjustment
            home_score += prob_adjustment
            visitors_score -= prob_adjustment
            
            # Calculate ranges with tighter bounds
            home_range = {
                'low': max(85, round(home_score - 6)),
                'mid': round(home_score),
                'high': round(home_score + 6)
            }
            
            visitors_range = {  # Changed from away_range
                'low': max(85, round(visitors_score - 6)),
                'mid': round(visitors_score),
                'high': round(visitors_score + 6)
            }
            
            return {'home': home_range, 'visitors': visitors_range}  # Changed from 'away'
            
        except Exception as e:
            logger.error(f"Error predicting score ranges: {str(e)}")
            return {
                'home': {'low': 95, 'mid': 105, 'high': 115},
                'visitors': {'low': 95, 'mid': 105, 'high': 115}  # Changed from 'away'
            }

    def _analyze_h2h_games(self, home_team_id, away_team_id):
        """Analyze head-to-head game history"""
        try:
            h2h_games = self.api_client.get_h2h_games(home_team_id, away_team_id)
            if not h2h_games:
                return 0.5
            
            weighted_wins = 0
            total_weight = 0
            weights = np.linspace(1, 0.5, len(h2h_games))
            
            for game, weight in zip(h2h_games, weights):
                home_score = game['scores']['home']['points']
                away_score = game['scores']['away']['points']
                
                if home_score > away_score:
                    weighted_wins += weight
                total_weight += weight
            
            return weighted_wins / total_weight if total_weight > 0 else 0.5
            
        except Exception as e:
            logger.error(f"Error analyzing H2H games: {str(e)}")
            return 0.5

    def _analyze_team_forms(self, home_team_id, away_team_id):
        """Analyze recent form of both teams"""
        try:
            home_games = self.api_client.get_last_games(home_team_id, 5)
            away_games = self.api_client.get_last_games(away_team_id, 5)
            
            home_form = self._calculate_form(home_games)
            away_form = self._calculate_form(away_games)
            
            return {
                'home': {
                    'value': home_form,
                    'trend': self._get_form_trend(home_form)
                },
                'away': {
                    'value': away_form,
                    'trend': self._get_form_trend(away_form)
                }
            }
            
        except Exception as e:
            logger.error(f"Error analyzing team forms: {str(e)}")
            return {'home': {'value': 0.5, 'trend': 'neutral'},
                    'away': {'value': 0.5, 'trend': 'neutral'}}

    def _calculate_form(self, games):
        """Calculate team's recent form"""
        if not games:
            return 0.5
        
        weighted_score = 0
        total_weight = 0
        weights = np.linspace(1, 0.6, len(games))
        
        for game, weight in zip(games, weights):
            team_score = game['scores']['home']['points']
            opp_score = game['scores']['away']['points']
            
            if game['teams']['away']['id'] == game['teams']['home']['id']:
                team_score, opp_score = opp_score, team_score
            
            if team_score > opp_score:
                weighted_score += weight
            total_weight += weight
        
        return weighted_score / total_weight if total_weight > 0 else 0.5

    def _get_form_trend(self, form):
        """Determine form trend"""
        if form > 0.7:
            return 'strong_upward'
        elif form > 0.6:
            return 'upward'
        elif form < 0.3:
            return 'strong_downward'
        elif form < 0.4:
            return 'downward'
        return 'neutral'

    def _analyze_injuries(self, home_team_id, away_team_id):
        """Simplified injury impact analysis based on available data"""
        try:
            # Return default values since we can't get injury data
            return {
                'home': {
                    'impact': 0,
                    'severity': 'unknown'
                },
                'away': {
                    'impact': 0,
                    'severity': 'unknown'
                }
            }
        except Exception as e:
            logger.error(f"Error in injury analysis: {str(e)}")
            return {
                'home': {'impact': 0, 'severity': 'unknown'},
                'away': {'impact': 0, 'severity': 'unknown'}
            }

    def _adjust_live_probability(self, base_prob, home_score, away_score, period, clock):
        """Adjust probability based on live game state"""
        try:
            # Convert clock to seconds remaining
            minutes, seconds = map(int, clock.split(':'))
            time_remaining = (minutes * 60 + seconds) + (48 - period * 12) * 60
            
            # Calculate score impact
            score_diff = home_score - away_score
            time_factor = time_remaining / (48 * 60)
            score_impact = (score_diff / 10) * (1 - time_factor)
            
            # Adjust probability
            adjusted_prob = base_prob + score_impact * 0.1
            return max(0.01, min(0.99, adjusted_prob))
            
        except Exception as e:
            logger.error(f"Error adjusting live probability: {str(e)}")
            return base_prob

    def _calculate_momentum(self, game_data):
        """Calculate current game momentum"""
        try:
            # Get last few minutes of scoring
            recent_plays = self.api_client.get_recent_plays(game_data['id'])
            
            home_momentum = 0
            away_momentum = 0
            
            for play in recent_plays:
                if play['team'] == 'home':
                    home_momentum += play['points']
                else:
                    away_momentum += play['points']
                
            return {
                'home': home_momentum,
                'away': away_momentum,
                'advantage': 'home' if home_momentum > away_momentum else 'away' if away_momentum > home_momentum else 'neutral'
            }
            
        except Exception as e:
            logger.error(f"Error calculating momentum: {str(e)}")
            return {'home': 0, 'away': 0, 'advantage': 'neutral'}

    def _calculate_confidence(self, probability):
        """Calculate confidence level of prediction"""
        try:
            prob_diff = abs(probability - 0.5)
            
            if prob_diff > 0.2:
                return 'high'
            elif prob_diff > 0.1:
                return 'medium'
            return 'low'
            
        except Exception as e:
            logger.error(f"Error calculating confidence: {str(e)}")
            return 'low'

    def update_prediction_tracking(self, game_id, actual_result):
        """Update prediction tracking and reward system"""
        try:
            # Get original prediction
            prediction = self.get_prediction_history(game_id)
            if not prediction:
                return None
            
            # Calculate accuracy
            predicted_winner = 'home' if prediction['home_probability'] > 0.5 else 'away'
            actual_winner = 'home' if actual_result['home_score'] > actual_result['away_score'] else 'away'
            is_correct = predicted_winner == actual_winner
            
            # Calculate score accuracy
            home_score_accuracy = 1 - abs(prediction['predicted_scores']['home']['mid'] - actual_result['home_score']) / 100
            away_score_accuracy = 1 - abs(prediction['predicted_scores']['away']['mid'] - actual_result['away_score']) / 100
            score_accuracy = (home_score_accuracy + away_score_accuracy) / 2
            
            # Update reward system
            reward_data = self._calculate_rewards(is_correct, score_accuracy)
            
            return {
                'prediction_accuracy': {
                    'winner_correct': is_correct,
                    'score_accuracy': score_accuracy,
                    'confidence_level': prediction['confidence_level']
                },
                'rewards': reward_data
            }
            
        except Exception as e:
            logger.error(f"Error updating prediction tracking: {str(e)}")
            return None

    def _calculate_rewards(self, is_correct, score_accuracy):
        """Calculate rewards based on prediction accuracy"""
        try:
            base_coins = 10 if is_correct else 0
            accuracy_bonus = int(score_accuracy * 10)
            total_coins = base_coins + accuracy_bonus
            
            boost_points = 0
            if is_correct and score_accuracy > 0.9:
                boost_points = 2
            elif is_correct and score_accuracy > 0.8:
                boost_points = 1
            
            return {
                'coins_earned': total_coins,
                'boost_points': boost_points,
                'accuracy_bonus': accuracy_bonus
            }
            
        except Exception as e:
            logger.error(f"Error calculating rewards: {str(e)}")
            return {'coins_earned': 0, 'boost_points': 0, 'accuracy_bonus': 0}

    def get_prediction_history(self, game_id):
        """Retrieve prediction history for a game"""
        try:
            # Implementation depends on your storage system
            return None
            
        except Exception as e:
            logger.error(f"Error getting prediction history: {str(e)}")
            return None

    def generate_prediction_insights(self, prediction_data):
        """Generate detailed insights from prediction data"""
        try:
            insights = []
            
            # Winner prediction insight
            win_prob = prediction_data['home_probability']
            if win_prob > 0.7:
                insights.append("Strong favorite to win")
            elif win_prob < 0.3:
                insights.append("Clear underdog")
            else:
                insights.append("Closely matched teams")
            
            # Scoring insight
            home_score = prediction_data['predicted_scores']['home']
            away_score = prediction_data['predicted_scores']['away']
            if home_score['high'] > 120 and away_score['high'] > 120:
                insights.append("High-scoring game likely")
            elif home_score['low'] < 100 and away_score['low'] < 100:
                insights.append("Defensive battle expected")
            
            # Form-based insight
            if prediction_data['analysis']['form']['home']['trend'] == 'strong_upward':
                insights.append("Home team in excellent form")
            if prediction_data['analysis']['form']['away']['trend'] == 'strong_upward':
                insights.append("Away team in excellent form")
            
            return insights
            
        except Exception as e:
            logger.error(f"Error generating insights: {str(e)}")
            return []

    def validate_prediction_data(self, prediction):
        """Validate prediction data structure"""
        try:
            required_fields = [
                'home_probability',
                'away_probability',
                'predicted_winner',
                'confidence_level',
                'predicted_scores',
                'analysis'
            ]
            
            return all(field in prediction for field in required_fields)
            
        except Exception as e:
            logger.error(f"Error validating prediction data: {str(e)}")
            return False

    def get_prediction_metrics(self):
        """Get overall prediction performance metrics"""
        try:
            # Implementation depends on your tracking system
            return {
                'total_predictions': 0,
                'accuracy_rate': 0.0,
                'average_score_accuracy': 0.0,
                'total_rewards': {
                    'coins': 0,
                    'boost_points': 0
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting prediction metrics: {str(e)}")
            return None


