# utils/task_manager.py

import threading
import time
from datetime import datetime, timedelta
import logging
from utils.cache_manager import cache_manager

logger = logging.getLogger(__name__)

class TaskManager:
    def __init__(self, api_client, predictor):
        self.api_client = api_client
        self.predictor = predictor
        self.is_running = False
        self.cache_refresh_interval = 21600  # 6 hours in seconds
        self.thread = None

    def start(self):
        """Start the background task manager"""
        if not self.is_running:
            self.is_running = True
            self.thread = threading.Thread(target=self._run_tasks)
            self.thread.daemon = True
            self.thread.start()
            logger.info("Task Manager started")

    def stop(self):
        """Stop the background task manager"""
        self.is_running = False
        if self.thread:
            self.thread.join()
        logger.info("Task Manager stopped")

    def _run_tasks(self):
        """Main task loop"""
        while self.is_running:
            try:
                self._refresh_cache()
                time.sleep(300)  # Check every 5 minutes
            except Exception as e:
                logger.error(f"Error in task loop: {str(e)}")

    def _refresh_cache(self):
        """Refresh cached data if needed"""
        try:
            current_time = datetime.now()
            
            # Get schedule for next 3 days
            for i in range(3):
                date = (current_time + timedelta(days=i)).strftime('%Y-%m-%d')
                self._cache_games_for_date(date)

            # Clear old cache entries
            cache_manager.clear_old()
            
        except Exception as e:
            logger.error(f"Error refreshing cache: {str(e)}")

    def _cache_games_for_date(self, date):
        """Cache all game-related data for a specific date"""
        try:
            # Cache schedule
            games = self.api_client.get_schedule_for_date(date)
            if not games:
                return

            for game in games:
                game_id = str(game['id'])
                home_team_id = game['teams']['home']['id']
                away_team_id = game['teams']['visitors']['id']

                # Cache team stats
                self._cache_team_data(home_team_id)
                self._cache_team_data(away_team_id)

                # Cache prediction
                prediction = self.predictor.predict_game(
                    home_team_id=home_team_id,
                    visitors_team_id=away_team_id,
                    game_id=game_id
                )
                if prediction:
                    cache_key = f'prediction_{game_id}'
                    cache_manager.set(cache_key, prediction, expires_in_minutes=360)  # 6 hours

        except Exception as e:
            logger.error(f"Error caching games for date {date}: {str(e)}")

    def _cache_team_data(self, team_id):
        """Cache all relevant team data"""
        try:
            # Cache team stats
            stats = self.api_client.get_team_stats(team_id)
            if stats:
                cache_key = f'team_stats_{team_id}'
                cache_manager.set(cache_key, stats, expires_in_minutes=360)

            # Cache team details
            details = self.api_client.get_team_details(team_id)
            if details:
                cache_key = f'team_details_{team_id}'
                cache_manager.set(cache_key, details, expires_in_minutes=360)

            # Cache roster
            roster = self.api_client.get_team_roster(team_id)
            if roster:
                cache_key = f'team_roster_{team_id}'
                cache_manager.set(cache_key, roster, expires_in_minutes=360)

        except Exception as e:
            logger.error(f"Error caching team data for team {team_id}: {str(e)}")
