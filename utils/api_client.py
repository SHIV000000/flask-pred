# utils/api_client.py

import requests
import logging
import json
from datetime import datetime, timedelta
import time
from utils.cache_manager import cache_manager
from pytz import timezone  # Add this import for timezone handling

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Add a file handler for debugging
debug_handler = logging.FileHandler('debug.log')
debug_handler.setLevel(logging.DEBUG)
debug_handler.setFormatter(logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
))
logger.addHandler(debug_handler)

class APIClient:
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "https://api-nba-v1.p.rapidapi.com"
        self.headers = {
            "X-RapidAPI-Key": api_key,
            "X-RapidAPI-Host": "api-nba-v1.p.rapidapi.com"
        }
        # Reward system initialization
        self.total_coins = 2460  # Initial coin balance
        self.boost_points = 0
        self.target_boost_points = 2337  # 95% of games
        self.games_played = 0
        self.current_season = '2024'  # Add current season

    def _safe_convert_id(self, value):
        """Safely convert any value to a string ID."""
        try:
            if value is None or value == '':
                return ''
            return str(value).strip()
        except Exception as e:
            logger.warning(f"Error converting ID value '{value}': {str(e)}")
            return ''

    def _make_request(self, endpoint, params=None):
        """Make API request with retry logic and error handling."""
        max_retries = 3
        retry_delay = 5
        
        for attempt in range(max_retries):
            try:
                url = f"{self.base_url}/{endpoint}"
                logger.debug(f"Making request to {url} with params {params}")
                
                response = requests.get(
                    url, 
                    headers=self.headers, 
                    params=params,
                    timeout=30
                )
                response.raise_for_status()
                logger.debug(f"Response status: {response.status_code}")
                
                if response.status_code != 200:
                    logger.warning(f"Error response: {response.text}")
                    return None
                
                data = response.json()
                logger.debug(f"Response structure: {list(data.keys()) if data else 'Empty response'}")
                
                time.sleep(1)  # Rate limiting
                return data
                
            except Exception as e:
                logger.error(f"Request error: {str(e)}")
                time.sleep(retry_delay)
                continue

        return None

    def _validate_game_data(self, game):
        """Validate game data structure"""
        try:
            logger.debug(f"Validating game data structure for game ID: {game.get('id')}")
            
            # Modified required fields structure
            required_fields = {
                'id': (str, int),  # Allow both string and integer types
                'teams': dict,
                'scores': dict,
                'periods': dict,
                'date': dict
            }
            
            # Basic structure validation
            for field, field_type in required_fields.items():
                if field not in game:
                    logger.warning(f"Missing required field: {field}")
                    return False
                if isinstance(field_type, tuple):
                    if not isinstance(game[field], field_type):
                        logger.warning(f"Invalid type for field {field}: expected one of {field_type}, got {type(game[field])}")
                        return False
                elif not isinstance(game[field], field_type):
                    logger.warning(f"Invalid type for field {field}: expected {field_type}, got {type(game[field])}")
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error validating game data: {str(e)}")
            return False

    def _is_game_live(self, game):
        """Check if game is live based on API status codes"""
        if not game or 'status' not in game:
            return False
            
        status = game.get('status', {})
        status_code = status.get('short', '')
        
        # API-NBA status codes for live games
        live_status_codes = ['Q1', 'Q2', 'Q3', 'Q4', 'HT', 'OT']
        
        logger.debug(f"Game {game.get('id')} status code: {status_code}")
        return status_code in live_status_codes

    def get_live_games(self):
        """Get current live games with scores and details"""
        try:
            est_time = datetime.now(timezone('US/Eastern'))
            today = est_time.strftime('%Y-%m-%d')
            
            # First, get all games for today
            response = self._make_request("games", {
                "date": today,
                "league": "standard",
                "season": "2024",  # Current season is 2024
                "timezone": "America/New_York"
            })
            
            if not response or 'response' not in response:
                logger.warning("No response or empty response from API")
                return []

            live_games = []
            for game in response.get('response', []):
                status = game.get('status', {})
                logger.debug(f"""
                    Game ID: {game.get('id')}
                    Status Short: {status.get('short')}
                    Status Long: {status.get('long')}
                    Clock: {status.get('clock')}
                    Period: {game.get('periods', {}).get('current')}
                """)
                
                if self._is_game_live(game):
                    try:
                        processed_game = {
                            'id': str(game.get('id')),
                            'teams': {
                                'home': {
                                    'id': str(game['teams']['home']['id']),
                                    'name': game['teams']['home']['name'],
                                    'score': int(game['scores']['home']['points'])
                                },
                                'visitors': {
                                    'id': str(game['teams']['visitors']['id']),
                                    'name': game['teams']['visitors']['name'],
                                    'score': int(game['scores']['visitors']['points'])
                                }
                            },
                            'period': game['periods'].get('current', 0),
                            'clock': status.get('clock', "00:00"),
                            'status': status.get('short', '')
                        }
                        live_games.append(processed_game)
                        logger.info(f"Added live game: {processed_game}")
                    except Exception as e:
                        logger.error(f"Error processing live game {game.get('id')}: {str(e)}")
                        continue

            logger.info(f"Found {len(live_games)} live games")
            return live_games

        except Exception as e:
            logger.error(f"Error getting live games: {str(e)}")
            return []

    def _process_live_game(self, game):
        """Process live game data"""
        try:
            # Process game data here
            processed_game = {
                'id': str(game.get('id')),
                'teams': {
                    'home': {
                        'id': str(game['teams']['home']['id']),
                        'name': game['teams']['home']['name'],
                        'score': game['scores']['home']['points']
                    },
                    'visitors': {
                        'id': str(game['teams']['visitors']['id']),
                        'name': game['teams']['visitors']['name'],
                        'score': game['scores']['visitors']['points']
                    }
                },
                'period': game['periods']['current'],
                'clock': game['status']['clock'] or "00:00",
                'status': game['status']['long']
            }
            return processed_game
        except Exception as e:
            logger.error(f"Error processing live game: {str(e)}")
            return None

    def _validate_live_game_data(self, game):
        """Validate required fields for live game data"""
        try:
            required_fields = {
                'id': str,
                'teams': {
                    'home': {'id': str, 'name': str},
                    'visitors': {'id': str, 'name': str}
                },
                'scores': {
                    'home': {'points': (int, str)},
                    'visitors': {'points': (int, str)}
                },
                'periods': {'current': (int, str)},
                'status': {'clock': str, 'long': str}
            }
            
            def validate_structure(data, structure):
                if not isinstance(data, dict):
                    return False
                for key, value in structure.items():
                    if key not in data:
                        logger.warning(f"Missing required field: {key}")
                        return False
                    if isinstance(value, dict):
                        if not validate_structure(data[key], value):
                            return False
                    else:
                        if not isinstance(data[key], value) and (
                            not isinstance(value, tuple) or 
                            not any(isinstance(data[key], t) for t in value)
                        ):
                            logger.warning(f"Invalid type for {key}: expected {value}, got {type(data[key])}")
                            return False
                return True
            
            return validate_structure(game, required_fields)
            
        except Exception as e:
            logger.error(f"Error validating game data: {str(e)}")
            return False

    def get_schedule_for_date(self, date_str):
        """Get scheduled games for a specific date with caching"""
        try:
            cache_key = f'schedule_{date_str}'
            cached_data = cache_manager.get(cache_key)
            if cached_data:
                logger.info(f"Using cached schedule for {date_str}")
                return cached_data

            logger.info(f"Fetching schedule for date: {date_str}")
            response = self._make_request("games", {
                "date": date_str,
                "league": "standard",
                "season": self.current_season
            })
            
            if not response or 'response' not in response:
                return []

            scheduled_games = []
            for game in response['response']:
                try:
                    # Skip finished games
                    if game.get('status', {}).get('long') == "Finished":
                        continue

                    processed_game = {
                        'id': self._safe_convert_id(game.get('id')),
                        'date': {
                            'start': game.get('date', {}).get('start') or date_str,
                            'timezone': game.get('date', {}).get('timezone', 'UTC')
                        },
                        'teams': {
                            'home': {
                                'id': self._safe_convert_id(game.get('teams', {}).get('home', {}).get('id')),
                                'name': game.get('teams', {}).get('home', {}).get('name', '')
                            },
                            'visitors': {  # Changed from 'away' to 'visitors'
                                'id': self._safe_convert_id(game.get('teams', {}).get('visitors', {}).get('id')),
                                'name': game.get('teams', {}).get('visitors', {}).get('name', '')
                            }
                        },
                        'status': {
                            'long': game.get('status', {}).get('long', ''),
                            'short': game.get('status', {}).get('short', '')
                        }
                    }
                    scheduled_games.append(processed_game)

                except Exception as e:
                    logger.error(f"Error processing game: {str(e)}")
                    continue

            # Cache the processed games
            cache_manager.set(cache_key, scheduled_games, expires_in_minutes=30)
            return scheduled_games

        except Exception as e:
            logger.error(f"Error in get_schedule_for_date: {str(e)}")
            return []

    def check_games_status(self):
        """Check the status of today's games and determine if we should show tomorrow's schedule"""
        try:
            today = datetime.now().strftime('%Y-%m-%d')
            response = self._make_request("games", {
                "date": today,
                "league": "standard",
                "season": self.current_season
            })
            
            if not response or 'response' not in response:
                return {'show_tomorrow': True, 'active_games': 0}

            all_games = response.get('response', [])
            active_games = [
                g for g in all_games 
                if g.get('status', {}).get('long') not in ["Finished", "Not Started"]
            ]
            
            return {
                'show_tomorrow': len(active_games) == 0,
                'active_games': len(active_games),
                'total_games': len(all_games),
                'finished_games': len([g for g in all_games if g.get('status', {}).get('long') == "Finished"])
            }

        except Exception as e:
            logger.error(f"Error checking games status: {str(e)}")
            return {'show_tomorrow': True, 'active_games': 0}

    def _calculate_available_coins(self):
        """Calculate available coins for betting"""
        remaining_games = 2460 - self.games_played
        return max(0, self.total_coins / remaining_games)

    def _calculate_potential_boost(self):
        """Calculate potential boost points for accurate predictions"""
        remaining_boost_needed = self.target_boost_points - self.boost_points
        remaining_games = 2460 - self.games_played
        return remaining_boost_needed / max(1, remaining_games)

    def update_prediction_results(self, game_id, actual_score, predicted_score):
        """Update prediction results and calculate rewards"""
        try:
            # Calculate accuracy based on score difference
            score_diff = abs(actual_score['home'] - predicted_score['home'])
            accuracy = 1 - (score_diff / max(actual_score['home'], predicted_score['home']))
            
            # Award coins and boost points based on accuracy
            if accuracy >= 0.95:  # Within 3 points
                self.total_coins += 10  # Bonus for high accuracy
                self.boost_points += 1
            elif accuracy >= 0.85:  # Within 5 points
                self.total_coins += 5
            
            self.games_played += 1
            
            return {
                'accuracy': accuracy,
                'coins_earned': self.total_coins,
                'boost_points': self.boost_points,
                'games_played': self.games_played
            }

        except Exception as e:
            logger.error(f"Error updating prediction results: {str(e)}")
            return None

    def get_prediction_stats(self):
        """Get current prediction statistics"""
        return {
            'total_coins': self.total_coins,
            'boost_points': self.boost_points,
            'games_played': self.games_played,
            'accuracy_rate': self.boost_points / max(1, self.games_played),
            'remaining_games': 2460 - self.games_played
        }

    def get_team_stats(self, team_id):
        """Get team statistics with caching"""
        try:
            cache_key = f'team_stats_{team_id}'
            cached_data = cache_manager.get(cache_key)
            if cached_data:
                logger.info(f"Using cached stats for team {team_id}")
                return cached_data

            logger.info(f"Fetching stats for team ID: {team_id}")
            
            # Get basic team statistics
            response = self._make_request("teams/statistics", {
                "id": team_id,
                "season": self.current_season
            })
            
            if not response or 'response' not in response:
                logger.warning(f"No statistics found for team {team_id}")
                return None
            
            stats = response['response'][0] if response['response'] else None
            if not stats:
                logger.warning(f"Empty statistics for team {team_id}")
                return None
            
            games = int(stats.get('games', 1))
            
            # Process comprehensive statistics
            processed_stats = {
                # Offensive Stats
                'points_per_game': float(stats.get('points', 0)) / games,
                'field_goal_pct': float(stats.get('fgp', 0)),
                'three_point_pct': float(stats.get('tpp', 0)),
                'free_throw_pct': float(stats.get('ftp', 0)),
                'offensive_rebounds_per_game': float(stats.get('offReb', 0)) / games,
                'assists_per_game': float(stats.get('assists', 0)) / games,
                
                # Defensive Stats
                'defensive_rebounds_per_game': float(stats.get('defReb', 0)) / games,
                'steals_per_game': float(stats.get('steals', 0)) / games,
                'blocks_per_game': float(stats.get('blocks', 0)) / games,
                'fouls_per_game': float(stats.get('fouls', 0)) / games,
                
                # Shooting Stats
                'field_goals_made_per_game': float(stats.get('fgm', 0)) / games,
                'field_goals_attempted_per_game': float(stats.get('fga', 0)) / games,
                'three_pointers_made_per_game': float(stats.get('tpm', 0)) / games,
                'three_pointers_attempted_per_game': float(stats.get('tpa', 0)) / games,
                'free_throws_made_per_game': float(stats.get('ftm', 0)) / games,
                'free_throws_attempted_per_game': float(stats.get('fta', 0)) / games,
                
                # Calculated Stats
                'turnover_per_game': float(stats.get('turnovers', 0)) / games,
                'points_allowed_per_game': self._calculate_points_allowed(team_id),
                'win_percentage': float(stats.get('win', {}).get('percentage', 0)),
                'games_played': games,
                
                # Additional Context
                'home_win_percentage': self._calculate_home_win_pct(team_id),
                'away_win_percentage': self._calculate_away_win_pct(team_id),
                'last_10_win_percentage': self._calculate_last_10_win_pct(team_id),
                
                # Derived Stats
                'net_rating': self._calculate_net_rating(stats, games),
                'effective_fg_pct': self._calculate_efg_pct(stats),
                'true_shooting_pct': self._calculate_ts_pct(stats),
                'pace': self._calculate_pace(stats, games)
            }
            
            logger.debug(f"Processed stats for team {team_id}: {processed_stats}")
            if stats:
                cache_manager.set(cache_key, processed_stats, expires_in_minutes=60)
            return processed_stats
            
        except Exception as e:
            logger.error(f"Error getting team stats for {team_id}: {str(e)}")
            return None

    def _calculate_efg_pct(self, stats):
        """Calculate Effective Field Goal Percentage"""
        try:
            fgm = float(stats.get('fgm', 0))
            tpm = float(stats.get('tpm', 0))
            fga = float(stats.get('fga', 0))
            if fga == 0:
                return 0.0
            return (fgm + 0.5 * tpm) / fga * 100
        except Exception:
            return 0.0

    def _calculate_ts_pct(self, stats):
        """Calculate True Shooting Percentage"""
        try:
            points = float(stats.get('points', 0))
            fga = float(stats.get('fga', 0))
            fta = float(stats.get('fta', 0))
            if (2 * (fga + 0.44 * fta)) == 0:
                return 0.0
            return (points / (2 * (fga + 0.44 * fta))) * 100
        except Exception:
            return 0.0

    def _calculate_net_rating(self, stats, games):
        """Calculate Net Rating"""
        try:
            points_scored = float(stats.get('points', 0))
            points_allowed = float(stats.get('points_against', 0))
            possessions = self._estimate_possessions(stats)
            if possessions == 0:
                return 0.0
            offensive_rating = (points_scored / possessions) * 100
            defensive_rating = (points_allowed / possessions) * 100
            return offensive_rating - defensive_rating
        except Exception:
            return 0.0

    def _estimate_possessions(self, stats):
        """Estimate number of possessions"""
        try:
            fga = float(stats.get('fga', 0))
            fta = float(stats.get('fta', 0))
            orb = float(stats.get('offReb', 0))
            drb = float(stats.get('defReb', 0))
            to = float(stats.get('turnovers', 0))
            fgm = float(stats.get('fgm', 0))
            return 0.96 * (fga + 0.44 * fta - 1.07 * (orb / (orb + drb)) * (fga - fgm) + to)
        except Exception:
            return 0.0

    def get_team_standings(self, team_id):
        """Get team standings information"""
        try:
            response = self._make_request("standings", {
                "team": team_id,
                "season": self.current_season
            })
            
            if not response or 'response' not in response:
                return None
                
            standings = response['response'][0]
            return {
                'conference_rank': standings.get('conference', {}).get('rank'),
                'win_pct': standings.get('win', {}).get('percentage'),
                'last_10': standings.get('streak')
            }
            
        except Exception as e:
            logger.error(f"Error getting team standings: {str(e)}")
            return None

    def get_team_form(self, team_id):
        """Get team's recent form based on last few games"""
        try:
            response = self._make_request("games", {
                "team": team_id,
                "season": self.current_season,
                "last": "5"
            })
            
            if not response or 'response' not in response:
                return None
                
            recent_games = response['response']
            wins = 0
            total_points = 0
            
            for game in recent_games:
                team_score = game['scores']['home']['points'] if game['teams']['home']['id'] == team_id else game['scores']['visitors']['points']
                opp_score = game['scores']['visitors']['points'] if game['teams']['home']['id'] == team_id else game['scores']['home']['points']
                
                if team_score > opp_score:
                    wins += 1
                total_points += team_score
            
            return {
                'recent_win_pct': wins / len(recent_games) if recent_games else 0,
                'avg_points': total_points / len(recent_games) if recent_games else 0
            }
            
        except Exception as e:
            logger.error(f"Error getting team form: {str(e)}")
            return None

    def _calculate_points_allowed(self, team_id):
        """Calculate average points allowed per game"""
        try:
            response = self._make_request("games", {
                "team": team_id,
                "season": self.current_season,
                "last": "10"  # Last 10 games for recent performance
            })
            
            if not response or 'response' not in response:
                return 0.0
                
            games = response['response']
            total_points_allowed = 0
            game_count = 0
            
            for game in games:
                try:
                    # Determine if team was home or away
                    is_home = game['teams']['home']['id'] == team_id
                    
                    # Get opponent's score
                    points_allowed = (
                        game['scores']['visitors']['points'] if is_home 
                        else game['scores']['home']['points']
                    )
                    
                    total_points_allowed += float(points_allowed)
                    game_count += 1
                    
                except (KeyError, ValueError):
                    continue
            
            return total_points_allowed / max(1, game_count)
            
        except Exception as e:
            logger.error(f"Error calculating points allowed: {str(e)}")
            return 0.0

    def _calculate_home_win_pct(self, team_id):
        """Calculate home game win percentage"""
        try:
            response = self._make_request("games", {
                "team": team_id,
                "season": self.current_season,
                "home": "true"
            })
            
            if not response or 'response' not in response:
                return 0.0
                
            games = response['response']
            wins = 0
            total_games = 0
            
            for game in games:
                try:
                    if game['status']['long'] != "Finished":
                        continue
                        
                    home_score = float(game['scores']['home']['points'])
                    away_score = float(game['scores']['visitors']['points'])
                    
                    if home_score > away_score:
                        wins += 1
                    total_games += 1
                    
                except (KeyError, ValueError):
                    continue
            
            return wins / max(1, total_games)
            
        except Exception as e:
            logger.error(f"Error calculating home win percentage: {str(e)}")
            return 0.0

    def _calculate_away_win_pct(self, team_id):
        """Calculate away game win percentage"""
        try:
            response = self._make_request("games", {
                "team": team_id,
                "season": self.current_season,
                "home": "false"
            })
            
            if not response or 'response' not in response:
                return 0.0
                
            games = response['response']
            wins = 0
            total_games = 0
            
            for game in games:
                try:
                    if game['status']['long'] != "Finished":
                        continue
                        
                    home_score = float(game['scores']['home']['points'])
                    away_score = float(game['scores']['visitors']['points'])
                    
                    if away_score > home_score:
                        wins += 1
                    total_games += 1
                    
                except (KeyError, ValueError):
                    continue
            
            return wins / max(1, total_games)
            
        except Exception as e:
            logger.error(f"Error calculating away win percentage: {str(e)}")
            return 0.0

    def _calculate_last_10_win_pct(self, team_id):
        """Calculate win percentage for last 10 games"""
        try:
            response = self._make_request("games", {
                "team": team_id,
                "season": self.current_season,
                "last": "10"
            })
            
            if not response or 'response' not in response:
                return 0.0
                
            games = response['response']
            wins = 0
            total_games = 0
            
            for game in games:
                try:
                    if game['status']['long'] != "Finished":
                        continue
                        
                    is_home = game['teams']['home']['id'] == team_id
                    home_score = float(game['scores']['home']['points'])
                    away_score = float(game['scores']['visitors']['points'])
                    
                    if (is_home and home_score > away_score) or (not is_home and away_score > home_score):
                        wins += 1
                    total_games += 1
                    
                except (KeyError, ValueError):
                    continue
            
            return wins / max(1, total_games)
            
        except Exception as e:
            logger.error(f"Error calculating last 10 win percentage: {str(e)}")
            return 0.0

    def _calculate_pace(self, stats, games):
        """Calculate team's pace (possessions per 48 minutes)"""
        try:
            possessions = self._estimate_possessions(stats)
            if games == 0:
                return 0.0
            return (possessions / games) * 48 / 40  # Adjust for regulation time
        except Exception as e:
            logger.error(f"Error calculating pace: {str(e)}")
            return 0.0

    def get_h2h_games(self, home_team_id, away_team_id):
        """Get head-to-head games between two teams"""
        try:
            # Get all games for home team
            response = self._make_request("games", {
                "team": home_team_id,
                "season": self.current_season
            })
            
            if not response or 'response' not in response:
                return []
                
            # Filter for games against away team
            h2h_games = [
                game for game in response['response']
                if (game['teams']['home']['id'] == home_team_id and 
                    game['teams']['visitors']['id'] == away_team_id) or
                   (game['teams']['home']['id'] == away_team_id and 
                    game['teams']['visitors']['id'] == home_team_id)
            ]
            
            return h2h_games
            
        except Exception as e:
            logger.error(f"Error getting H2H games: {str(e)}")
            return []

    def get_last_games(self, team_id, limit=5):
        """Get team's last N games"""
        try:
            response = self._make_request("games", {
                "team": team_id,
                "season": self.current_season,
                "last": str(limit)
            })
            
            if not response or 'response' not in response:
                return []
                
            return response['response']
            
        except Exception as e:
            logger.error(f"Error getting last games: {str(e)}")
            return []

    def get_team_name(self, team_id):
        """Get team name from ID"""
        try:
            response = self._make_request("teams", {"id": team_id})
            if response and 'response' in response and response['response']:
                return response['response'][0]['name']
            return f"Team {team_id}"
        except Exception as e:
            logger.error(f"Error getting team name: {str(e)}")
            return f"Team {team_id}"

    def get_team_details(self, team_id):
        """Get detailed information about a team."""
        try:
            logger.info(f"Fetching details for team ID: {team_id}")
            response = self._make_request("teams", {"id": team_id})
            
            logger.debug(f"Team details response: {response}")
            
            if not response or 'response' not in response:
                logger.warning(f"No details found for team {team_id}")
                return None
            
            return response['response'][0] if response['response'] else None
            
        except Exception as e:
            logger.error(f"Error getting team details for {team_id}: {str(e)}")
            return None

    def get_team_roster(self, team_id):
        """Get the roster of a team for the current season."""
        try:
            logger.info(f"Fetching roster for team ID: {team_id}")
            response = self._make_request("players", {
                "team": team_id,
                "season": self.current_season
            })
            
            logger.debug(f"Team roster response: {response}")
            
            if not response or 'response' not in response:
                logger.warning(f"No roster found for team {team_id}")
                return None
            
            return response['response'] if response['response'] else None
            
        except Exception as e:
            logger.error(f"Error getting team roster for {team_id}: {str(e)}")
            return None

    def get_team_recent_performance(self, team_id, num_games=5):
        """Get recent performance statistics for a team."""
        try:
            logger.info(f"Fetching recent performance for team ID: {team_id}")
            response = self._make_request("games", {
                "team": team_id,
                "season": self.current_season,
                "last": str(num_games)
            })
            
            logger.debug(f"Recent performance response: {response}")
            
            if not response or 'response' not in response:
                logger.warning(f"No recent performance data found for team {team_id}")
                return None
            
            recent_games = response['response']
            wins = 0
            total_points = 0
            total_points_allowed = 0
            
            for game in recent_games:
                team_score = game['scores']['home']['points'] if game['teams']['home']['id'] == team_id else game['scores']['visitors']['points']
                opp_score = game['scores']['visitors']['points'] if game['teams']['home']['id'] == team_id else game['scores']['home']['points']
                
                if team_score > opp_score:
                    wins += 1
                total_points += team_score
                total_points_allowed += opp_score
            
            return {
                'recent_win_pct': wins / len(recent_games) if recent_games else 0,
                'avg_points': total_points / len(recent_games) if recent_games else 0,
                'avg_points_allowed': total_points_allowed / len(recent_games) if recent_games else 0
            }
            
        except Exception as e:
            logger.error(f"Error getting recent performance for team {team_id}: {str(e)}")
            return None

    def get_live_game_details(self):
        """Get current live games with scores and details"""
        try:
            today = datetime.now().strftime('%Y-%m-%d')
            response = self._make_request("games", {
                "date": today,
                "league": "standard",
                "season": self.current_season,
                "live": "all"  # Get all live games
            })
            
            if not response or 'response' not in response:
                return []

            live_games = []
            for game in response['response']:
                if game.get('status', {}).get('long') == "In Play":
                    processed_game = {
                        'id': str(game.get('id')),
                        'teams': {
                            'home': {
                                'id': str(game['teams']['home']['id']),
                                'name': game['teams']['home']['name'],
                                'score': game['scores']['home']['points']
                            },
                            'visitors': {
                                'id': str(game['teams']['visitors']['id']),
                                'name': game['teams']['visitors']['name'],
                                'score': game['scores']['visitors']['points']
                            }
                        },
                        'period': game['periods']['current'],
                        'clock': game['status']['clock'] or "00:00",
                        'status': game['status']['long']
                    }
                    live_games.append(processed_game)
            
            return live_games

        except Exception as e:
            logger.error(f"Error getting live games: {str(e)}")
            return []

    def _validate_game_status(self, game):
        """Validate game status information"""
        try:
            status = game.get('status', {})
            if not isinstance(status, dict):
                logger.warning(f"Invalid status format for game {game.get('id')}")
                return False
                
            # Check for required fields
            required_fields = {
                'long': str,
                'short': str,
                'clock': (str, type(None))
            }
            
            for field, field_type in required_fields.items():
                value = status.get(field)
                if not isinstance(value, field_type):
                    logger.warning(f"Invalid {field} type in status: {type(value)}")
                    return False
                    
            return True
            
        except Exception as e:
            logger.error(f"Error validating game status: {str(e)}")
            return False


