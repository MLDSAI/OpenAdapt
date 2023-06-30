/*
 * Function to send a message to the background script
*/
function sendMessageToBackgroundScript(message) {
    chrome.runtime.sendMessage(message);
  }
  
  
/*
* Function to detect DOM changes
*/
function detectDOMChanges() {
// Create a mutation observer
const observer = new MutationObserver(function(mutationsList) {
    // Send a message to the background script when a DOM change is detected
    sendMessageToBackgroundScript({
    action: 'logDOMChange',
    documentObject: document,
    });
});

// Start observing DOM changes
observer.observe(document, {
    subtree: true,
    childList: true,
    attributes: true,
    characterData: true,
});
}

// Call the function to start detecting DOM changes
detectDOMChanges();
