// Package auth: browser-based login via OAuth 2.0 authorization code + PKCE
// against Clerk (RFC 7636 + RFC 8252 loopback redirect). Replaces the Auth0
// device-authorization flow — Clerk does not offer device flow (an accepted
// capability loss recorded in the migration ledger); headless machines use
// the PAT path (`tiddly login --token`) instead, and the timeout error says so.
package auth

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"os"
	"os/exec"
	"runtime"
	"strings"
	"time"
)

// BrowserOpener opens URLs in the user's browser.
type BrowserOpener interface {
	Open(url string) error
}

// DefaultBrowserOpener opens URLs using the platform-specific command.
type DefaultBrowserOpener struct{}

func (o *DefaultBrowserOpener) Open(url string) error {
	var cmd string
	var args []string

	switch runtime.GOOS {
	case "darwin":
		cmd = "open"
		args = []string{url}
	case "linux":
		cmd = "xdg-open"
		args = []string{url}
	case "windows":
		cmd = "rundll32"
		args = []string{"url.dll,FileProtocolHandler", url}
	default:
		return fmt.Errorf("unsupported platform: %s", runtime.GOOS)
	}

	return exec.Command(cmd, args...).Start()
}

// OAuthConfig holds the Clerk OAuth application configuration for the CLI.
// These are public client values (not secrets — a public PKCE client has no
// client secret by design; possession of these values grants nothing without
// a user completing the browser sign-in).
type OAuthConfig struct {
	// Issuer is the Clerk Frontend API origin (also the OAuth issuer),
	// e.g. https://clerk.tiddly.me. Endpoints hang off it: /oauth/authorize,
	// /oauth/token.
	Issuer   string
	ClientID string
}

// prodOAuthClientID is the client_id of the production "Tiddly CLI" OAuth
// application (created 2026-07-13, public PKCE-required client). A public
// value by OAuth design — it identifies the app, it authenticates nothing.
const prodOAuthClientID = "ORodzjFt0ZR8fTJQ"

// DefaultOAuthConfig returns the production Clerk configuration, with env
// var overrides for pointing at the dev instance.
func DefaultOAuthConfig() OAuthConfig {
	cfg := OAuthConfig{
		Issuer:   "https://clerk.tiddly.me",
		ClientID: prodOAuthClientID,
	}

	if v := os.Getenv("TIDDLY_OAUTH_ISSUER"); v != "" {
		cfg.Issuer = v
	}
	if v := os.Getenv("TIDDLY_OAUTH_CLIENT_ID"); v != "" {
		cfg.ClientID = v
	}

	return cfg
}

// TokenResponse is the response from the token endpoint.
type TokenResponse struct {
	AccessToken  string `json:"access_token"`
	RefreshToken string `json:"refresh_token"`
	TokenType    string `json:"token_type"`
	ExpiresIn    int    `json:"expires_in"`
}

// oauthScopes must stay within the scopes registered on the Clerk OAuth
// application. offline_access is what makes Clerk issue a refresh token.
const oauthScopes = "openid profile email offline_access"

// defaultLoginTimeout bounds the wait for the browser callback. The device
// flow used the server-provided code expiry; the loopback flow has no server
// equivalent, so this is our own bound.
const defaultLoginTimeout = 5 * time.Minute

// defaultUserAgent identifies the CLI to Clerk's endpoints. REQUIRED, not
// cosmetic: Clerk's token endpoint bot-blocks default HTTP-library
// User-Agents with a bare 403 and no OAuth error body (found empirically
// during the milestone's opening probe; recorded in the migration ledger).
const defaultUserAgent = "tiddly-cli"

