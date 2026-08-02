package testutil

// UserMeResponse returns a typical /users/me response body.
func UserMeResponse(email string) map[string]any {
	return map[string]any{
		"id":    "user-123",
		"email": email,
		"name":  "Test User",
	}
}

// HealthResponse returns a typical /health response body.
func HealthResponse() map[string]any {
	return map[string]any{
		"status": "ok",
	}
}

// Error402Response returns a 402 quota-exceeded response.
func Error402Response(resource string, current, limit int) map[string]any {
	return map[string]any{
		"detail":     "Quota exceeded",
		"error_code": "QUOTA_EXCEEDED",
		"resource":   resource,
		"current":    current,
		"limit":      limit,
	}
}
