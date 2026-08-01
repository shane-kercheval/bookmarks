package auth

import (
	"encoding/base64"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// mockStore is an in-memory CredentialStore for auth package tests.
// Cannot use testutil.MockCredStore here due to import cycle (testutil imports auth).
type mockStore struct {
	creds          map[string]string
	getErr         error // if non-nil, Get always returns this error
	setMultipleErr error // if non-nil, SetMultiple always returns this error
}

func newMockStore() *mockStore {
	return &mockStore{creds: make(map[string]string)}
}

func (m *mockStore) Get(account string) (string, error) {
	if m.getErr != nil {
		return "", m.getErr
	}
	val, ok := m.creds[account]
	if !ok {
		return "", ErrNotFound
	}
	return val, nil
}

func (m *mockStore) Set(account string, value string) error {
	m.creds[account] = value
	return nil
}

func (m *mockStore) SetMultiple(entries map[string]string) error {
	if m.setMultipleErr != nil {
		return m.setMultipleErr
	}
	for k, v := range entries {
		m.creds[k] = v
	}
	return nil
}

func (m *mockStore) Delete(account string) error {
	delete(m.creds, account)
	return nil
}

// makeJWT creates a minimal JWT for testing with the given expiry.
func makeJWT(exp time.Time) string {
	header := base64.RawURLEncoding.EncodeToString([]byte(`{"alg":"HS256"}`))
	claims := map[string]any{"exp": exp.Unix(), "sub": "test"}
	claimsJSON, _ := json.Marshal(claims)
	payload := base64.RawURLEncoding.EncodeToString(claimsJSON)
	sig := base64.RawURLEncoding.EncodeToString([]byte("fake-sig"))
	return fmt.Sprintf("%s.%s.%s", header, payload, sig)
}

func TestResolveToken(t *testing.T) {
	validJWT := makeJWT(time.Now().Add(1 * time.Hour))

	tests := []struct {
		name        string
		flagToken   string
		envToken    string
		storedPAT   string
		storedOAuth string
		preferOAuth bool
		wantToken   string
		wantType    string
		wantErr     string
	}{
		{
			name:      "flag takes precedence over everything",
			flagToken: "flag-token",
			storedPAT: "stored-pat",
			wantToken: "flag-token",
			wantType:  "flag",
		},
		{
			name:      "env var takes precedence over stored",
			envToken:  "env-token",
			storedPAT: "stored-pat",
			wantToken: "env-token",
			wantType:  "env",
		},
		{
			name:      "PAT resolved from store (default order)",
			storedPAT: "bm_test123",
			wantToken: "bm_test123",
			wantType:  "pat",
		},
		{
			name:        "OAuth resolved from store when no PAT",
			storedOAuth: validJWT,
			wantToken:   validJWT,
			wantType:    "oauth",
		},
		{
			name:        "default order prefers PAT over OAuth",
			storedPAT:   "bm_test123",
			storedOAuth: validJWT,
			wantToken:   "bm_test123",
			wantType:    "pat",
		},
		{
			name:        "preferOAuth prefers OAuth over PAT",
			storedPAT:   "bm_test123",
			storedOAuth: validJWT,
			preferOAuth: true,
			wantToken:   validJWT,
			wantType:    "oauth",
		},
		{
			name:        "preferOAuth falls back to PAT when no OAuth",
			storedPAT:   "bm_test123",
			preferOAuth: true,
			wantToken:   "bm_test123",
			wantType:    "pat",
		},
		{
			name:    "no credentials returns error",
			wantErr: "not logged in",
		},
		{
			name:      "flag token with whitespace is trimmed",
			flagToken: "  flag-token  ",
			wantToken: "flag-token",
			wantType:  "flag",
		},
		{
			name:      "flag token with embedded space rejected",
			flagToken: "bad token",
			wantErr:   "invalid token",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			store := newMockStore()
			if tt.storedPAT != "" {
				require.NoError(t, store.Set(AccountPAT, tt.storedPAT))
			}
			if tt.storedOAuth != "" {
				require.NoError(t, store.Set(AccountOAuthAccess, tt.storedOAuth))
			}

			if tt.envToken != "" {
				t.Setenv("TIDDLY_TOKEN", tt.envToken)
			} else {
				t.Setenv("TIDDLY_TOKEN", "")
			}

			tm := NewTokenManager(store, nil)
			result, err := tm.ResolveToken(tt.flagToken, tt.preferOAuth)

			if tt.wantErr != "" {
				require.Error(t, err)
				assert.Contains(t, err.Error(), tt.wantErr)
				return
			}

			require.NoError(t, err)
			assert.Equal(t, tt.wantToken, result.Token)
			assert.Equal(t, tt.wantType, result.AuthType)
		})
	}
}

