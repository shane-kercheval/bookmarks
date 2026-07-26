import {
  handleCreateBookmark,
  handleGetTags,
  handleGetLimits,
  handleSearchBookmarks,
  getAuthStatus,
} from './background-core.js';

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  // Only this extension's own pages (popup/options) may drive the worker —
  // combined with no externally_connectable in the manifest, tokens and
  // API access never serve another extension or web page.
  if (sender.id !== chrome.runtime.id) return;

  if (message.type === 'CREATE_BOOKMARK') {
    handleCreateBookmark(message).then(sendResponse).catch(err =>
      sendResponse({ success: false, error: err.message })
    );
    return true;
  }

  if (message.type === 'GET_TAGS') {
    handleGetTags().then(sendResponse).catch(err =>
      sendResponse({ success: false, error: err.message })
    );
    return true;
  }

  if (message.type === 'GET_LIMITS') {
    handleGetLimits().then(sendResponse).catch(err =>
      sendResponse({ success: false, error: err.message })
    );
    return true;
  }

  if (message.type === 'SEARCH_BOOKMARKS') {
    handleSearchBookmarks(message).then(sendResponse).catch(err =>
      sendResponse({ success: false, error: err.message })
    );
    return true;
  }

  if (message.type === 'GET_AUTH_STATUS') {
    getAuthStatus().then(sendResponse).catch(() =>
      sendResponse({ activeMode: 'none', hasPat: false, hasSession: false })
    );
    return true;
  }
});
