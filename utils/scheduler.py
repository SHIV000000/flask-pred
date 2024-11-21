# utils/scheduler.py

from datetime import datetime, timedelta
import threading
import time

class PredictionScheduler:
    def __init__(self, api_client, predictor):
        self.api_client = api_client
        self.predictor = predictor
        self.running = False
        self.thread = None

    def schedule_predictions(self):
        """Schedule predictions for today's games"""
        self.running = True
        self.thread = threading.Thread(target=self._run_scheduler)
        self.thread.daemon = True
        self.thread.start()

    def _run_scheduler(self):
        """Run the scheduler loop"""
        while self.running:
            try:
                # Update predictions
                predictions = self._update_predictions()
                
                # Store or process predictions as needed
                if predictions:
                    print(f"Updated {len(predictions)} predictions")
                
                # Wait for an hour before next update
                time.sleep(3600)  # 3600 seconds = 1 hour
                
            except Exception as e:
                print(f"Scheduler error: {str(e)}")
                time.sleep(60)  # Wait a minute before retrying on error

    def _update_predictions(self):
        """Update predictions for today's games"""
        try:
            games = self.api_client.get_todays_schedule()
            predictions = []
            
            for game in games:
                home_team_id = game['teams']['home']['id']
                away_team_id = game['teams']['away']['id']
                
                prediction = self.predictor.predict_game(home_team_id, away_team_id)
                if prediction:
                    predictions.append({
                        'game_id': game['id'],
                        'prediction': prediction,
                        'game_info': game
                    })
            
            return predictions
        except Exception as e:
            print(f"Error updating predictions: {str(e)}")
            return []

    def stop(self):
        """Stop the scheduler"""
        self.running = False
        if self.thread:
            self.thread.join()



