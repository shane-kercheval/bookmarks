package mcp

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"testing"

	"github.com/shane-kercheval/tiddly/cli/internal/api"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestRunConfigure__oauth_creates_pats_with_unique_names(t *testing.T) {
	var createdNames []string
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch {
		case r.Method == "POST" && r.URL.Path == "/tokens/":
			var req api.TokenCreateRequest
			_ = json.NewDecoder(r.Body).Decode(&req)
			createdNames = append(createdNames, req.Name)
			w.WriteHeader(http.StatusCreated)
			_ = json.NewEncoder(w).Encode(api.TokenCreateResponse{
				ID:    "tok-new",
				Name:  req.Name,
				Token: "bm_created_" + req.Name,
			})
		case r.Method == "GET" && r.URL.Path == "/users/me":
			// No existing config means no existing PAT → validatePAT won't be called
			w.WriteHeader(404)
		default:
			w.WriteHeader(404)
		}
	}))
	defer server.Close()

	dir := t.TempDir()
	configPath := filepath.Join(dir, "claude_desktop_config.json")

	client := api.NewClient(server.URL, "oauth-jwt", "oauth")
	stdout := &bytes.Buffer{}

	tools := []DetectedTool{
		{Name: "claude-desktop", Detected: true, ConfigPath: configPath, HasNpx: true},
	}

	result, err := RunConfigure(ConfigureOpts{
		Handlers: DefaultHandlers(),
		Client:   client,
		AuthType: "oauth",
		Output:   stdout,
	}, tools)

	require.NoError(t, err)
	assert.Len(t, createdNames, 2, "should create 2 PATs")

	// Token names should match the pattern cli-mcp-{tool}-{server}-{6hex}
	namePattern := regexp.MustCompile(`^cli-mcp-claude-desktop-(content|prompts)-[0-9a-f]{6}$`)
	for _, name := range createdNames {
		assert.Regexp(t, namePattern, name)
	}

	assert.Len(t, result.TokensCreated, 2)
	assert.Contains(t, result.ToolsConfigured, "claude-desktop")
}

func TestRunConfigure__oauth_reuses_valid_existing_pat(t *testing.T) {
	var tokenCalls int
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch {
		case r.Method == "GET" && r.URL.Path == "/users/me":
			// Validate existing PAT — return 200 (valid)
			_ = json.NewEncoder(w).Encode(api.UserInfo{ID: "user-1", Email: "test@test.com"})
		case r.Method == "POST" && r.URL.Path == "/tokens/":
			tokenCalls++
			w.WriteHeader(http.StatusCreated)
			_ = json.NewEncoder(w).Encode(api.TokenCreateResponse{
				ID:    "tok-new",
				Token: "bm_new_token",
			})
		default:
			w.WriteHeader(404)
		}
	}))
	defer server.Close()

	dir := t.TempDir()
	configPath := filepath.Join(dir, "claude_desktop_config.json")

	// Write existing config with valid PATs
	existingConfig := map[string]any{
		"mcpServers": map[string]any{
			"tiddly_notes_bookmarks": map[string]any{
				"command": "npx",
				"args":    []string{"mcp-remote", "https://content-mcp.tiddly.me/mcp", "--header", "Authorization: Bearer bm_existing_content"},
			},
			"tiddly_prompts": map[string]any{
				"command": "npx",
				"args":    []string{"mcp-remote", "https://prompts-mcp.tiddly.me/mcp", "--header", "Authorization: Bearer bm_existing_prompt"},
			},
		},
	}
	writeTestJSON(t, configPath, existingConfig)

	client := api.NewClient(server.URL, "oauth-jwt", "oauth")
	stdout := &bytes.Buffer{}

	tools := []DetectedTool{
		{Name: "claude-desktop", Detected: true, ConfigPath: configPath, HasNpx: true},
	}

	result, err := RunConfigure(ConfigureOpts{
		Handlers: DefaultHandlers(),
		Client:   client,
		AuthType: "oauth",
		Output:   stdout,
	}, tools)

	require.NoError(t, err)
	assert.Equal(t, 0, tokenCalls, "should NOT create new tokens when existing PATs are valid")
	assert.Len(t, result.TokensReused, 2)
	assert.Empty(t, result.TokensCreated)
}

func TestRunConfigure__oauth_creates_new_pat_when_existing_invalid(t *testing.T) {
	var tokenCalls int
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch {
		case r.Method == "GET" && r.URL.Path == "/users/me":
			// Reject the existing PAT (401)
			w.WriteHeader(http.StatusUnauthorized)
			_ = json.NewEncoder(w).Encode(map[string]string{"detail": "Invalid token"})
		case r.Method == "POST" && r.URL.Path == "/tokens/":
			tokenCalls++
			var req api.TokenCreateRequest
			_ = json.NewDecoder(r.Body).Decode(&req)
			w.WriteHeader(http.StatusCreated)
			_ = json.NewEncoder(w).Encode(api.TokenCreateResponse{
				ID:    "tok-new",
				Name:  req.Name,
				Token: "bm_new_" + req.Name,
			})
		default:
			w.WriteHeader(404)
		}
	}))
	defer server.Close()

	dir := t.TempDir()
	configPath := filepath.Join(dir, "claude_desktop_config.json")

	// Write existing config with invalid PATs
	existingConfig := map[string]any{
		"mcpServers": map[string]any{
			"tiddly_notes_bookmarks": map[string]any{
				"command": "npx",
				"args":    []string{"mcp-remote", "https://content-mcp.tiddly.me/mcp", "--header", "Authorization: Bearer bm_expired_content"},
			},
			"tiddly_prompts": map[string]any{
				"command": "npx",
				"args":    []string{"mcp-remote", "https://prompts-mcp.tiddly.me/mcp", "--header", "Authorization: Bearer bm_expired_prompt"},
			},
		},
	}
	writeTestJSON(t, configPath, existingConfig)

	client := api.NewClient(server.URL, "oauth-jwt", "oauth")
	stdout := &bytes.Buffer{}

	tools := []DetectedTool{
		{Name: "claude-desktop", Detected: true, ConfigPath: configPath, HasNpx: true},
	}

	result, err := RunConfigure(ConfigureOpts{
		Handlers: DefaultHandlers(),
		Client:   client,
		AuthType: "oauth",
		Output:   stdout,
	}, tools)

	require.NoError(t, err)
	assert.Equal(t, 2, tokenCalls, "should create 2 new PATs when existing are invalid")
	assert.Len(t, result.TokensCreated, 2)
	assert.Empty(t, result.TokensReused)
}

func TestRunConfigure__pat_reuses_token(t *testing.T) {
	dir := t.TempDir()
	configPath := filepath.Join(dir, "claude_desktop_config.json")

	// No API calls needed for PAT auth (no token creation)
	client := api.NewClient("http://unused", "bm_existing", "pat")
	stdout := &bytes.Buffer{}
	stderr := &bytes.Buffer{}

	tools := []DetectedTool{
		{Name: "claude-desktop", Detected: true, ConfigPath: configPath, HasNpx: true},
	}

	result, err := RunConfigure(ConfigureOpts{
		Handlers: DefaultHandlers(),
		Client:    client,
		AuthType:  "pat",
		Output:    stdout,
		ErrOutput: stderr,
	}, tools)

	require.NoError(t, err)
	assert.Empty(t, result.TokensCreated, "should not create tokens")
	assert.Contains(t, result.Warnings[0], "current token")

	// Verify the config was written with the existing PAT
	config := readTestJSON(t, configPath)
	servers := config["mcpServers"].(map[string]any)
	content := servers["tiddly_notes_bookmarks"].(map[string]any)
	args := toStringSlice(content["args"])
	assert.Contains(t, args[3], "bm_existing")
}

func TestRunConfigure__dry_run_no_token_creation(t *testing.T) {
	var tokenCalls int
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch {
		case r.Method == "POST" && r.URL.Path == "/tokens/":
			tokenCalls++
			w.WriteHeader(http.StatusCreated)
			_ = json.NewEncoder(w).Encode(api.TokenCreateResponse{Token: "bm_new"})
		case r.Method == "GET" && r.URL.Path == "/users/me":
			w.WriteHeader(http.StatusUnauthorized)
		default:
			w.WriteHeader(404)
		}
	}))
	defer server.Close()

	dir := t.TempDir()
	configPath := filepath.Join(dir, "claude_desktop_config.json")

	client := api.NewClient(server.URL, "oauth-jwt", "oauth")
	stdout := &bytes.Buffer{}

	tools := []DetectedTool{
		{Name: "claude-desktop", Detected: true, ConfigPath: configPath, HasNpx: true},
	}

	result, err := RunConfigure(ConfigureOpts{
		Handlers: DefaultHandlers(),
		Client:   client,
		AuthType: "oauth",
		DryRun:   true,
		Output:   stdout,
	}, tools)

	require.NoError(t, err)
	assert.Equal(t, 0, tokenCalls, "dry-run should NOT create tokens")
	assert.Empty(t, result.ToolsConfigured,
		"dry-run writes nothing, so ToolsConfigured must stay empty")

	// Output should contain placeholder (JSON-escaped angle brackets)
	assert.Contains(t, stdout.String(), "new-token-would-be-created")

	// File should NOT exist
	_, err = os.Stat(configPath)
	assert.True(t, os.IsNotExist(err), "config file should not be created in dry-run")
}

func TestRunConfigure__dry_run_skips_pat_validation(t *testing.T) {
	// Dry-run should not make any network calls — not even PAT validation.
	// Use a server that fails on any request to prove this.
	var apiCalls int
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		apiCalls++
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer server.Close()

	dir := t.TempDir()
	configPath := filepath.Join(dir, ".claude.json")

	client := api.NewClient(server.URL, "oauth-jwt", "oauth")
	stdout := &bytes.Buffer{}

	tools := []DetectedTool{
		{Name: "claude-code", Detected: true, ConfigPath: configPath},
	}

	result, err := RunConfigure(ConfigureOpts{
		Handlers: DefaultHandlers(),
		Client:   client,
		AuthType: "oauth",
		DryRun:   true,
		Output:   stdout,
	}, tools)

	require.NoError(t, err)
	assert.Equal(t, 0, apiCalls, "dry-run should not make any API calls")
	assert.Empty(t, result.ToolsConfigured,
		"dry-run writes nothing, so ToolsConfigured must stay empty")
	assert.Contains(t, stdout.String(), "new-token-would-be-created")
}

func TestRunConfigure__dry_run_pat_auth_shows_diff(t *testing.T) {
	dir := t.TempDir()
	configPath := filepath.Join(dir, ".claude.json")

	client := api.NewClient("http://unused", "bm_test", "pat")
	stdout := &bytes.Buffer{}

	tools := []DetectedTool{
		{Name: "claude-code", Detected: true, ConfigPath: configPath},
	}

	_, err := RunConfigure(ConfigureOpts{
		Handlers: DefaultHandlers(),
		Client:   client,
		AuthType: "pat",
		DryRun:   true,
		Output:   stdout,
	}, tools)

	require.NoError(t, err)
	assert.Contains(t, stdout.String(), "tiddly_notes_bookmarks")
	// Dry-run output MUST redact Bearer values so tokens don't land in
	// terminal history. The raw PAT was "bm_test"; it must not appear.
	assert.NotContains(t, stdout.String(), "bm_test",
		"dry-run must not echo raw PAT values (security: tokens in terminal history)")
	assert.Contains(t, stdout.String(), "Bearer bm_REDACTED",
		"dry-run must replace Bearer values with Bearer bm_REDACTED")

	// File should NOT exist (dry run)
	_, statErr := os.Stat(configPath)
	assert.True(t, os.IsNotExist(statErr), "config file should not be created in dry-run")
}

