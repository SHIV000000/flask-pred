// static/js/app.js

function updateLiveGames() {
    fetch('/api/live-games')
        .then(response => response.json())
        .then(data => {
            const liveGamesContainer = document.getElementById('live-games');
            if (liveGamesContainer) {
                updateGamesDisplay(liveGamesContainer, data);
            }
        })
        .catch(error => console.error('Error:', error));
}

function updateScheduledGames() {
    fetch('/api/scheduled-games')
        .then(response => response.json())
        .then(data => {
            const scheduledGamesContainer = document.getElementById('scheduled-games');
            if (scheduledGamesContainer) {
                updateGamesDisplay(scheduledGamesContainer, data);
            }
        })
        .catch(error => console.error('Error:', error));
}

function updateGamesDisplay(container, games) {
    container.innerHTML = '';
    games.forEach(game => {
        const gameElement = document.createElement('div');
        gameElement.className = 'bg-white rounded-lg shadow-md p-6 mb-4';
        
        // Add team names
        const teams = document.createElement('div');
        teams.className = 'flex justify-between items-center mb-4';
        teams.innerHTML = `
            <h3 class="text-lg font-semibold">${game.teams.home.name} vs ${game.teams.away.name}</h3>
            <span class="bg-red-500 text-white px-2 py-1 rounded-full text-sm">LIVE</span>
        `;
        gameElement.appendChild(teams);

        // Add scores and period
        const scoresContainer = document.createElement('div');
        scoresContainer.className = 'grid grid-cols-3 gap-4 text-center mb-4';
        scoresContainer.innerHTML = `
            <div>
                <p class="font-bold">${game.scores.home}</p>
                <p class="text-sm text-gray-600">${game.teams.home.name}</p>
            </div>
            <div class="flex items-center justify-center">
                <p class="text-sm font-semibold">Q${game.period}</p>
            </div>
            <div>
                <p class="font-bold">${game.scores.away}</p>
                <p class="text-sm text-gray-600">${game.teams.away.name}</p>
            </div>
        `;
        gameElement.appendChild(scoresContainer);

        // Add win probability
        const winProbability = document.createElement('div');
        winProbability.className = 'bg-gray-100 rounded p-3 mt-4';
        winProbability.innerHTML = `
            <p class="text-sm font-semibold">Win Probability</p>
            <div class="w-full bg-gray-200 rounded-full h-2.5 mt-2">
                <div class="bg-blue-600 h-2.5 rounded-full" style="width: ${game.prediction.win_probability * 100}%"></div>
            </div>
        `;
        gameElement.appendChild(winProbability);

        container.appendChild(gameElement);
    });
}

