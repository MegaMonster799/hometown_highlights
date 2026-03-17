// Immediately invoked function to avoid polluting global scope
(function(){
    /**
     * Display flash messages to the user via alerts.
     * In production, this could be replaced with toast notifications or custom modals.
     */
    function showMessage(messageType, messageText) {
        if (!messageText) return;
        
        try {
            if (messageType === 'error') {
                alert(messageText);
            } else if (messageType === 'success') {
                alert(messageText);
            }
        } catch (error) {
            console.error('Flash message display error:', error);
        }
    }

    // Wait for DOM to be fully loaded before accessing elements
    document.addEventListener('DOMContentLoaded', function(){
        try {
            console.log('flash.js: DOMContentLoaded running');
            
            // Look for the hidden element that contains flash message data from the server
            var flashDataElement = document.getElementById('flash-data');
            console.log('flash.js: flash-data element=', flashDataElement);
            
            if (!flashDataElement) return;
            
            // Extract error and success messages from data attributes
            var errorMessage = flashDataElement.getAttribute('data-error');
            var successMessage = flashDataElement.getAttribute('data-success');
            console.log('flash.js: data-error=', errorMessage, 'data-success=', successMessage);
            
            // Show whichever message is present (errors take priority)
            if (errorMessage) {
                showMessage('error', errorMessage);
            } else if (successMessage) {
                showMessage('success', successMessage);
            }
        } catch (error) {
            console.error('flash.js error in DOMContentLoaded:', error);
        }
    });
})();
 