func TestRunConfigure__servers_content_only(t *testing.T) {
	var createdNames []string
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch {
		case r.Method == "POST" && r.URL.Path == "/tokens/":
			var req api.TokenCreateRequest
			_ = json.NewDecoder(r.Body).Decode(&req)
			createdNames = append(createdNames, req.Name)
			w.WriteHeader(http.StatusCreated)
			_ = json.NewEncoder(w).Encode(api.TokenCreateResponse{
				ID:    "tok-new",
				Name:  req.Name,
				Token: "bm_created_" + req.Name,
			})
		case r.Method == "GET" && r.URL.Path == "/users/me":
			w.WriteHeader(404)
		default:
			w.WriteHeader(404)
		}
	}))
	defer server.Close()

	dir := t.TempDir()
	configPath := filepath.Join(dir, "claude_desktop_config.json")

	client := api.NewClient(server.URL, "oauth-jwt", "oauth")
	stdout := &bytes.Buffer{}

	tools := []DetectedTool{
		{Name: "claude-desktop", Detected: true, ConfigPath: configPath, HasNpx: true},
	}

	result, err := RunConfigure(ConfigureOpts{
		Handlers: DefaultHandlers(),
		Client:   client,
		AuthType: "oauth",
		Servers:  []string{"content"},
		Output:   stdout,
	}, tools)

	require.NoError(t, err)
	assert.Len(t, createdNames, 1, "should only create 1 PAT")
	assert.Contains(t, createdNames[0], "content")
	assert.Len(t, result.TokensCreated, 1)

	// Config should only have content server
	config := readTestJSON(t, configPath)
	servers := config["mcpServers"].(map[string]any)
	assert.Contains(t, servers, "tiddly_notes_bookmarks")
	assert.NotContains(t, servers, "tiddly_prompts")
}

func TestRunConfigure__servers_prompts_only(t *testing.T) {
	dir := t.TempDir()
	configPath := filepath.Join(dir, "claude_desktop_config.json")

	client := api.NewClient("http://unused", "bm_test", "pat")
	stdout := &bytes.Buffer{}

	tools := []DetectedTool{
		{Name: "claude-desktop", Detected: true, ConfigPath: configPath, HasNpx: true},
	}

	result, err := RunConfigure(ConfigureOpts{
		Handlers: DefaultHandlers(),
		Client:   client,
		AuthType: "pat",
		Servers:  []string{"prompts"},
		Output:   stdout,
	}, tools)

	require.NoError(t, err)
	assert.Contains(t, result.ToolsConfigured, "claude-desktop")

	config := readTestJSON(t, configPath)
	servers := config["mcpServers"].(map[string]any)
	assert.NotContains(t, servers, "tiddly_notes_bookmarks")
	assert.Contains(t, servers, "tiddly_prompts")
}

func TestRunConfigure__servers_content_only_preserves_existing_prompts(t *testing.T) {
	dir := t.TempDir()
	configPath := filepath.Join(dir, ".claude.json")

	// Pre-configure both servers
	rc := ResolvedConfig{Path: configPath, Scope: "user"}
	_, err := configureClaudeCode(rc, "bm_old_content", "bm_old_prompts")
	require.NoError(t, err)

	client := api.NewClient("http://unused", "bm_test", "pat")
	stdout := &bytes.Buffer{}

	tools := []DetectedTool{
		{Name: "claude-code", Detected: true, ConfigPath: configPath},
	}

	_, err = RunConfigure(ConfigureOpts{
		Handlers: DefaultHandlers(),
		Client:   client,
		AuthType: "pat",
		Servers:  []string{"content"},
		Output:   stdout,
	}, tools)

	require.NoError(t, err)

	config := readTestJSON(t, configPath)
	servers := config["mcpServers"].(map[string]any)

	// Content should be updated with the new PAT
	content := servers["tiddly_notes_bookmarks"].(map[string]any)
	headers := content["headers"].(map[string]any)
	assert.Equal(t, "Bearer bm_test", headers["Authorization"])

	// Prompts should be preserved from the original configure
	assert.Contains(t, servers, "tiddly_prompts", "prompts server should be preserved when --servers content")
	prompts := servers["tiddly_prompts"].(map[string]any)
	promptHeaders := prompts["headers"].(map[string]any)
	assert.Equal(t, "Bearer bm_old_prompts", promptHeaders["Authorization"])
}

func TestRunConfigure__servers_prompts_only_preserves_existing_content(t *testing.T) {
	dir := t.TempDir()
	configPath := filepath.Join(dir, ".claude.json")

	// Pre-configure both servers
	rc := ResolvedConfig{Path: configPath, Scope: "user"}
	_, err := configureClaudeCode(rc, "bm_old_content", "bm_old_prompts")
	require.NoError(t, err)

	client := api.NewClient("http://unused", "bm_test", "pat")
	stdout := &bytes.Buffer{}

	tools := []DetectedTool{
		{Name: "claude-code", Detected: true, ConfigPath: configPath},
	}

	_, err = RunConfigure(ConfigureOpts{
		Handlers: DefaultHandlers(),
		Client:   client,
		AuthType: "pat",
		Servers:  []string{"prompts"},
		Output:   stdout,
	}, tools)

	require.NoError(t, err)

	config := readTestJSON(t, configPath)
	servers := config["mcpServers"].(map[string]any)

	// Content should be preserved from the original configure
	assert.Contains(t, servers, "tiddly_notes_bookmarks", "content server should be preserved when --servers prompts")
	content := servers["tiddly_notes_bookmarks"].(map[string]any)
	headers := content["headers"].(map[string]any)
	assert.Equal(t, "Bearer bm_old_content", headers["Authorization"])

	// Prompts should be updated with the new PAT
	prompts := servers["tiddly_prompts"].(map[string]any)
	promptHeaders := prompts["headers"].(map[string]any)
	assert.Equal(t, "Bearer bm_test", promptHeaders["Authorization"])
}

func TestRunConfigure__skips_undetected_tools(t *testing.T) {
	client := api.NewClient("http://unused", "bm_test", "pat")
	stdout := &bytes.Buffer{}

	tools := []DetectedTool{
		{Name: "claude-desktop", Detected: false},
		{Name: "claude-code", Detected: false},
	}

	result, err := RunConfigure(ConfigureOpts{
		Handlers: DefaultHandlers(),
		Client:   client,
		AuthType: "pat",
		Output:   stdout,
	}, tools)

	require.NoError(t, err)
	assert.Empty(t, result.ToolsConfigured)
}

func TestRunConfigure__malformed_config_returns_parse_error(t *testing.T) {
	dir := t.TempDir()
	configPath := filepath.Join(dir, "claude_desktop_config.json")
	require.NoError(t, os.WriteFile(configPath, []byte("not json{"), 0644))

	client := api.NewClient("http://unused", "bm_test", "pat")
	stdout := &bytes.Buffer{}
	stderr := &bytes.Buffer{}

	tools := []DetectedTool{
		{Name: "claude-desktop", Detected: true, ConfigPath: configPath, HasNpx: true},
	}

	_, err := RunConfigure(ConfigureOpts{
		Handlers: DefaultHandlers(),
		Client:    client,
		AuthType:  "pat",
		Output:    stdout,
		ErrOutput: stderr,
	}, tools)

	require.Error(t, err)
	assert.Contains(t, err.Error(), "parsing")

	// Original file should be untouched
	data, readErr := os.ReadFile(configPath)
	require.NoError(t, readErr)
	assert.Equal(t, "not json{", string(data))
}

func TestRunConfigure__unsupported_scope_returns_error(t *testing.T) {
	client := api.NewClient("http://unused", "bm_test", "pat")
	stdout := &bytes.Buffer{}

	tools := []DetectedTool{
		{Name: "codex", Detected: true},
	}

	_, err := RunConfigure(ConfigureOpts{
		Handlers: DefaultHandlers(),
		Client:   client,
		AuthType: "pat",
		Scope:    "local",
		Output:   stdout,
	}, tools)

	require.Error(t, err)
	assert.Contains(t, err.Error(), "not supported by codex")
}

func TestCheckOrphanedTokens__finds_mcp_tokens_for_tool(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode([]api.TokenInfo{
			{ID: "tok-1", Name: "cli-mcp-claude-code-content-a1b2c3"},
			{ID: "tok-2", Name: "cli-mcp-claude-code-prompts-d4e5f6"},
			{ID: "tok-3", Name: "cli-mcp-codex-content-x1y2z3"},
			{ID: "tok-4", Name: "other-token"},
		})
	}))
	defer server.Close()

	client := api.NewClient(server.URL, "oauth-jwt", "oauth")

	// Should only return claude-code tokens (both server types)
	orphaned, err := CheckOrphanedTokens(context.Background(), client, "claude-code", []string{"content", "prompts"})
	require.NoError(t, err)
	assert.Len(t, orphaned, 2)
	assert.Contains(t, orphaned[0].Name, "cli-mcp-claude-code-")
	assert.Contains(t, orphaned[1].Name, "cli-mcp-claude-code-")

	// Should only return codex tokens
	orphaned, err = CheckOrphanedTokens(context.Background(), client, "codex", []string{"content", "prompts"})
	require.NoError(t, err)
	assert.Len(t, orphaned, 1)
	assert.Contains(t, orphaned[0].Name, "cli-mcp-codex-")
}

func TestCheckOrphanedTokens__no_orphans(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode([]api.TokenInfo{
			{ID: "tok-1", Name: "other-token"},
			{ID: "tok-2", Name: "cli-mcp-codex-content-a1b2c3"},
		})
	}))
	defer server.Close()

	client := api.NewClient(server.URL, "oauth-jwt", "oauth")
	orphaned, err := CheckOrphanedTokens(context.Background(), client, "claude-code", []string{"content", "prompts"})

	require.NoError(t, err)
	assert.Nil(t, orphaned)
}

func TestCheckOrphanedTokens__filters_by_server_type(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode([]api.TokenInfo{
			{ID: "tok-1", Name: "cli-mcp-claude-code-content-a1b2c3"},
			{ID: "tok-2", Name: "cli-mcp-claude-code-prompts-d4e5f6"},
		})
	}))
	defer server.Close()

	client := api.NewClient(server.URL, "oauth-jwt", "oauth")

	// Content only — should only find content token
	orphaned, err := CheckOrphanedTokens(context.Background(), client, "claude-code", []string{"content"})
	require.NoError(t, err)
	require.Len(t, orphaned, 1)
	assert.Contains(t, orphaned[0].Name, "content")

	// Prompts only — should only find prompts token
	orphaned, err = CheckOrphanedTokens(context.Background(), client, "claude-code", []string{"prompts"})
	require.NoError(t, err)
	require.Len(t, orphaned, 1)
	assert.Contains(t, orphaned[0].Name, "prompts")
}

func TestGenerateTokenName__format(t *testing.T) {
	name := generateTokenName("claude-code", "content")
	assert.Regexp(t, `^cli-mcp-claude-code-content-[0-9a-f]{6}$`, name)
}