func TestResolveToken__store_error_propagates(t *testing.T) {
	store := newMockStore()
	store.getErr = fmt.Errorf("credentials file corrupt")
	t.Setenv("TIDDLY_TOKEN", "")

	tm := NewTokenManager(store, nil)
	_, err := tm.ResolveToken("", false)

	require.Error(t, err)
	assert.Contains(t, err.Error(), "credentials file corrupt")
	assert.NotContains(t, err.Error(), "not logged in")
}

func TestResolveToken__expired_oauth_nil_flow(t *testing.T) {
	expiredJWT := makeJWT(time.Now().Add(-1 * time.Hour))
	t.Setenv("TIDDLY_TOKEN", "")

	store := newMockStore()
	require.NoError(t, store.Set(AccountOAuthAccess, expiredJWT))
	require.NoError(t, store.Set(AccountOAuthRefresh, "old-refresh-token"))

	tm := NewTokenManager(store, nil)
	_, err := tm.ResolveToken("", false)

	require.Error(t, err)
	assert.Contains(t, err.Error(), "session expired")
}

func TestResolveToken__expired_oauth_triggers_refresh(t *testing.T) {
	expiredJWT := makeJWT(time.Now().Add(-1 * time.Hour))
	newJWT := makeJWT(time.Now().Add(1 * time.Hour))

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		assert.Equal(t, "/oauth/token", r.URL.Path)
		assert.Equal(t, "refresh_token", r.FormValue("grant_type"))
		assert.Equal(t, "old-refresh-token", r.FormValue("refresh_token"))

		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]any{
			"access_token":  newJWT,
			"refresh_token": "new-refresh-token",
			"token_type":    "Bearer",
			"expires_in":    3600,
		})
	}))
	defer server.Close()

	store := newMockStore()
	require.NoError(t, store.Set(AccountOAuthAccess, expiredJWT))
	require.NoError(t, store.Set(AccountOAuthRefresh, "old-refresh-token"))

	flow := &PKCEFlow{
		Config:     OAuthConfig{ClientID: "test-client"},
		BaseURL:    server.URL,
		HTTPClient: &http.Client{},
	}
	tm := NewTokenManager(store, flow)
	t.Setenv("TIDDLY_TOKEN", "")

	result, err := tm.ResolveToken("", false)

	require.NoError(t, err)
	assert.Equal(t, newJWT, result.Token)
	assert.Equal(t, "oauth", result.AuthType)

	// Verify both new tokens were stored (refresh-token rotation)
	access, err := store.Get(AccountOAuthAccess)
	require.NoError(t, err)
	assert.Equal(t, newJWT, access)

	refresh, err := store.Get(AccountOAuthRefresh)
	require.NoError(t, err)
	assert.Equal(t, "new-refresh-token", refresh)
}

func TestResolveToken__refresh_failure_propagates(t *testing.T) {
	expiredJWT := makeJWT(time.Now().Add(-1 * time.Hour))

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusForbidden)
		_ = json.NewEncoder(w).Encode(map[string]any{
			"error":             "invalid_grant",
			"error_description": "token has been revoked",
		})
	}))
	defer server.Close()

	store := newMockStore()
	require.NoError(t, store.Set(AccountOAuthAccess, expiredJWT))
	require.NoError(t, store.Set(AccountOAuthRefresh, "revoked-token"))

	flow := &PKCEFlow{
		Config:     OAuthConfig{ClientID: "test-client"},
		BaseURL:    server.URL,
		HTTPClient: &http.Client{},
	}
	tm := NewTokenManager(store, flow)
	t.Setenv("TIDDLY_TOKEN", "")

	_, err := tm.ResolveToken("", false)

	require.Error(t, err)
	assert.Contains(t, err.Error(), "session expired")
}

