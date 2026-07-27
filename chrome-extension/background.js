import {
  handleCreateBookmark,
  handleGetTags,
  handleGetLimits,
  handleSearchBookmarks,
} from './background-core.js';
import { getAuthStatus } from './auth.js';

// Uniform failure envelope for thrown handler errors; authRequired (set when
// no credential exists at resolution time) is the popup's structured routing
// signal for signed-out copy — flag, not prose.
function failureResponse(err) {
  return { success: false, error: err.message, authRequired: err.authRequired === true };
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  // Only this extension's own pages (popup/options) may drive the worker —
  // combined with no externally_connectable in the manifest, tokens and
  // API access never serve another extension or web page.
  if (sender.id !== chrome.runtime.id) return;

  if (message.type === 'CREATE_BOOKMARK') {
    handleCreateBookmark(message).then(sendResponse).catch(err =>
      sendResponse(failureResponse(err))
    );
    return true;
  }

  if (message.type === 'GET_TAGS') {
    handleGetTags().then(sendResponse).catch(err =>
      sendResponse(failureResponse(err))
    );
    return true;
  }

  if (message.type === 'GET_LIMITS') {
    handleGetLimits().then(sendResponse).catch(err =>
      sendResponse(failureResponse(err))
    );
    return true;
  }

  if (message.type === 'SEARCH_BOOKMARKS') {
    handleSearchBookmarks(message).then(sendResponse).catch(err =>
      sendResponse(failureResponse(err))
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