func TestGenerateTokenName__unique(t *testing.T) {
	name1 := generateTokenName("claude-code", "content")
	name2 := generateTokenName("claude-code", "content")
	assert.NotEqual(t, name1, name2, "names should be unique due to random suffix")
}

func TestConfigureClaudeCode__both_pats_empty_preserves_existing(t *testing.T) {
	dir := t.TempDir()
	configPath := filepath.Join(dir, ".claude.json")

	// Configure both servers first
	rc := ResolvedConfig{Path: configPath, Scope: "user"}
	_, err := configureClaudeCode(rc, "bm_content", "bm_prompts")
	require.NoError(t, err)

	// Call with both PATs empty — should be a no-op for existing servers
	_, err = configureClaudeCode(rc, "", "")
	require.NoError(t, err)

	config := readTestJSON(t, configPath)
	servers := config["mcpServers"].(map[string]any)
	assert.Contains(t, servers, "tiddly_notes_bookmarks", "content should be preserved")
	assert.Contains(t, servers, "tiddly_prompts", "prompts should be preserved")
}

func TestValidatePAT__valid(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(api.UserInfo{ID: "user-1"})
	}))
	defer server.Close()

	valid, err := validatePAT(context.Background(), server.URL, "bm_valid")
	require.NoError(t, err)
	assert.True(t, valid)
}

func TestValidatePAT__invalid_401(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusUnauthorized)
	}))
	defer server.Close()

	valid, err := validatePAT(context.Background(), server.URL, "bm_expired")
	require.NoError(t, err)
	assert.False(t, valid)
}

func TestValidatePAT__server_error_returns_error(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer server.Close()

	valid, err := validatePAT(context.Background(), server.URL, "bm_test")
	assert.False(t, valid)
	require.Error(t, err)
	assert.Contains(t, err.Error(), "validating token")
}

func TestValidatePAT__network_error_returns_error(t *testing.T) {
	// Use a URL that will fail to connect
	valid, err := validatePAT(context.Background(), "http://127.0.0.1:1", "bm_test")
	assert.False(t, valid)
	require.Error(t, err)
	assert.Contains(t, err.Error(), "validating token")
}

func TestDeleteTokensByPrefix__matches_and_deletes(t *testing.T) {
	var deletedIDs []string
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch {
		case r.Method == "GET" && r.URL.Path == "/tokens/":
			// token_prefix is the first 12 chars of the PAT (bm_ + 9 chars)
			_ = json.NewEncoder(w).Encode([]api.TokenInfo{
				{ID: "tok-1", Name: "cli-mcp-claude-code-content-a1b2c3", TokenPrefix: "bm_abcdefghi"},
				{ID: "tok-2", Name: "cli-mcp-claude-code-prompts-d4e5f6", TokenPrefix: "bm_123456789"},
				{ID: "tok-3", Name: "other-token", TokenPrefix: "bm_xxxxxxxxx"},
			})
		case r.Method == "DELETE" && strings.HasPrefix(r.URL.Path, "/tokens/"):
			tokenID := strings.TrimPrefix(r.URL.Path, "/tokens/")
			deletedIDs = append(deletedIDs, tokenID)
			w.WriteHeader(http.StatusNoContent)
		default:
			w.WriteHeader(404)
		}
	}))
	defer server.Close()

	client := api.NewClient(server.URL, "oauth-jwt", "oauth")

	// PATs whose first 12 chars match the token_prefix
	reqs := []TokenRevokeRequest{
		{EntryLabel: "tiddly_notes_bookmarks", PAT: "bm_abcdefghijklmnop"},
		{EntryLabel: "tiddly_prompts", PAT: "bm_123456789jklmnop"},
	}
	results, err := DeleteTokensByPrefix(context.Background(), client, reqs)

	require.NoError(t, err)
	assert.Contains(t, deletedIDs, "tok-1")
	assert.Contains(t, deletedIDs, "tok-2")
	assert.NotContains(t, deletedIDs, "tok-3")
	require.Len(t, results, 2)
	assert.Equal(t, "tiddly_notes_bookmarks", results[0].EntryLabel)
	assert.Equal(t, []string{"cli-mcp-claude-code-content-a1b2c3"}, results[0].DeletedNames)
	assert.Equal(t, "tiddly_prompts", results[1].EntryLabel)
	assert.Equal(t, []string{"cli-mcp-claude-code-prompts-d4e5f6"}, results[1].DeletedNames)
}

func TestDeleteTokensByPrefix__partial_failure_returns_deleted_and_error(t *testing.T) {
	var deletedIDs []string
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch {
		case r.Method == "GET" && r.URL.Path == "/tokens/":
			_ = json.NewEncoder(w).Encode([]api.TokenInfo{
				{ID: "tok-1", Name: "cli-mcp-claude-code-content-a1b2c3", TokenPrefix: "bm_abcdefghi"},
				{ID: "tok-2", Name: "cli-mcp-claude-code-prompts-d4e5f6", TokenPrefix: "bm_123456789"},
			})
		case r.Method == "DELETE" && r.URL.Path == "/tokens/tok-1":
			deletedIDs = append(deletedIDs, "tok-1")
			w.WriteHeader(http.StatusNoContent)
		case r.Method == "DELETE" && r.URL.Path == "/tokens/tok-2":
			// Simulate failure for second token
			w.WriteHeader(http.StatusInternalServerError)
		default:
			w.WriteHeader(404)
		}
	}))
	defer server.Close()

	client := api.NewClient(server.URL, "oauth-jwt", "oauth")

	reqs := []TokenRevokeRequest{
		{EntryLabel: "tiddly_notes_bookmarks", PAT: "bm_abcdefghijklmnop"},
		{EntryLabel: "tiddly_prompts", PAT: "bm_123456789jklmnop"},
	}
	results, err := DeleteTokensByPrefix(context.Background(), client, reqs)

	// Top-level err is reserved for list-tokens failure, so no error here —
	// the per-request failure is on results[1].Err.
	require.NoError(t, err)
	require.Len(t, results, 2)
	assert.Equal(t, []string{"cli-mcp-claude-code-content-a1b2c3"}, results[0].DeletedNames)
	assert.NoError(t, results[0].Err)
	assert.Empty(t, results[1].DeletedNames)
	require.Error(t, results[1].Err)
	assert.Contains(t, results[1].Err.Error(), "cli-mcp-claude-code-prompts-d4e5f6")
}

func TestExtractPATs__claude_desktop_handler(t *testing.T) {
	dir := t.TempDir()
	configPath := filepath.Join(dir, "claude_desktop_config.json")

	config := map[string]any{
		"mcpServers": map[string]any{
			"tiddly_notes_bookmarks": map[string]any{
				"command": "npx",
				"args":    []string{"mcp-remote", "https://content-mcp.tiddly.me/mcp", "--header", "Authorization: Bearer bm_content123"},
			},
			"tiddly_prompts": map[string]any{
				"command": "npx",
				"args":    []string{"mcp-remote", "https://prompts-mcp.tiddly.me/mcp", "--header", "Authorization: Bearer bm_prompt456"},
			},
		},
	}
	writeTestJSON(t, configPath, config)

	h := &ClaudeDesktopHandler{}
	rc := ResolvedConfig{Path: configPath, Scope: "user"}
	ext := h.ExtractPATs(rc)
	assert.Equal(t, "bm_content123", ext.ContentPAT)
	assert.Equal(t, "bm_prompt456", ext.PromptPAT)
}

func TestExtractPATs__missing_config(t *testing.T) {
	h := &ClaudeDesktopHandler{}
	rc := ResolvedConfig{Path: "/nonexistent/path.json", Scope: "user"}
	ext := h.ExtractPATs(rc)
	assert.Empty(t, ext.ContentPAT)
	assert.Empty(t, ext.PromptPAT)
}

func TestConfigureTool__claude_code_project_scope_malformed_returns_error(t *testing.T) {
	cwd := t.TempDir()
	mcpPath := filepath.Join(cwd, ".mcp.json")

	// Write malformed .mcp.json
	require.NoError(t, os.WriteFile(mcpPath, []byte("not json{"), 0644))

	client := api.NewClient("http://unused", "bm_test", "pat")
	stdout := &bytes.Buffer{}
	stderr := &bytes.Buffer{}

	tools := []DetectedTool{
		{Name: "claude-code", Detected: true, ConfigPath: ""},
	}

	_, err := RunConfigure(ConfigureOpts{
		Handlers: DefaultHandlers(),
		Client:    client,
		AuthType:  "pat",
		Scope:     "project",
		Cwd:       cwd,
		Output:    stdout,
		ErrOutput: stderr,
	}, tools)

	require.Error(t, err)
	assert.Contains(t, err.Error(), "parsing")

	// Original malformed file should be untouched
	data, readErr := os.ReadFile(mcpPath)
	require.NoError(t, readErr)
	assert.Equal(t, "not json{", string(data))
}

func TestDryRunConfigure__claude_code_project_scope_shows_correct_path(t *testing.T) {
	// Regression: dryRunTool claude-code case showed tool.ResolvedConfigPath()
	// in diff output instead of the resolved project path.
	cwd := t.TempDir()
	client := api.NewClient("http://unused", "bm_test", "pat")
	stdout := &bytes.Buffer{}

	tools := []DetectedTool{
		{Name: "claude-code", Detected: true, ConfigPath: ""},
	}

	_, err := RunConfigure(ConfigureOpts{
		Handlers: DefaultHandlers(),
		Client:   client,
		AuthType: "pat",
		DryRun:   true,
		Scope:    "project",
		Cwd:      cwd,
		Output:   stdout,
	}, tools)

	require.NoError(t, err)
	output := stdout.String()
	// Should show the .mcp.json path, not ~/.claude.json
	assert.Contains(t, output, filepath.Join(cwd, ".mcp.json"))
}

func TestRunConfigure__valid_config_creates_backup_before_writing(t *testing.T) {
	dir := t.TempDir()
	configPath := filepath.Join(dir, "claude_desktop_config.json")

	// Write a valid existing config
	existingConfig := map[string]any{"existingKey": "existingValue"}
	writeTestJSON(t, configPath, existingConfig)

	client := api.NewClient("http://unused", "bm_test", "pat")
	stdout := &bytes.Buffer{}

	tools := []DetectedTool{
		{Name: "claude-desktop", Detected: true, ConfigPath: configPath, HasNpx: true},
	}

	result, err := RunConfigure(ConfigureOpts{
		Handlers: DefaultHandlers(),
		Client:   client,
		AuthType: "pat",
		Output:   stdout,
	}, tools)

	require.NoError(t, err)
	assert.Contains(t, result.ToolsConfigured, "claude-desktop")

	// Backup path should be surfaced in the result.
	require.Len(t, result.Backups, 1)
	assert.Equal(t, "claude-desktop", result.Backups[0].Tool)
	assert.True(t, strings.HasPrefix(result.Backups[0].Path, configPath+".bak."),
		"backup path should be <original>.bak.<timestamp>; got %q", result.Backups[0].Path)

	// Backup file should exist with the original content
	backupMatches, _ := filepath.Glob(configPath + ".bak.*")
	require.Len(t, backupMatches, 1, "exactly one timestamped backup should exist")
	backupData, backupErr := os.ReadFile(backupMatches[0])
	require.NoError(t, backupErr, "backup file should exist")
	assert.Contains(t, string(backupData), "existingKey")

	// New config should have our servers
	newData, err := os.ReadFile(configPath)
	require.NoError(t, err)
	assert.Contains(t, string(newData), "tiddly_notes_bookmarks")
}