func TestResolveToken__refresh_store_failure_returns_actionable_error(t *testing.T) {
	expiredJWT := makeJWT(time.Now().Add(-1 * time.Hour))
	newJWT := makeJWT(time.Now().Add(1 * time.Hour))

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]any{
			"access_token":  newJWT,
			"refresh_token": "new-refresh-token",
			"token_type":    "Bearer",
			"expires_in":    3600,
		})
	}))
	defer server.Close()

	store := newMockStore()
	require.NoError(t, store.Set(AccountOAuthAccess, expiredJWT))
	require.NoError(t, store.Set(AccountOAuthRefresh, "old-refresh-token"))
	store.setMultipleErr = fmt.Errorf("disk full")

	flow := &PKCEFlow{
		Config:     OAuthConfig{ClientID: "test-client"},
		BaseURL:    server.URL,
		HTTPClient: &http.Client{},
	}
	tm := NewTokenManager(store, flow)
	t.Setenv("TIDDLY_TOKEN", "")

	_, err := tm.ResolveToken("", false)

	require.Error(t, err)
	assert.Contains(t, err.Error(), "storing refreshed tokens")
	assert.Contains(t, err.Error(), "disk full")
}

func TestClearAll(t *testing.T) {
	store := newMockStore()
	require.NoError(t, store.Set(AccountOAuthAccess, "access"))
	require.NoError(t, store.Set(AccountOAuthRefresh, "refresh"))
	require.NoError(t, store.Set(AccountPAT, "pat"))

	tm := NewTokenManager(store, nil)
	err := tm.ClearAll()
	require.NoError(t, err)

	_, err = store.Get(AccountOAuthAccess)
	assert.ErrorIs(t, err, ErrNotFound)
	_, err = store.Get(AccountOAuthRefresh)
	assert.ErrorIs(t, err, ErrNotFound)
	_, err = store.Get(AccountPAT)
	assert.ErrorIs(t, err, ErrNotFound)
}

func TestValidatePATFormat(t *testing.T) {
	tests := []struct {
		name    string
		token   string
		wantErr bool
	}{
		{name: "valid PAT", token: "bm_abc123", wantErr: false},
		{name: "invalid prefix", token: "invalid_token", wantErr: true},
		{name: "empty", token: "", wantErr: true},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := ValidatePATFormat(tt.token)
			if tt.wantErr {
				assert.Error(t, err)
			} else {
				assert.NoError(t, err)
			}
		})
	}
}

func TestIsJWTExpired(t *testing.T) {
	tests := []struct {
		name    string
		token   string
		expired bool
	}{
		{
			name:    "valid non-expired JWT",
			token:   makeJWT(time.Now().Add(1 * time.Hour)),
			expired: false,
		},
		{
			name:    "expired JWT",
			token:   makeJWT(time.Now().Add(-1 * time.Hour)),
			expired: true,
		},
		{
			name:    "JWT expiring within 30s buffer",
			token:   makeJWT(time.Now().Add(10 * time.Second)),
			expired: true,
		},
		{
			name:    "non-JWT token returns false",
			token:   "not-a-jwt",
			expired: false,
		},
		{
			name:    "PAT returns false",
			token:   "bm_abc123",
			expired: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			assert.Equal(t, tt.expired, isJWTExpired(tt.token))
		})
	}
}

func TestCleanToken(t *testing.T) {
	tests := []struct {
		name     string
		input    string
		expected string
	}{
		{name: "no whitespace", input: "bm_test", expected: "bm_test"},
		{name: "leading space", input: "  bm_test", expected: "bm_test"},
		{name: "trailing newline", input: "bm_test\n", expected: "bm_test"},
		{name: "embedded space rejected", input: "bad token", expected: ""},
		{name: "embedded tab rejected", input: "bad\ttoken", expected: ""},
		{name: "only whitespace", input: "   ", expected: ""},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			assert.Equal(t, tt.expected, cleanToken(tt.input))
		})
	}
}
