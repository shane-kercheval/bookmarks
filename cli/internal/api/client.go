package api

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strconv"
	"time"
)

const maxRetries = 2

// Client is an HTTP client for the Tiddly API.
type Client struct {
	BaseURL    string
	Token      string
	AuthType   string
	HTTPClient *http.Client
	// Stderr for retry messages (defaults to nil = silent).
	Stderr io.Writer
}

// NewClient creates a new API client.
func NewClient(baseURL, token, authType string) *Client {
	return &Client{
		BaseURL:    baseURL,
		Token:      token,
		AuthType:   authType,
		HTTPClient: &http.Client{Timeout: 30 * time.Second},
	}
}

// APIError represents a structured error from the API.
type APIError struct {
	StatusCode int
	Message    string
	// Fields for 402 quota errors
	ErrorCode string `json:"error_code"`
	Resource  string `json:"resource"`
	Current   int    `json:"current"`
	Limit     int    `json:"limit"`
}

func (e *APIError) Error() string {
	return e.Message
}

// Do executes an HTTP request with auth headers and error handling.
// If body is non-nil, it's JSON-encoded. If result is non-nil, response is JSON-decoded into it.
func (c *Client) Do(ctx context.Context, method, path string, body any, result any) error {
	return c.doWithRetry(ctx, method, path, body, result, 0)
}

func (c *Client) doWithRetry(ctx context.Context, method, path string, body any, result any, attempt int) error {
	var bodyReader io.Reader
	if body != nil {
		data, err := json.Marshal(body)
		if err != nil {
			return fmt.Errorf("encoding request body: %w", err)
		}
		bodyReader = bytes.NewReader(data)
	}

	req, err := http.NewRequestWithContext(ctx, method, c.BaseURL+path, bodyReader)
	if err != nil {
		return fmt.Errorf("creating request: %w", err)
	}

	req.Header.Set("Authorization", "Bearer "+c.Token)
	req.Header.Set("X-Request-Source", "cli")
	req.Header.Set("Content-Type", "application/json")

	resp, err := c.HTTPClient.Do(req)
	if err != nil {
		return fmt.Errorf("request failed: %w", err)
	}
	defer resp.Body.Close() //nolint:errcheck

	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		return fmt.Errorf("reading response: %w", err)
	}

	if resp.StatusCode >= 200 && resp.StatusCode < 300 {
		if result != nil && len(respBody) > 0 {
			if err := json.Unmarshal(respBody, result); err != nil {
				return fmt.Errorf("decoding response: %w", err)
			}
		}
		return nil
	}

	return c.handleError(ctx, resp, respBody, method, path, body, result, attempt)
}

func (c *Client) handleError(ctx context.Context, resp *http.Response, respBody []byte, method, path string, reqBody any, result any, attempt int) error {
	// 429 is the only status that triggers retry logic
	if resp.StatusCode == http.StatusTooManyRequests {
		return c.handle429(ctx, resp, respBody, method, path, reqBody, result, attempt)
	}
	return c.classifyError(resp, respBody)
}

// classifyError maps a non-2xx response to an APIError without retry logic.
// Used by handleError (after 429 check) and directly by methods that bypass Do()
// (e.g., ExportSkills which streams the response body).
func (c *Client) classifyError(resp *http.Response, respBody []byte) error {
	switch resp.StatusCode {
	case http.StatusUnauthorized:
		return c.handle401(respBody)

	case 402:
		return c.handle402(respBody)

	case http.StatusForbidden:
		return &APIError{
			StatusCode: 403,
			Message:    "This action requires browser login. Run 'tiddly login' (without --token).",
		}

	default:
		msg := string(respBody)
		// Try to extract detail from JSON error response
		var errResp struct {
			Detail string `json:"detail"`
		}
		if json.Unmarshal(respBody, &errResp) == nil && errResp.Detail != "" {
			msg = errResp.Detail
		}
		return &APIError{
			StatusCode: resp.StatusCode,
			Message:    fmt.Sprintf("API error (%d): %s", resp.StatusCode, msg),
		}
	}
}

// handle401 distinguishes the terminal account-deleted 401 (the token is valid,
// but its account was deleted, so re-login can never succeed) from an ordinary
// expired session. Clients bind to the stable machine-readable error_code, not
// the human-readable detail. Credential removal is deliberately NOT done here —
// it belongs to the keyring/auth layer (`tiddly logout`), which the message
// directs the user to; the API client must not own credential storage.
func (c *Client) handle401(body []byte) error {
	var errResp struct {
		ErrorCode string `json:"error_code"`
	}
	if json.Unmarshal(body, &errResp) == nil && errResp.ErrorCode == "account_deleted" {
		return &APIError{
			StatusCode: 401,
			ErrorCode:  errResp.ErrorCode,
			Message: "This account has been deleted; logging in again will not restore it. " +
				"Run 'tiddly logout' to clear the stored credentials.",
		}
	}
	return &APIError{
		StatusCode: 401,
		Message:    "Session expired. Run 'tiddly login' to re-authenticate.",
	}
}

func (c *Client) handle402(body []byte) error {
	var errResp struct {
		Detail    string `json:"detail"`
		ErrorCode string `json:"error_code"`
		Resource  string `json:"resource"`
		Current   int    `json:"current"`
		Limit     int    `json:"limit"`
	}
	apiErr := &APIError{StatusCode: 402}
	if json.Unmarshal(body, &errResp) == nil && errResp.ErrorCode != "" {
		apiErr.ErrorCode = errResp.ErrorCode
		apiErr.Resource = errResp.Resource
		apiErr.Current = errResp.Current
		apiErr.Limit = errResp.Limit
		apiErr.Message = fmt.Sprintf(
			"Quota exceeded: %s (%d/%d). Upgrade at https://tiddly.me/pricing",
			errResp.Resource, errResp.Current, errResp.Limit,
		)
	} else {
		apiErr.Message = "Quota exceeded. Upgrade at https://tiddly.me/pricing"
	}
	return apiErr
}

func (c *Client) handle429(ctx context.Context, resp *http.Response, body []byte, method, path string, reqBody any, result any, attempt int) error {
	retryAfter := resp.Header.Get("Retry-After")
	seconds := 1
	if retryAfter != "" {
		if s, err := strconv.Atoi(retryAfter); err == nil {
			seconds = s
		}
	}

	// Only retry idempotent methods to avoid duplicate side effects (e.g., POST /tokens/)
	isIdempotent := method == "GET" || method == "HEAD" || method == "PUT" || method == "DELETE"
	if isIdempotent && attempt < maxRetries {
		if c.Stderr != nil {
			fmt.Fprintf(c.Stderr, "Rate limited, retrying in %ds...\n", seconds)
		}
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-time.After(time.Duration(seconds) * time.Second):
		}
		return c.doWithRetry(ctx, method, path, reqBody, result, attempt+1)
	}

	return &APIError{
		StatusCode: 429,
		Message:    fmt.Sprintf("Rate limited. Try again in %d seconds.", seconds),
	}
}