func TestPrintDiff__redacts_bearer_across_all_three_formats(t *testing.T) {
	// Regression guard: mcp configure --dry-run must never echo plaintext
	// Bearer values. Covers all three config formats (claude-code JSON
	// with headers object, claude-desktop stdio args string, codex TOML
	// with quoted value). tokens create still shows plaintext by design
	// — that's an explicit token-display command; --dry-run is not.
	cases := []struct {
		name string
		in   string
	}{
		{
			name: "claude-code headers object",
			in:   `"headers": { "Authorization": "Bearer bm_live_token_aaa111" }`,
		},
		{
			name: "claude-desktop stdio args",
			in:   `"args": ["mcp-remote", "https://x/mcp", "--header", "Authorization: Bearer bm_live_token_bbb222"]`,
		},
		{
			name: "codex TOML http_headers",
			in:   `Authorization = "Bearer bm_live_token_ccc333"`,
		},
		{
			name: "multiple bearers in one blob",
			in:   "Bearer bm_first_token Bearer bm_second_token",
		},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			var buf bytes.Buffer
			printDiff(&buf, "/tmp/x", "", tc.in)
			out := buf.String()
			assert.NotRegexp(t, `Bearer bm_[a-z0-9_]+(?:$|")`, out,
				"raw Bearer value must not appear in dry-run output")
			assert.Contains(t, out, "Bearer bm_REDACTED",
				"every Bearer must be replaced with Bearer bm_REDACTED")
		})
	}
}

func TestRunConfigure__status_error_aborts_non_dry_run(t *testing.T) {
	// If Status fails in a non-dry-run, URL-mismatch detection is blind and
	// silently proceeding would bypass the fail-closed safety net. Preflight
	// must propagate the error and abort before any write.
	dir := t.TempDir()
	configPath := filepath.Join(dir, "not-a-valid-file.json")
	require.NoError(t, os.WriteFile(configPath, []byte("{{ not valid json"), 0600))

	client := api.NewClient("http://unused", "bm_test", "pat")
	stdout := &bytes.Buffer{}

	tools := []DetectedTool{
		{Name: "claude-code", Detected: true, ConfigPath: configPath},
	}

	_, err := RunConfigure(ConfigureOpts{
		Handlers: DefaultHandlers(),
		Client:   client,
		AuthType: "pat",
		Output:   stdout,
	}, tools)
	require.Error(t, err, "non-dry-run must fail closed on Status error")
	assert.Contains(t, err.Error(), "reading claude-code config for safety check")

	// Original (invalid) file must be preserved — no write happened.
	data, readErr := os.ReadFile(configPath)
	require.NoError(t, readErr)
	assert.Equal(t, "{{ not valid json", string(data))
}

func TestRunConfigure__commit_phase_failure_preserves_earlier_writes(t *testing.T) {
	// Two tools configured in one call. Tool-1 succeeds. Tool-2's parent
	// directory is read-only, so its write fails during phase 3 (commit).
	//
	// Contract under test: RunConfigure returns the failing tool's error,
	// but tool-1's filesystem state is NOT rolled back. A future regression
	// that "helpfully" restored tool-1 on tool-2 failure would lose the
	// user's successful work without telling them — this test prevents that.

	// Tool-1: ordinary temp dir. Configure will create .claude.json here.
	dir1 := t.TempDir()
	configPath1 := filepath.Join(dir1, ".claude.json")

	// Tool-2: pre-create the parent, then chmod it read-only so the
	// atomic-write temp-file create fails inside writeJSONConfig.
	dir2 := t.TempDir()
	readonly := filepath.Join(dir2, "readonly")
	require.NoError(t, os.Mkdir(readonly, 0700))
	configPath2 := filepath.Join(readonly, "claude_desktop_config.json")
	require.NoError(t, os.Chmod(readonly, 0500))
	t.Cleanup(func() {
		// Restore write bit so t.TempDir() cleanup can remove the directory.
		_ = os.Chmod(readonly, 0700)
	})

	client := api.NewClient("http://unused", "bm_test", "pat")
	stdout := &bytes.Buffer{}

	tools := []DetectedTool{
		{Name: "claude-code", Detected: true, ConfigPath: configPath1},
		{Name: "claude-desktop", Detected: true, ConfigPath: configPath2, HasNpx: true},
	}

	result, err := RunConfigure(ConfigureOpts{
		Handlers: DefaultHandlers(),
		Client:   client,
		AuthType: "pat",
		Output:   stdout,
	}, tools)

	require.Error(t, err)
	assert.Contains(t, err.Error(), "configuring claude-desktop",
		"error should identify the failing tool so the user knows where to look")

	// Partial result contract: RunConfigure returns the accumulated result
	// alongside the commit-phase error so the cmd layer can tell the user
	// what DID succeed. Declined/NeedsConfirmation errors return nil result
	// because nothing changed; this is the opposite — things changed.
	require.NotNil(t, result, "commit-phase failure must surface the partial result, not nil")
	assert.Equal(t, []string{"claude-code"}, result.ToolsConfigured,
		"tool-1 succeeded and must be listed; tool-2 must not")

	// Tool-1's write MUST persist — no rollback.
	config1 := readTestJSON(t, configPath1)
	servers1, ok := config1["mcpServers"].(map[string]any)
	require.True(t, ok, "tool-1's config file should exist and be valid JSON")
	assert.Contains(t, servers1, "tiddly_notes_bookmarks",
		"tool-1's successful write must survive tool-2's failure")

	// Tool-2's config must not exist — the write failed atomically.
	_, statErr := os.Stat(configPath2)
	assert.True(t, os.IsNotExist(statErr),
		"tool-2's config file should not exist after a failed write")
}

func TestRunConfigure__oauth_commit_failure_revokes_minted_tokens(t *testing.T) {
	// Under OAuth, phase 3 may mint new server-side tokens via CreateToken
	// before handler.Configure writes to disk. If the write fails, those
	// tokens are orphaned — present on the server, referenced by no config.
	// revokeMintedTokens cleans them up so the user's token list stays tidy.
	//
	// Setup: tool-1 has a writable config dir; tool-2's parent is 0500 so
	// the atomic write fails. Mock server accepts token creation (logs IDs)
	// and token deletion (logs IDs). Assert: exactly one DELETE call for
	// tool-2's token, zero for tool-1's.

	var (
		createdIDs []string
		deletedIDs []string
	)
	idCounter := 0
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch {
		case r.Method == "POST" && r.URL.Path == "/tokens/":
			idCounter++
			id := fmt.Sprintf("tok-%d", idCounter)
			createdIDs = append(createdIDs, id)
			var req api.TokenCreateRequest
			_ = json.NewDecoder(r.Body).Decode(&req)
			w.WriteHeader(http.StatusCreated)
			_ = json.NewEncoder(w).Encode(api.TokenCreateResponse{
				ID: id, Name: req.Name, Token: "bm_" + id,
			})
		case r.Method == "DELETE" && strings.HasPrefix(r.URL.Path, "/tokens/"):
			id := strings.TrimPrefix(r.URL.Path, "/tokens/")
			deletedIDs = append(deletedIDs, id)
			w.WriteHeader(http.StatusNoContent)
		default:
			// Any other call (e.g. /users/me validation) shouldn't happen —
			// there are no existing PATs in these configs, so both tools
			// go straight to the mint path.
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer server.Close()

	// Tool-1: writable temp dir.
	dir1 := t.TempDir()
	configPath1 := filepath.Join(dir1, ".claude.json")

	// Tool-2: read-only parent so Configure fails in phase 3.
	dir2 := t.TempDir()
	readonly := filepath.Join(dir2, "readonly")
	require.NoError(t, os.Mkdir(readonly, 0700))
	configPath2 := filepath.Join(readonly, "claude_desktop_config.json")
	require.NoError(t, os.Chmod(readonly, 0500))
	t.Cleanup(func() { _ = os.Chmod(readonly, 0700) })

	client := api.NewClient(server.URL, "oauth-jwt", "oauth")
	stdout := &bytes.Buffer{}

	tools := []DetectedTool{
		{Name: "claude-code", Detected: true, ConfigPath: configPath1},
		{Name: "claude-desktop", Detected: true, ConfigPath: configPath2, HasNpx: true},
	}

	result, err := RunConfigure(ConfigureOpts{
		Handlers: DefaultHandlers(),
		Client:   client,
		AuthType: "oauth",
		Output:   stdout,
	}, tools)

	require.Error(t, err)
	assert.Contains(t, err.Error(), "configuring claude-desktop")

	// Tool-1 minted 2 tokens (content + prompts), tool-2 attempted 2 before
	// Configure failed — so 4 tokens total were created server-side.
	assert.Len(t, createdIDs, 4, "expected 2 tokens per tool, 4 total")

	// Tool-2's 2 tokens must have been revoked. Tool-1's must NOT be
	// touched — they're legitimately in tool-1's written config.
	assert.Len(t, deletedIDs, 2, "exactly tool-2's minted tokens must be deleted")
	assert.ElementsMatch(t, []string{"tok-3", "tok-4"}, deletedIDs,
		"the deleted IDs must be the last two (tool-2's mints), not tool-1's")

	// result.TokensCreated reflects the surviving tokens only — tool-1's.
	require.NotNil(t, result)
	assert.Len(t, result.TokensCreated, 2,
		"only tool-1's tokens belong in TokensCreated; tool-2's were revoked")
}

func TestRevokeMintedTokens__cancelled_context_fails_every_delete(t *testing.T) {
	// Documents the primitive's contract: revokeMintedTokens honors
	// whatever context it's given. If the caller passes a cancelled
	// context, every DeleteToken call fails and orphans are reported —
	// which is exactly why RunConfigure passes a FRESH context (with
	// timeout), not opts.Ctx, at the two cleanup call sites. See
	// cleanupTimeout / the revokeMintedTokens call sites in configure.go.
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// A working endpoint — proves the failure is due to the cancelled
		// client context, not the server refusing.
		w.WriteHeader(http.StatusNoContent)
	}))
	defer server.Close()

	client := api.NewClient(server.URL, "oauth-jwt", "oauth")
	minted := []mintedToken{
		{ID: "tok-1", Name: "cli-mcp-x-content-abc123", Token: "bm_ends_in_1111"},
		{ID: "tok-2", Name: "cli-mcp-x-prompts-def456", Token: "bm_ends_in_2222"},
	}

	cancelled, cancel := context.WithCancel(context.Background())
	cancel()

	err := revokeMintedTokens(cancelled, client, minted)
	require.Error(t, err, "all deletes must fail under a cancelled context")
	assert.Contains(t, err.Error(), "cli-mcp-x-content-abc123")
	assert.Contains(t, err.Error(), "cli-mcp-x-prompts-def456")
}