// PKCEFlow handles browser-based login: authorization code + PKCE (S256)
// with a loopback redirect per RFC 8252 §7.3.
type PKCEFlow struct {
	Config     OAuthConfig
	Browser    BrowserOpener
	HTTPClient *http.Client
	// Output is where user-facing messages are written (defaults to os.Stderr).
	Output io.Writer
	// BaseURL overrides the issuer-derived base for OAuth endpoints.
	// Used in tests to point at httptest servers.
	BaseURL string
	// UserAgent is sent on token-endpoint requests (see defaultUserAgent).
	UserAgent string
	// LoginTimeout bounds the wait for the browser callback (see
	// defaultLoginTimeout). Tests shorten it.
	LoginTimeout time.Duration
}

// NewPKCEFlow creates a PKCEFlow with default settings.
func NewPKCEFlow(cfg OAuthConfig) *PKCEFlow {
	return &PKCEFlow{
		Config:       cfg,
		Browser:      &DefaultBrowserOpener{},
		HTTPClient:   &http.Client{Timeout: 10 * time.Second},
		Output:       os.Stderr,
		UserAgent:    defaultUserAgent,
		LoginTimeout: defaultLoginTimeout,
	}
}

// oauthBaseURL returns the base URL for the OAuth endpoints.
func (f *PKCEFlow) oauthBaseURL() string {
	if f.BaseURL != "" {
		return f.BaseURL
	}
	return f.Config.Issuer
}

// errInvalidGrant marks an OAuth invalid_grant response; per RFC 6749 §5.2 it
// covers both dead refresh tokens and expired/used authorization codes, so
// each caller maps it to grant-appropriate wording.
var errInvalidGrant = errors.New("invalid_grant")

// callbackResult carries the authorization response from the loopback
// listener to the flow.
type callbackResult struct {
	code string
	// err is set when the provider redirected back with an OAuth error
	// (e.g. the user denied consent).
	err error
}

// Login performs the full PKCE flow: start a loopback listener, open the
// browser to the authorize URL, wait for the redirect, exchange the code.
// The context should be cancelled on Ctrl+C for clean exit.
func (f *PKCEFlow) Login(ctx context.Context) (*TokenResponse, error) {
	verifier, challenge, err := newPKCEPair()
	if err != nil {
		return nil, fmt.Errorf("generating PKCE pair: %w", err)
	}
	state, err := randomToken(24)
	if err != nil {
		return nil, fmt.Errorf("generating state: %w", err)
	}

	// 127.0.0.1, not localhost: RFC 8252 §7.3 loopback semantics without DNS
	// resolution surprises. Port 0 lets the OS pick — the registered redirect
	// URI is port-less, and Clerk matches any loopback port.
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		return nil, fmt.Errorf("starting local callback listener: %w", err)
	}
	redirectURI := fmt.Sprintf("http://127.0.0.1:%d/callback", listener.Addr().(*net.TCPAddr).Port)

	results := make(chan callbackResult, 1)
	server := &http.Server{
		Handler: callbackHandler(state, results),
		// A half-open local connection (partial request, never completed)
		// must not be able to hold the listener open — without this, the
		// graceful Shutdown below would wait on it forever.
		ReadHeaderTimeout: 5 * time.Second,
	}
	go server.Serve(listener) //nolint:errcheck // Serve always returns non-nil on Shutdown
	// The listener must ALWAYS terminate when Login returns (plan M4 security
	// review): graceful shutdown gets a short deadline, then hard-close.
	defer func() {
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
		defer cancel()
		if err := server.Shutdown(shutdownCtx); err != nil {
			server.Close() //nolint:errcheck,gosec // force-close is the fallback
		}
	}()

	authorizeURL := f.oauthBaseURL() + "/oauth/authorize?" + url.Values{
		"response_type":         {"code"},
		"client_id":             {f.Config.ClientID},
		"redirect_uri":          {redirectURI},
		"scope":                 {oauthScopes},
		"state":                 {state},
		"code_challenge":        {challenge},
		"code_challenge_method": {"S256"},
	}.Encode()

	fmt.Fprintf(f.Output, "\nOpening your browser to sign in. If it doesn't open, visit:\n  %s\n\n", authorizeURL)
	if f.Browser != nil {
		if err := f.Browser.Open(authorizeURL); err != nil {
			// Non-fatal; user can open manually
			fmt.Fprintf(f.Output, "(Could not open browser automatically)\n")
		}
	}
	fmt.Fprintf(f.Output, "Waiting for authorization...\n")

	timeout := f.LoginTimeout
	if timeout == 0 {
		timeout = defaultLoginTimeout
	}

	select {
	case <-ctx.Done():
		return nil, fmt.Errorf("login cancelled")
	case <-time.After(timeout):
		return nil, fmt.Errorf(
			"timed out waiting for browser authorization; on a machine without a browser, create a token in the web app (Settings → API Tokens) and run: tiddly login --token <bm_...>")
	case result := <-results:
		if result.err != nil {
			return nil, result.err
		}
		return f.exchangeCode(result.code, verifier, redirectURI)
	}
}

