

document.addEventListener('DOMContentLoaded', function() {
    // Function to update prediction status
    function updatePredictionStatus() {
        fetch('/api/update_predictions', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            credentials: 'same-origin'
        })
        .then(response => response.json())
        .then(data => {
            if (data.updated) {
                location.reload();
            }
        })
        .catch(error => console.error('Error:', error));
    }

    // Update predictions every 5 minutes
    setInterval(updatePredictionStatus, 300000);

    // Add animation for new rewards
    document.querySelectorAll('.new-reward').forEach(element => {
        element.classList.add('animate-bounce');
        setTimeout(() => {
            element.classList.remove('animate-bounce');
        }, 2000);
    });
});