func TestRevokeMintedTokens__fresh_context_revokes_cleanly(t *testing.T) {
	// Complement: with a live context, revoke succeeds and returns nil.
	// Proves the primitive does the work it's supposed to, so the only
	// reason production code would fail cleanup is passing a bad context.
	var deletedIDs []string
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method == "DELETE" && strings.HasPrefix(r.URL.Path, "/tokens/") {
			deletedIDs = append(deletedIDs, strings.TrimPrefix(r.URL.Path, "/tokens/"))
			w.WriteHeader(http.StatusNoContent)
			return
		}
		w.WriteHeader(http.StatusNotFound)
	}))
	defer server.Close()

	client := api.NewClient(server.URL, "oauth-jwt", "oauth")
	minted := []mintedToken{
		{ID: "tok-1", Name: "cli-mcp-x-content-abc", Token: "bm_x"},
		{ID: "tok-2", Name: "cli-mcp-x-prompts-def", Token: "bm_y"},
	}

	err := revokeMintedTokens(context.Background(), client, minted)
	require.NoError(t, err)
	assert.ElementsMatch(t, []string{"tok-1", "tok-2"}, deletedIDs)
}

func TestRunConfigure__oauth_commit_failure_with_revoke_failure_surfaces_orphans(t *testing.T) {
	// When both the Configure write AND the cleanup revoke fail, the error
	// message must name the orphaned tokens so the user can delete them
	// manually. "Something may be orphaned" isn't enough.

	var createdNames []string
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch {
		case r.Method == "POST" && r.URL.Path == "/tokens/":
			var req api.TokenCreateRequest
			_ = json.NewDecoder(r.Body).Decode(&req)
			createdNames = append(createdNames, req.Name)
			w.WriteHeader(http.StatusCreated)
			_ = json.NewEncoder(w).Encode(api.TokenCreateResponse{
				ID: "tok-" + req.Name, Name: req.Name, Token: "bm_prefix1234_rest_of_token",
			})
		case r.Method == "DELETE" && strings.HasPrefix(r.URL.Path, "/tokens/"):
			// Simulate revoke failure so the orphan-naming path fires.
			w.WriteHeader(http.StatusInternalServerError)
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer server.Close()

	dir := t.TempDir()
	readonly := filepath.Join(dir, "readonly")
	require.NoError(t, os.Mkdir(readonly, 0700))
	configPath := filepath.Join(readonly, "claude_desktop_config.json")
	require.NoError(t, os.Chmod(readonly, 0500))
	t.Cleanup(func() { _ = os.Chmod(readonly, 0700) })

	client := api.NewClient(server.URL, "oauth-jwt", "oauth")
	stdout := &bytes.Buffer{}

	tools := []DetectedTool{
		{Name: "claude-desktop", Detected: true, ConfigPath: configPath, HasNpx: true},
	}

	_, err := RunConfigure(ConfigureOpts{
		Handlers: DefaultHandlers(),
		Client:   client,
		AuthType: "oauth",
		Output:   stdout,
	}, tools)

	require.Error(t, err)
	msg := err.Error()
	assert.Contains(t, msg, "cleanup partially failed")
	// Each minted token name should appear so the user can find it.
	require.Len(t, createdNames, 2)
	for _, name := range createdNames {
		assert.Contains(t, msg, name,
			"orphan token name must appear in the error for manual cleanup")
	}
	// First-12 TokenPrefix matches what the settings UI shows, so the
	// user can correlate this error with the row to delete manually.
	assert.Contains(t, msg, "bm_prefix123",
		"orphan token first-12 prefix (matching settings UI) must appear in the error")
	assert.NotContains(t, msg, "...",
		"old last-4 ellipsis format must not reappear")
}

func TestRunConfigure__commit_phase_failure_surfaces_backup_path(t *testing.T) {
	// Regression guard for the backup-path-on-failure drop: when the
	// write fails, the backup was already taken before the attempt, so
	// the recovery copy IS on disk — callers must see it in result.Backups
	// so they can tell the user where to find it. Before this fix,
	// writeJSONConfig returned ("", err) on write failure, losing the
	// single most useful piece of information to the user.
	//
	// Reliably separating "backup succeeds" from "write fails" via
	// filesystem permissions isn't feasible because both ops share the
	// same parent dir. Instead, inject a failing atomic-write so the
	// timing we need to test — backup-then-write — is deterministic.
	prev := atomicWriteFileFunc
	atomicWriteFileFunc = func(path string, data []byte, defaultPerm os.FileMode) error {
		return fmt.Errorf("simulated write failure")
	}
	t.Cleanup(func() { atomicWriteFileFunc = prev })

	dir := t.TempDir()
	configPath := filepath.Join(dir, "claude_desktop_config.json")
	require.NoError(t, os.WriteFile(configPath, []byte(`{"mcpServers":{}}`), 0600))

	client := api.NewClient("http://unused", "bm_test", "pat")
	stdout := &bytes.Buffer{}

	tools := []DetectedTool{
		{Name: "claude-desktop", Detected: true, ConfigPath: configPath, HasNpx: true},
	}

	result, err := RunConfigure(ConfigureOpts{
		Handlers: DefaultHandlers(),
		Client:   client,
		AuthType: "pat",
		Output:   stdout,
	}, tools)

	require.Error(t, err)
	assert.Contains(t, err.Error(), "simulated write failure")
	require.NotNil(t, result)
	require.Len(t, result.Backups, 1,
		"backup must be recorded even when the write fails — the recovery artifact is already on disk")
	assert.Equal(t, "claude-desktop", result.Backups[0].Tool)
	assert.True(t, strings.HasPrefix(result.Backups[0].Path, configPath+".bak."),
		"backup path must point at the timestamped copy taken before the failed write; got %q",
		result.Backups[0].Path)

	// The backup file really exists on disk — this isn't just a stale record.
	data, statErr := os.ReadFile(result.Backups[0].Path)
	require.NoError(t, statErr, "recorded backup path must point at a real file")
	assert.Equal(t, `{"mcpServers":{}}`, string(data),
		"backup must contain the pre-write original contents")
}

func TestRunConfigure__preflight_failure_returns_nil_result(t *testing.T) {
	// The complement of the partial-result contract: preflight errors
	// (Status read failure on a malformed file, etc.) must return nil
	// because nothing has been written or minted. A non-nil result here
	// would trick the cmd layer into printing a bogus "Configured: ..."
	// summary for tools that never actually got touched.
	dir := t.TempDir()
	configPath := filepath.Join(dir, ".claude.json")
	require.NoError(t, os.WriteFile(configPath, []byte("not valid json{"), 0600))

	client := api.NewClient("http://unused", "bm_test", "pat")
	stdout := &bytes.Buffer{}

	tools := []DetectedTool{
		{Name: "claude-code", Detected: true, ConfigPath: configPath},
	}

	result, err := RunConfigure(ConfigureOpts{
		Handlers: DefaultHandlers(),
		Client:   client,
		AuthType: "pat",
		Output:   stdout,
	}, tools)

	require.Error(t, err)
	assert.Nil(t, result, "preflight failure must return nil result — nothing happened")
}

func TestRunRemove__valid_config_creates_backup_before_writing(t *testing.T) {
	dir := t.TempDir()
	configPath := filepath.Join(dir, "claude_desktop_config.json")

	// Write a valid existing config with tiddly servers
	existingConfig := map[string]any{
		"mcpServers": map[string]any{
			"tiddly_notes_bookmarks": map[string]any{
				"command": "npx",
				"args":    []string{"mcp-remote", "https://content-mcp.tiddly.me/mcp", "--header", "Authorization: Bearer bm_test"},
			},
		},
	}
	writeTestJSON(t, configPath, existingConfig)

	h := &ClaudeDesktopHandler{}
	result, err := h.Remove(ResolvedConfig{Path: configPath, Scope: "user"}, []string{"content", "prompts"})
	require.NoError(t, err)
	require.NotNil(t, result)
	assert.Equal(t, []string{"tiddly_notes_bookmarks"}, result.RemovedEntries,
		"RemovedEntries must list the canonical names actually deleted")
	require.NotEmpty(t, result.BackupPath, "Remove should return backup path when a write occurred")
	assert.True(t, strings.HasPrefix(result.BackupPath, configPath+".bak."),
		"backup filename should be <path>.bak.<timestamp>; got %q", result.BackupPath)

	// Backup file should exist with the original content (including the tiddly server)
	backupData, backupErr := os.ReadFile(result.BackupPath)
	require.NoError(t, backupErr, "backup file should exist")
	assert.Contains(t, string(backupData), "tiddly_notes_bookmarks")
}

func TestRunConfigure__no_existing_file_does_not_create_backup(t *testing.T) {
	dir := t.TempDir()
	configPath := filepath.Join(dir, "claude_desktop_config.json")

	client := api.NewClient("http://unused", "bm_test", "pat")
	stdout := &bytes.Buffer{}

	tools := []DetectedTool{
		{Name: "claude-desktop", Detected: true, ConfigPath: configPath, HasNpx: true},
	}

	result, err := RunConfigure(ConfigureOpts{
		Handlers: DefaultHandlers(),
		Client:   client,
		AuthType: "pat",
		Output:   stdout,
	}, tools)

	require.NoError(t, err)
	assert.Contains(t, result.ToolsConfigured, "claude-desktop")

	// No backup should be produced when no original file existed.
	assert.Empty(t, result.Backups, "no backup record should be surfaced when there was no prior config")
	backupMatches, _ := filepath.Glob(configPath + ".bak.*")
	assert.Empty(t, backupMatches, "backup should not be created when no original file exists")

	// Config should have been created
	newData, err := os.ReadFile(configPath)
	require.NoError(t, err)
	assert.Contains(t, string(newData), "tiddly_notes_bookmarks")
}

// ---------------------------------------------------------------------------
// Additive-configure tests — URL-mismatch detection, --force, preserved
// entries. Exhaustively covers the preflight and commit paths introduced when
// the consolidation gate was removed.
// ---------------------------------------------------------------------------

func TestRunConfigure__additive_preserves_non_canonical_tiddly_entries(t *testing.T) {
	// User configured work_prompts + personal_prompts manually; configure
	// must add the canonical entries WITHOUT touching those non-canonical
	// ones (no consolidation).
	dir := t.TempDir()
	configPath := filepath.Join(dir, ".claude.json")

	writeTestJSON(t, configPath, map[string]any{
		"mcpServers": map[string]any{
			"work_prompts": map[string]any{
				"type":    "http",
				"url":     PromptMCPURL(),
				"headers": map[string]any{"Authorization": "Bearer bm_work"},
			},
			"personal_prompts": map[string]any{
				"type":    "http",
				"url":     PromptMCPURL(),
				"headers": map[string]any{"Authorization": "Bearer bm_personal"},
			},
		},
	})

	client := api.NewClient("http://unused", "bm_login", "pat")
	stdout := &bytes.Buffer{}
	tools := []DetectedTool{{Name: "claude-code", Detected: true, ConfigPath: configPath}}

	result, err := RunConfigure(ConfigureOpts{
		Handlers: DefaultHandlers(), Client: client, AuthType: "pat", Output: stdout,
	}, tools)
	require.NoError(t, err)
	assert.Contains(t, result.ToolsConfigured, "claude-code")

	config := readTestJSON(t, configPath)
	servers := config["mcpServers"].(map[string]any)
	assert.Contains(t, servers, "work_prompts", "non-canonical entry must survive")
	assert.Contains(t, servers, "personal_prompts", "non-canonical entry must survive")
	assert.Contains(t, servers, "tiddly_prompts", "canonical prompts entry must be written")
}

func TestRunConfigure__does_not_reuse_pat_from_non_canonical_entry(t *testing.T) {
	// OAuth: no canonical entry exists, only non-canonical ones. ExtractPATs
	// must NOT harvest work_prompts' PAT for tiddly_prompts — configure
	// should mint a fresh token.
	var mintedCount int
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch {
		case r.Method == "POST" && r.URL.Path == "/tokens/":
			mintedCount++
			var req api.TokenCreateRequest
			_ = json.NewDecoder(r.Body).Decode(&req)
			w.WriteHeader(http.StatusCreated)
			_ = json.NewEncoder(w).Encode(api.TokenCreateResponse{ID: "tok-new", Name: req.Name, Token: "bm_new"})
		default:
			w.WriteHeader(404)
		}
	}))
	defer server.Close()

	dir := t.TempDir()
	configPath := filepath.Join(dir, ".claude.json")
	writeTestJSON(t, configPath, map[string]any{
		"mcpServers": map[string]any{
			"work_prompts": map[string]any{
				"type":    "http",
				"url":     PromptMCPURL(),
				"headers": map[string]any{"Authorization": "Bearer bm_work_prompt"},
			},
		},
	})

	client := api.NewClient(server.URL, "oauth-jwt", "oauth")
	stdout := &bytes.Buffer{}
	tools := []DetectedTool{{Name: "claude-code", Detected: true, ConfigPath: configPath}}

	_, err := RunConfigure(ConfigureOpts{
		Handlers: DefaultHandlers(), Client: client, AuthType: "oauth",
		Servers: []string{ServerPrompts}, Output: stdout,
	}, tools)
	require.NoError(t, err)
	assert.Equal(t, 1, mintedCount, "must mint a fresh token — non-canonical PAT is not reused")
}