// callbackHandler validates the redirect and hands the code to the flow. It
// responds to the browser BEFORE the token exchange runs so the user isn't
// staring at a hung tab during the exchange round-trip.
func callbackHandler(expectedState string, results chan<- callbackResult) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/callback" {
			http.NotFound(w, r)
			return
		}
		q := r.URL.Query()

		// State correlates EVERY callback shape — success AND error — with
		// this flow's own authorize request (RFC 6749 §4.1.2.1 requires error
		// redirects to echo state too). An uncorrelated request, from any
		// local process able to reach the loopback port, is answered 400 and
		// IGNORED — it must neither claim the one-slot result channel nor
		// abort a legitimate login still in flight (local-DoS hardening from
		// the M4 review).
		if q.Get("state") != expectedState {
			w.Header().Set("Content-Type", "text/html; charset=utf-8")
			w.WriteHeader(http.StatusBadRequest)
			fmt.Fprint(w, "<h3>Ignored an unexpected callback — continue signing in from your browser.</h3>")
			return
		}

		var result callbackResult
		switch {
		case q.Get("error") != "":
			desc := q.Get("error_description")
			if q.Get("error") == "access_denied" {
				result.err = fmt.Errorf("access denied: %s", desc)
			} else {
				result.err = fmt.Errorf("auth error: %s — %s", q.Get("error"), desc)
			}
		case q.Get("code") == "":
			result.err = errors.New("OAuth callback carried no authorization code")
		default:
			result.code = q.Get("code")
		}

		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		if result.err != nil {
			w.WriteHeader(http.StatusBadRequest)
			fmt.Fprint(w, "<h3>Sign-in failed — you can close this tab and return to the terminal.</h3>")
		} else {
			fmt.Fprint(w, "<h3>Signed in — you can close this tab and return to the terminal.</h3>")
		}

		// Non-blocking: the channel is buffered (1) and only the first
		// result matters; duplicate callbacks are dropped.
		select {
		case results <- result:
		default:
		}
	})
}

// exchangeCode trades the authorization code for tokens at /oauth/token.
func (f *PKCEFlow) exchangeCode(code, verifier, redirectURI string) (*TokenResponse, error) {
	body, err := f.postForm("/oauth/token", url.Values{
		"grant_type":    {"authorization_code"},
		"code":          {code},
		"redirect_uri":  {redirectURI},
		"client_id":     {f.Config.ClientID},
		"code_verifier": {verifier},
	})
	if err != nil {
		// invalid_grant here means the authorization code expired or was
		// already used (RFC 6749 §5.2) — NOT a dead session; the user may
		// never have had one.
		if errors.Is(err, errInvalidGrant) {
			return nil, errors.New("the sign-in attempt expired or was already used — run 'tiddly login' to try again")
		}
		return nil, fmt.Errorf("exchanging authorization code: %w", err)
	}

	var token TokenResponse
	if err := json.Unmarshal(body, &token); err != nil {
		return nil, fmt.Errorf("parsing token response: %w", err)
	}
	// A 200 with missing fields must fail HERE, at login, where the error is
	// visible and actionable — not later as baffling 401s from an empty
	// stored credential.
	if token.AccessToken == "" {
		return nil, errors.New("token endpoint returned no access token — run 'tiddly login' to try again")
	}
	// offline_access is always requested, so a missing refresh token means
	// the OAuth app is misconfigured — surface it at login, not as a failed
	// refresh 24 hours from now.
	if token.RefreshToken == "" {
		return nil, errors.New("token endpoint returned no refresh token (is the OAuth app missing the offline_access scope?)")
	}
	return &token, nil
}