func TestRunConfigure__refuses_overwrite_when_managed_key_has_non_tiddly_url(t *testing.T) {
	// The CLI-managed key tiddly_prompts points at a non-Tiddly URL (user
	// hand-edit). Configure must fail closed, mint nothing, write nothing.
	var tokenCalls int
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		tokenCalls++
		w.WriteHeader(500)
	}))
	defer server.Close()

	dir := t.TempDir()
	configPath := filepath.Join(dir, ".claude.json")
	original := map[string]any{
		"mcpServers": map[string]any{
			serverNamePrompts: map[string]any{
				"type":    "http",
				"url":     "https://example.com/my-prompts",
				"headers": map[string]any{"Authorization": "Bearer bm_custom"},
			},
		},
	}
	writeTestJSON(t, configPath, original)

	client := api.NewClient(server.URL, "oauth-jwt", "oauth")
	stdout, stderr := &bytes.Buffer{}, &bytes.Buffer{}
	tools := []DetectedTool{{Name: "claude-code", Detected: true, ConfigPath: configPath}}

	_, err := RunConfigure(ConfigureOpts{
		Handlers: DefaultHandlers(), Client: client, AuthType: "oauth",
		Output: stdout, ErrOutput: stderr,
	}, tools)
	require.Error(t, err)
	assert.Contains(t, err.Error(), "CLI-managed")
	assert.Contains(t, err.Error(), "unexpected URL")
	assert.Contains(t, err.Error(), "--force")
	assert.NotContains(t, err.Error(), "canonical",
		"user-facing error must NOT use the word 'canonical'")
	assert.Equal(t, 0, tokenCalls, "no API calls should happen when preflight fails closed")

	// Config file must be unchanged.
	after := readTestJSON(t, configPath)
	assert.Equal(t, original["mcpServers"], after["mcpServers"])
}

func TestRunConfigure__refuses_when_canonical_name_has_wrong_type_tiddly_url(t *testing.T) {
	// tiddly_prompts points at the CONTENT Tiddly URL (cross-wired). Same
	// fail-closed behavior and same error template as the non-Tiddly URL case.
	dir := t.TempDir()
	configPath := filepath.Join(dir, ".claude.json")
	writeTestJSON(t, configPath, map[string]any{
		"mcpServers": map[string]any{
			serverNamePrompts: map[string]any{
				"type":    "http",
				"url":     ContentMCPURL(),
				"headers": map[string]any{"Authorization": "Bearer bm_wrong"},
			},
		},
	})

	client := api.NewClient("http://unused", "bm_login", "pat")
	stdout := &bytes.Buffer{}
	tools := []DetectedTool{{Name: "claude-code", Detected: true, ConfigPath: configPath}}

	_, err := RunConfigure(ConfigureOpts{
		Handlers: DefaultHandlers(), Client: client, AuthType: "pat", Output: stdout,
	}, tools)
	require.Error(t, err)
	assert.Contains(t, err.Error(), serverNamePrompts)
	assert.Contains(t, err.Error(), ContentMCPURL())
	assert.Contains(t, err.Error(), "--force")
}

func TestRunConfigure__does_not_refuse_on_out_of_scope_mismatch(t *testing.T) {
	// tiddly_prompts has a non-Tiddly URL, but --servers content scopes
	// the run to the content slot. Mismatch is out of scope → ignored.
	dir := t.TempDir()
	configPath := filepath.Join(dir, ".claude.json")
	writeTestJSON(t, configPath, map[string]any{
		"mcpServers": map[string]any{
			serverNamePrompts: map[string]any{
				"type":    "http",
				"url":     "https://example.com/my-prompts",
				"headers": map[string]any{"Authorization": "Bearer bm_custom"},
			},
		},
	})

	client := api.NewClient("http://unused", "bm_login", "pat")
	stdout := &bytes.Buffer{}
	tools := []DetectedTool{{Name: "claude-code", Detected: true, ConfigPath: configPath}}

	result, err := RunConfigure(ConfigureOpts{
		Handlers: DefaultHandlers(), Client: client, AuthType: "pat",
		Servers: []string{ServerContent}, Output: stdout,
	}, tools)
	require.NoError(t, err, "out-of-scope mismatch must not block configure")
	assert.Contains(t, result.ToolsConfigured, "claude-code")

	// Prompts slot must still have the user's custom URL (untouched).
	after := readTestJSON(t, configPath)
	servers := after["mcpServers"].(map[string]any)
	prompts := servers[serverNamePrompts].(map[string]any)
	assert.Equal(t, "https://example.com/my-prompts", prompts["url"])
}

func TestRunConfigure__servers_scope_refuses_only_on_in_scope_mismatch(t *testing.T) {
	// BOTH canonicals have URL mismatches, but --servers content scopes to
	// content. The error must mention content but NOT prompts.
	dir := t.TempDir()
	configPath := filepath.Join(dir, ".claude.json")
	writeTestJSON(t, configPath, map[string]any{
		"mcpServers": map[string]any{
			serverNameContent: map[string]any{
				"type": "http", "url": "http://localhost:8001/mcp",
				"headers": map[string]any{"Authorization": "Bearer bm_a"},
			},
			serverNamePrompts: map[string]any{
				"type": "http", "url": "https://example.com/my-prompts",
				"headers": map[string]any{"Authorization": "Bearer bm_b"},
			},
		},
	})

	client := api.NewClient("http://unused", "bm_login", "pat")
	stdout := &bytes.Buffer{}
	tools := []DetectedTool{{Name: "claude-code", Detected: true, ConfigPath: configPath}}

	_, err := RunConfigure(ConfigureOpts{
		Handlers: DefaultHandlers(), Client: client, AuthType: "pat",
		Servers: []string{ServerContent}, Output: stdout,
	}, tools)
	require.Error(t, err)
	assert.Contains(t, err.Error(), serverNameContent)
	assert.NotContains(t, err.Error(), serverNamePrompts,
		"out-of-scope mismatched slot must not appear in the error")
}

func TestRunConfigure__error_format_single_tool_one_mismatch(t *testing.T) {
	dir := t.TempDir()
	configPath := filepath.Join(dir, ".claude.json")
	writeTestJSON(t, configPath, map[string]any{
		"mcpServers": map[string]any{
			serverNamePrompts: map[string]any{
				"type": "http", "url": "https://example.com/my-prompts",
				"headers": map[string]any{"Authorization": "Bearer bm_x"},
			},
		},
	})

	client := api.NewClient("http://unused", "bm_login", "pat")
	tools := []DetectedTool{{Name: "claude-code", Detected: true, ConfigPath: configPath}}

	_, err := RunConfigure(ConfigureOpts{
		Handlers: DefaultHandlers(), Client: client, AuthType: "pat",
	}, tools)
	require.Error(t, err)
	msg := err.Error()
	assert.Contains(t, msg, "1 CLI-managed entry")
	assert.Contains(t, msg, "has an unexpected URL")
	assert.Contains(t, msg, "Preserve it")
	assert.Contains(t, msg, "Replace it")
}

func TestRunConfigure__error_format_single_tool_multiple_mismatches(t *testing.T) {
	dir := t.TempDir()
	configPath := filepath.Join(dir, ".claude.json")
	writeTestJSON(t, configPath, map[string]any{
		"mcpServers": map[string]any{
			serverNameContent: map[string]any{
				"type": "http", "url": "http://localhost:8001/mcp",
				"headers": map[string]any{"Authorization": "Bearer bm_a"},
			},
			serverNamePrompts: map[string]any{
				"type": "http", "url": "https://example.com/my-prompts",
				"headers": map[string]any{"Authorization": "Bearer bm_b"},
			},
		},
	})

	client := api.NewClient("http://unused", "bm_login", "pat")
	tools := []DetectedTool{{Name: "claude-code", Detected: true, ConfigPath: configPath}}

	_, err := RunConfigure(ConfigureOpts{
		Handlers: DefaultHandlers(), Client: client, AuthType: "pat",
	}, tools)
	require.Error(t, err)
	msg := err.Error()
	assert.Contains(t, msg, "2 CLI-managed entries")
	assert.Contains(t, msg, "have an unexpected URL")
	assert.Contains(t, msg, "Preserve them")
	assert.Contains(t, msg, "Replace them")
}

func TestRunConfigure__error_format_uses_CLI_managed_wording(t *testing.T) {
	dir := t.TempDir()
	configPath := filepath.Join(dir, ".claude.json")
	writeTestJSON(t, configPath, map[string]any{
		"mcpServers": map[string]any{
			serverNamePrompts: map[string]any{
				"type": "http", "url": "https://example.com/my-prompts",
				"headers": map[string]any{"Authorization": "Bearer bm_x"},
			},
		},
	})

	client := api.NewClient("http://unused", "bm_login", "pat")
	tools := []DetectedTool{{Name: "claude-code", Detected: true, ConfigPath: configPath}}

	_, err := RunConfigure(ConfigureOpts{
		Handlers: DefaultHandlers(), Client: client, AuthType: "pat",
	}, tools)
	require.Error(t, err)
	assert.NotContains(t, strings.ToLower(err.Error()), "canonical",
		"user-facing error copy must not use 'canonical'")
}