// RefreshAccessToken uses a refresh token to get new access and refresh
// tokens. Clerk rotates refresh tokens (each refresh returns a new one), so
// both returned tokens must be stored.
func (f *PKCEFlow) RefreshAccessToken(refreshToken string) (*TokenResponse, error) {
	body, err := f.postForm("/oauth/token", url.Values{
		"grant_type":    {"refresh_token"},
		"refresh_token": {refreshToken},
		"client_id":     {f.Config.ClientID},
	})
	if err != nil {
		if errors.Is(err, errInvalidGrant) {
			return nil, errors.New("session expired. Run 'tiddly login' to re-authenticate")
		}
		return nil, err
	}

	var token TokenResponse
	if err := json.Unmarshal(body, &token); err != nil {
		return nil, fmt.Errorf("parsing refresh response: %w", err)
	}
	if token.AccessToken == "" {
		return nil, errors.New("token endpoint returned no access token — run 'tiddly login' to re-authenticate")
	}
	// Deliberately NO refresh-token requirement here: a refresh response
	// without a replacement token has standard OAuth semantics ("keep using
	// the current one"), and TokenManager preserves the stored token in that
	// case. Clerk has only ever been observed rotating, but treating that
	// observation as a contract would turn a legal provider behavior into a
	// hard failure (M4 review decision).
	return &token, nil
}

// postForm POSTs form data to an OAuth endpoint with the required headers
// and maps OAuth error responses to user-facing errors.
func (f *PKCEFlow) postForm(path string, data url.Values) ([]byte, error) {
	req, err := http.NewRequest(http.MethodPost, f.oauthBaseURL()+path, strings.NewReader(data.Encode()))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	ua := f.UserAgent
	if ua == "" {
		ua = defaultUserAgent
	}
	req.Header.Set("User-Agent", ua)

	resp, err := f.HTTPClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("token request failed: %w", err)
	}
	defer resp.Body.Close() //nolint:errcheck

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("reading token response: %w", err)
	}

	if resp.StatusCode == http.StatusOK {
		return body, nil
	}

	var errResp struct {
		Error            string `json:"error"`
		ErrorDescription string `json:"error_description"`
	}
	if json.Unmarshal(body, &errResp) == nil && errResp.Error != "" {
		if errResp.Error == "invalid_grant" {
			// Sentinel: the right user-facing message depends on the grant
			// type (dead session vs. expired sign-in attempt) — callers map it.
			return nil, fmt.Errorf("%w: %s", errInvalidGrant, errResp.ErrorDescription)
		}
		return nil, fmt.Errorf("auth error: %s — %s", errResp.Error, errResp.ErrorDescription)
	}
	return nil, fmt.Errorf("token request failed (%d): %s", resp.StatusCode, string(body))
}

// newPKCEPair generates a code_verifier (43-char base64url of 32 random
// bytes, 256 bits of entropy) and its S256 code_challenge.
func newPKCEPair() (verifier, challenge string, err error) {
	verifier, err = randomToken(32)
	if err != nil {
		return "", "", err
	}
	sum := sha256.Sum256([]byte(verifier))
	return verifier, base64.RawURLEncoding.EncodeToString(sum[:]), nil
}

// randomToken returns n crypto-random bytes as unpadded base64url.
func randomToken(n int) (string, error) {
	b := make([]byte, n)
	if _, err := rand.Read(b); err != nil {
		return "", err
	}
	return base64.RawURLEncoding.EncodeToString(b), nil
}