func TestRunConfigure__dry_run_warns_on_mismatch_but_shows_diff(t *testing.T) {
	dir := t.TempDir()
	configPath := filepath.Join(dir, ".claude.json")
	writeTestJSON(t, configPath, map[string]any{
		"mcpServers": map[string]any{
			serverNamePrompts: map[string]any{
				"type": "http", "url": "https://example.com/my-prompts",
				"headers": map[string]any{"Authorization": "Bearer bm_x"},
			},
		},
	})

	client := api.NewClient("http://unused", "bm_login", "pat")
	stdout, stderr := &bytes.Buffer{}, &bytes.Buffer{}
	tools := []DetectedTool{{Name: "claude-code", Detected: true, ConfigPath: configPath}}

	_, err := RunConfigure(ConfigureOpts{
		Handlers: DefaultHandlers(), Client: client, AuthType: "pat",
		DryRun: true, Output: stdout, ErrOutput: stderr,
	}, tools)
	require.NoError(t, err, "dry-run must not abort on mismatch")
	assert.Contains(t, stderr.String(), "Warning")
	assert.Contains(t, stderr.String(), serverNamePrompts)
	assert.Contains(t, stderr.String(), "--force")
	assert.Contains(t, stdout.String(), "claude-code")
	assert.Contains(t, stdout.String(), "Before")
}

func TestRunConfigure__force_with_dry_run_shows_overwrite_without_warning(t *testing.T) {
	dir := t.TempDir()
	configPath := filepath.Join(dir, ".claude.json")
	writeTestJSON(t, configPath, map[string]any{
		"mcpServers": map[string]any{
			serverNamePrompts: map[string]any{
				"type": "http", "url": "https://example.com/my-prompts",
				"headers": map[string]any{"Authorization": "Bearer bm_x"},
			},
		},
	})

	client := api.NewClient("http://unused", "bm_login", "pat")
	stdout, stderr := &bytes.Buffer{}, &bytes.Buffer{}
	tools := []DetectedTool{{Name: "claude-code", Detected: true, ConfigPath: configPath}}

	_, err := RunConfigure(ConfigureOpts{
		Handlers: DefaultHandlers(), Client: client, AuthType: "pat",
		DryRun: true, Force: true, Output: stdout, ErrOutput: stderr,
	}, tools)
	require.NoError(t, err)
	assert.NotContains(t, stderr.String(), "real run will require",
		"--force suppresses the per-entry warning under dry-run")
	// Non-dry-run-only log must NOT appear under dry-run.
	assert.NotContains(t, stderr.String(), "Forcing overwrite of")
	// Diff still shows the canonical prompts URL (the after state).
	assert.Contains(t, stdout.String(), PromptMCPURL())
}

func TestRunConfigure__aggregates_mismatches_across_multiple_tools(t *testing.T) {
	dir := t.TempDir()
	ccPath := filepath.Join(dir, ".claude.json")
	desktopPath := filepath.Join(dir, "claude_desktop_config.json")

	writeTestJSON(t, ccPath, map[string]any{
		"mcpServers": map[string]any{
			serverNamePrompts: map[string]any{
				"type": "http", "url": "https://example.com/my-prompts",
				"headers": map[string]any{"Authorization": "Bearer bm_a"},
			},
		},
	})
	writeTestJSON(t, desktopPath, map[string]any{
		"mcpServers": map[string]any{
			serverNameContent: map[string]any{
				"command": "npx",
				"args":    []string{"mcp-remote", "http://localhost:8001/mcp", "--header", "Authorization: Bearer bm_b"},
			},
		},
	})

	client := api.NewClient("http://unused", "bm_login", "pat")
	tools := []DetectedTool{
		{Name: "claude-code", Detected: true, ConfigPath: ccPath},
		{Name: "claude-desktop", Detected: true, ConfigPath: desktopPath, HasNpx: true},
	}

	_, err := RunConfigure(ConfigureOpts{
		Handlers: DefaultHandlers(), Client: client, AuthType: "pat",
	}, tools)
	require.Error(t, err)
	msg := err.Error()
	assert.Contains(t, msg, "2 tools")
	assert.Contains(t, msg, "claude-code")
	assert.Contains(t, msg, "claude-desktop")
	assert.Contains(t, msg, "--force (applies to all tools in this run)")
}

func TestRunConfigure__force_overwrites_canonical_with_non_tiddly_url(t *testing.T) {
	dir := t.TempDir()
	configPath := filepath.Join(dir, ".claude.json")
	writeTestJSON(t, configPath, map[string]any{
		"mcpServers": map[string]any{
			serverNamePrompts: map[string]any{
				"type": "http", "url": "https://example.com/my-prompts",
				"headers": map[string]any{"Authorization": "Bearer bm_old"},
			},
		},
	})

	client := api.NewClient("http://unused", "bm_login", "pat")
	stdout, stderr := &bytes.Buffer{}, &bytes.Buffer{}
	tools := []DetectedTool{{Name: "claude-code", Detected: true, ConfigPath: configPath}}

	_, err := RunConfigure(ConfigureOpts{
		Handlers: DefaultHandlers(), Client: client, AuthType: "pat",
		Force: true, Output: stdout, ErrOutput: stderr,
	}, tools)
	require.NoError(t, err)
	assert.Contains(t, stderr.String(), "Forcing overwrite of "+serverNamePrompts)
	assert.Contains(t, stderr.String(), "https://example.com/my-prompts")

	after := readTestJSON(t, configPath)
	servers := after["mcpServers"].(map[string]any)
	prompts := servers[serverNamePrompts].(map[string]any)
	assert.Equal(t, PromptMCPURL(), prompts["url"], "--force must rewrite the URL to canonical")
}

func TestRunConfigure__force_is_no_op_when_no_mismatch(t *testing.T) {
	// --force is an override; without a mismatch, it produces no extra noise.
	dir := t.TempDir()
	configPath := filepath.Join(dir, ".claude.json")
	client := api.NewClient("http://unused", "bm_login", "pat")
	stdout, stderr := &bytes.Buffer{}, &bytes.Buffer{}
	tools := []DetectedTool{{Name: "claude-code", Detected: true, ConfigPath: configPath}}

	_, err := RunConfigure(ConfigureOpts{
		Handlers: DefaultHandlers(), Client: client, AuthType: "pat",
		Force: true, Output: stdout, ErrOutput: stderr,
	}, tools)
	require.NoError(t, err)
	assert.NotContains(t, stderr.String(), "Forcing overwrite")
}

func TestRunConfigure__antigravity_mis_keyed_canonical_self_heals(t *testing.T) {
	// A canonical-named Antigravity entry mis-keyed with "url" (which agy
	// ignores) reads as an empty URL under strict serverUrl-only classification.
	// That must NOT trigger the "unexpected URL" mismatch refusal — configure
	// should overwrite it in place with the correct serverUrl form.
	dir := t.TempDir()
	configPath := filepath.Join(dir, "mcp_config.json")
	writeTestJSON(t, configPath, map[string]any{
		"mcpServers": map[string]any{
			serverNameContent: map[string]any{
				"url":     ContentMCPURL(),
				"headers": map[string]any{"Authorization": "Bearer bm_old"},
			},
		},
	})

	client := api.NewClient("http://unused", "bm_login", "pat")
	tools := []DetectedTool{{Name: "antigravity", Detected: true, ConfigPath: configPath}}

	_, err := RunConfigure(ConfigureOpts{
		Handlers: DefaultHandlers(), Client: client, AuthType: "pat",
	}, tools)
	require.NoError(t, err, "mis-keyed canonical entry must self-heal, not refuse")

	servers := readTestJSON(t, configPath)["mcpServers"].(map[string]any)
	content := servers[serverNameContent].(map[string]any)
	assert.Equal(t, ContentMCPURL(), content["serverUrl"])
	assert.NotContains(t, content, "url", "mis-keyed url field must be replaced by serverUrl")
}

func TestRunConfigure__reports_preserved_non_canonical_entries(t *testing.T) {
	dir := t.TempDir()
	configPath := filepath.Join(dir, ".claude.json")
	writeTestJSON(t, configPath, map[string]any{
		"mcpServers": map[string]any{
			"work_prompts":     map[string]any{"type": "http", "url": PromptMCPURL()},
			"personal_prompts": map[string]any{"type": "http", "url": PromptMCPURL()},
		},
	})

	client := api.NewClient("http://unused", "bm_login", "pat")
	tools := []DetectedTool{{Name: "claude-code", Detected: true, ConfigPath: configPath}}

	result, err := RunConfigure(ConfigureOpts{
		Handlers: DefaultHandlers(), Client: client, AuthType: "pat",
	}, tools)
	require.NoError(t, err)
	require.NotNil(t, result.PreservedEntries)
	preserved := result.PreservedEntries["claude-code"]
	assert.ElementsMatch(t, []string{"work_prompts", "personal_prompts"}, preserved)
}

func TestRunConfigure__preserved_entries_scoped_to_requested_servers(t *testing.T) {
	// --servers content: work_prompts (prompts-typed) must NOT be reported
	// as preserved because it's out of scope.
	dir := t.TempDir()
	configPath := filepath.Join(dir, ".claude.json")
	writeTestJSON(t, configPath, map[string]any{
		"mcpServers": map[string]any{
			"work_content": map[string]any{"type": "http", "url": ContentMCPURL()},
			"work_prompts": map[string]any{"type": "http", "url": PromptMCPURL()},
		},
	})

	client := api.NewClient("http://unused", "bm_login", "pat")
	tools := []DetectedTool{{Name: "claude-code", Detected: true, ConfigPath: configPath}}

	result, err := RunConfigure(ConfigureOpts{
		Handlers: DefaultHandlers(), Client: client, AuthType: "pat",
		Servers: []string{ServerContent},
	}, tools)
	require.NoError(t, err)
	preserved := result.PreservedEntries["claude-code"]
	assert.Equal(t, []string{"work_content"}, preserved,
		"only in-scope non-canonical entries should be reported as preserved")
}

func TestDeleteTokensByPrefix__empty_reqs_returns_no_error(t *testing.T) {
	// With no requests, the helper should not even call ListTokens.
	var listCalls int
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		listCalls++
		w.WriteHeader(500)
	}))
	defer server.Close()

	client := api.NewClient(server.URL, "oauth-jwt", "oauth")
	results, err := DeleteTokensByPrefix(context.Background(), client, nil)
	require.NoError(t, err)
	assert.Empty(t, results)
	assert.Equal(t, 0, listCalls)
}

// ---------------------------------------------------------------------------
// Review-driven additions: cross-contamination guard, hard-error ordering,
// --force log timing, DeleteTokensByPrefix helper-level coverage.
// ---------------------------------------------------------------------------

func TestRunConfigure__does_not_reuse_pat_from_cross_wired_canonical_slot(t *testing.T) {
	// Regression guard for the ExtractPATs cross-contamination bug:
	// tiddly_prompts is cross-wired to the content URL (user hand-edit).
	// --servers content scopes the run to content; tiddly_prompts is
	// out-of-scope so it survives untouched. No canonical content entry
	// exists. Configure must MINT a fresh content token — it must NOT
	// reuse the PAT from the cross-wired tiddly_prompts slot.
	var mintedCount int
	var validatedPATs []string
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch {
		case r.Method == "GET" && r.URL.Path == "/users/me":
			validatedPATs = append(validatedPATs, r.Header.Get("Authorization"))
			_ = json.NewEncoder(w).Encode(api.UserInfo{ID: "u1"})
		case r.Method == "POST" && r.URL.Path == "/tokens/":
			mintedCount++
			var req api.TokenCreateRequest
			_ = json.NewDecoder(r.Body).Decode(&req)
			w.WriteHeader(http.StatusCreated)
			_ = json.NewEncoder(w).Encode(api.TokenCreateResponse{ID: "tok-new", Name: req.Name, Token: "bm_minted"})
		default:
			w.WriteHeader(404)
		}
	}))
	defer server.Close()

	dir := t.TempDir()
	configPath := filepath.Join(dir, ".claude.json")
	writeTestJSON(t, configPath, map[string]any{
		"mcpServers": map[string]any{
			// Cross-wired: canonical prompts name at the CONTENT URL.
			serverNamePrompts: map[string]any{
				"type":    "http",
				"url":     ContentMCPURL(),
				"headers": map[string]any{"Authorization": "Bearer bm_cross_wired"},
			},
		},
	})

	client := api.NewClient(server.URL, "oauth-jwt", "oauth")
	stdout := &bytes.Buffer{}
	tools := []DetectedTool{{Name: "claude-code", Detected: true, ConfigPath: configPath}}

	_, err := RunConfigure(ConfigureOpts{
		Handlers: DefaultHandlers(), Client: client, AuthType: "oauth",
		Servers: []string{ServerContent}, Output: stdout,
	}, tools)
	require.NoError(t, err)
	assert.Equal(t, 1, mintedCount,
		"content slot must mint fresh — cross-wired prompts PAT must not bleed in")
	assert.NotContains(t, validatedPATs, "Bearer bm_cross_wired",
		"cross-wired PAT must not even reach validation — canonicalEntryPATs filters it out")
}

func TestRunConfigure__hard_error_on_second_tool_discards_first_tool_mismatch(t *testing.T) {
	// Tool A has an in-scope URL mismatch; tool B has a malformed config
	// (Status parse error). The hard error from tool B must surface alone;
	// tool A's accumulated mismatch must NOT appear in the error.
	dir := t.TempDir()
	toolAPath := filepath.Join(dir, ".claude.json")
	writeTestJSON(t, toolAPath, map[string]any{
		"mcpServers": map[string]any{
			serverNamePrompts: map[string]any{
				"type":    "http",
				"url":     "https://example.com/my-prompts",
				"headers": map[string]any{"Authorization": "Bearer bm_a"},
			},
		},
	})

	toolBPath := filepath.Join(dir, "claude_desktop_config.json")
	require.NoError(t, os.WriteFile(toolBPath, []byte("{{ not valid json"), 0600))

	client := api.NewClient("http://unused", "bm_login", "pat")
	tools := []DetectedTool{
		{Name: "claude-code", Detected: true, ConfigPath: toolAPath},
		{Name: "claude-desktop", Detected: true, ConfigPath: toolBPath, HasNpx: true},
	}

	_, err := RunConfigure(ConfigureOpts{
		Handlers: DefaultHandlers(), Client: client, AuthType: "pat",
	}, tools)
	require.Error(t, err)
	assert.Contains(t, err.Error(), "reading claude-desktop config for safety check",
		"hard error from tool B must surface")
	assert.NotContains(t, err.Error(), "CLI-managed",
		"tool A's accumulated mismatch must be discarded when a hard error fires")
	assert.NotContains(t, err.Error(), serverNamePrompts,
		"tool A's mismatched entry name must not leak into the hard-error message")
}

func TestRunConfigure__hard_error_on_first_tool_short_circuits_second_tool_scan(t *testing.T) {
	// Tool A has a parse error; tool B has an in-scope mismatch. The parse
	// error from tool A must surface; tool B must never be scanned
	// (its mismatch must NOT appear in the error).
	dir := t.TempDir()
	toolAPath := filepath.Join(dir, ".claude.json")
	require.NoError(t, os.WriteFile(toolAPath, []byte("{{ not valid json"), 0600))

	toolBPath := filepath.Join(dir, "claude_desktop_config.json")
	writeTestJSON(t, toolBPath, map[string]any{
		"mcpServers": map[string]any{
			serverNameContent: map[string]any{
				"command": "npx",
				"args":    []string{"mcp-remote", "http://localhost:8001/mcp", "--header", "Authorization: Bearer bm_b"},
			},
		},
	})

	client := api.NewClient("http://unused", "bm_login", "pat")
	tools := []DetectedTool{
		{Name: "claude-code", Detected: true, ConfigPath: toolAPath},
		{Name: "claude-desktop", Detected: true, ConfigPath: toolBPath, HasNpx: true},
	}

	_, err := RunConfigure(ConfigureOpts{
		Handlers: DefaultHandlers(), Client: client, AuthType: "pat",
	}, tools)
	require.Error(t, err)
	assert.Contains(t, err.Error(), "reading claude-code config for safety check",
		"hard error from tool A must surface")
	assert.NotContains(t, err.Error(), serverNameContent,
		"tool B's mismatch must not appear — tool B was never scanned")
}

func TestRunConfigure__force_log_not_emitted_when_pat_resolution_fails(t *testing.T) {
	// Regression guard for the "Forcing overwrite..." log timing: if
	// resolveToolPATs fails (e.g. token mint error), the log must not have
	// already been printed. Users should never see "Forcing overwrite of X"
	// followed by an error — it implies an overwrite happened.
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Fail every /tokens/ POST so mint errors trigger before any write.
		if r.Method == "POST" && r.URL.Path == "/tokens/" {
			w.WriteHeader(http.StatusInternalServerError)
			return
		}
		w.WriteHeader(404)
	}))
	defer server.Close()

	dir := t.TempDir()
	configPath := filepath.Join(dir, ".claude.json")
	writeTestJSON(t, configPath, map[string]any{
		"mcpServers": map[string]any{
			serverNamePrompts: map[string]any{
				"type":    "http",
				"url":     "https://example.com/my-prompts",
				"headers": map[string]any{"Authorization": "Bearer bm_old"},
			},
		},
	})

	client := api.NewClient(server.URL, "oauth-jwt", "oauth")
	stdout, stderr := &bytes.Buffer{}, &bytes.Buffer{}
	tools := []DetectedTool{{Name: "claude-code", Detected: true, ConfigPath: configPath}}

	_, err := RunConfigure(ConfigureOpts{
		Handlers: DefaultHandlers(), Client: client, AuthType: "oauth",
		Force: true, Output: stdout, ErrOutput: stderr,
	}, tools)
	require.Error(t, err, "mint failure must surface")
	assert.NotContains(t, stderr.String(), "Forcing overwrite of",
		"force log must not fire before resolveToolPATs succeeds")
}

func TestDeleteTokensByPrefix__shared_pat_fans_out_single_deletion(t *testing.T) {
	// Two requests sharing one PAT must produce exactly one server-side
	// DELETE; both results must mirror the same DeletedNames.
	var deleteCalls int
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch {
		case r.Method == "GET" && r.URL.Path == "/tokens/":
			// TokenPrefix must equal PAT[:tokenPrefixLen] (12) to match.
			_ = json.NewEncoder(w).Encode([]api.TokenInfo{
				{ID: "tok-shared", Name: "cli-mcp-claude-code-content-abc", TokenPrefix: "bm_shared_12"},
			})
		case r.Method == "DELETE" && r.URL.Path == "/tokens/tok-shared":
			deleteCalls++
			w.WriteHeader(http.StatusNoContent)
		default:
			w.WriteHeader(404)
		}
	}))
	defer server.Close()

	client := api.NewClient(server.URL, "oauth-jwt", "oauth")
	reqs := []TokenRevokeRequest{
		{EntryLabel: "tiddly_notes_bookmarks", PAT: "bm_shared_1234567"},
		{EntryLabel: "tiddly_prompts", PAT: "bm_shared_1234567"},
	}
	results, err := DeleteTokensByPrefix(context.Background(), client, reqs)
	require.NoError(t, err)
	assert.Equal(t, 1, deleteCalls, "shared PAT must dedupe to a single DELETE")
	require.Len(t, results, 2)
	assert.Equal(t, []string{"cli-mcp-claude-code-content-abc"}, results[0].DeletedNames,
		"both requests must surface the same DeletedNames from the single delete")
	assert.Equal(t, []string{"cli-mcp-claude-code-content-abc"}, results[1].DeletedNames)
	assert.NoError(t, results[0].Err)
	assert.NoError(t, results[1].Err)
}

func TestDeleteTokensByPrefix__preserves_order_and_labels_with_mixed_shared_and_unique_pats(t *testing.T) {
	// Requests: [A→pat1, B→pat2, C→pat1]. Results must come back as
	// [A, B, C] in order. A and C share DeletedNames (shared PAT);
	// B is independent. Note tokenPrefixLen=12: the TokenPrefix values
	// below must exactly equal PAT[:12] to match.
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch {
		case r.Method == "GET" && r.URL.Path == "/tokens/":
			_ = json.NewEncoder(w).Encode([]api.TokenInfo{
				{ID: "tok-1", Name: "cli-mcp-claude-code-content-x1", TokenPrefix: "bm_pat1shrd_"},
				{ID: "tok-2", Name: "cli-mcp-claude-code-prompts-x2", TokenPrefix: "bm_pat2uniq_"},
			})
		case r.Method == "DELETE" && strings.HasPrefix(r.URL.Path, "/tokens/"):
			w.WriteHeader(http.StatusNoContent)
		default:
			w.WriteHeader(404)
		}
	}))
	defer server.Close()

	client := api.NewClient(server.URL, "oauth-jwt", "oauth")
	reqs := []TokenRevokeRequest{
		{EntryLabel: "A", PAT: "bm_pat1shrd_tail"},
		{EntryLabel: "B", PAT: "bm_pat2uniq_tail"},
		{EntryLabel: "C", PAT: "bm_pat1shrd_tail"},
	}
	results, err := DeleteTokensByPrefix(context.Background(), client, reqs)
	require.NoError(t, err)
	require.Len(t, results, 3)

	// Order and labels must be preserved.
	assert.Equal(t, "A", results[0].EntryLabel)
	assert.Equal(t, "B", results[1].EntryLabel)
	assert.Equal(t, "C", results[2].EntryLabel)

	// A and C share the shared-PAT deletion.
	assert.Equal(t, []string{"cli-mcp-claude-code-content-x1"}, results[0].DeletedNames)
	assert.Equal(t, []string{"cli-mcp-claude-code-content-x1"}, results[2].DeletedNames)

	// B has the unique-PAT deletion.
	assert.Equal(t, []string{"cli-mcp-claude-code-prompts-x2"}, results[1].DeletedNames)
}

func TestDeleteTokensByPrefix__short_pat_returns_empty_not_error(t *testing.T) {
	// A PAT too short for a prefix (see PATPrefix) must yield an empty DeletedNames
	// with nil Err (treated as "nothing matched" for consistent caller
	// handling of per-entry notes).
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		if r.Method == "GET" && r.URL.Path == "/tokens/" {
			_ = json.NewEncoder(w).Encode([]api.TokenInfo{
				{ID: "tok-1", Name: "cli-mcp-x-content-abc", TokenPrefix: "bm_anyprefix"},
			})
			return
		}
		w.WriteHeader(404)
	}))
	defer server.Close()

	client := api.NewClient(server.URL, "oauth-jwt", "oauth")
	reqs := []TokenRevokeRequest{{EntryLabel: "tiddly_prompts", PAT: "bm_short"}} // too short for a prefix (see PATPrefix)
	results, err := DeleteTokensByPrefix(context.Background(), client, reqs)
	require.NoError(t, err)
	require.Len(t, results, 1)
	assert.Equal(t, "tiddly_prompts", results[0].EntryLabel)
	assert.Empty(t, results[0].DeletedNames, "short PAT must not match anything")
	assert.NoError(t, results[0].Err, "short PAT must not surface an error")
}
