package cmd

import (
	"fmt"
	"os"
	"os/signal"
	"strings"

	"github.com/shane-kercheval/tiddly/cli/internal/api"
	"github.com/shane-kercheval/tiddly/cli/internal/auth"
	"github.com/spf13/cobra"
)

func newLoginCmd() *cobra.Command {
	var tokenFlag string

	cmd := &cobra.Command{
		Use:   "login",
		Short: "Authenticate with Tiddly",
		Long: `Authenticate with Tiddly by signing in through your browser, or with a Personal Access Token.

Without --token, opens your browser to sign in (OAuth with PKCE): approve in the browser and the CLI receives its credentials via a temporary local callback. Press Ctrl+C to cancel. This requires a browser on this machine - on headless machines (SSH, containers), use --token instead.

With --token, validates the PAT format (must start with "bm_"), verifies it against the API, and stores it. Leading/trailing whitespace is trimmed.

Credentials are stored in the system keyring. If the keyring is unavailable, falls back to plaintext at ~/.config/tiddly/credentials.

Examples:
  tiddly login              Open browser for OAuth login
  tiddly login --token X    Use a Personal Access Token`,
		RunE: func(cmd *cobra.Command, args []string) error {
			if tokenFlag != "" {
				return loginWithPAT(cmd, tokenFlag)
			}
			return loginWithOAuth(cmd)
		},
	}

	cmd.Flags().StringVar(&tokenFlag, "token", "", "Personal Access Token (starts with bm_)")

	return cmd
}

func loginWithPAT(cmd *cobra.Command, token string) error {
	// Trim whitespace (common copy-paste artifact)
	original := token
	token = strings.TrimSpace(token)
	if token != original {
		fmt.Fprintln(cmd.ErrOrStderr(), "Trimmed whitespace from token.")
	}

	// Reject tokens with embedded spaces/newlines
	if strings.ContainsAny(token, " \t\n\r") {
		return fmt.Errorf("invalid token: contains embedded whitespace")
	}

	// Validate format
	if err := auth.ValidatePATFormat(token); err != nil {
		return err
	}

	// Verify token works
	client := api.NewClient(apiURL(), token, "pat")
	user, err := client.GetMe(cmd.Context())
	if err != nil {
		return fmt.Errorf("token verification failed: %w", err)
	}

	// Store PAT
	if err := appDeps.TokenManager.StorePAT(token); err != nil {
		return fmt.Errorf("storing token: %w", err)
	}

	msg := "Logged in successfully."
	if user.Email != "" {
		msg = fmt.Sprintf("Logged in as %s", user.Email)
	}
	fmt.Fprintln(cmd.OutOrStdout(), msg)
	warnIfFileStore(cmd)
	return nil
}

func loginWithOAuth(cmd *cobra.Command) error {
	// Set up context with Ctrl+C cancellation
	ctx, stop := signal.NotifyContext(cmd.Context(), os.Interrupt)
	defer stop()

	// Shallow copy the PKCEFlow from appDeps to preserve HTTPClient, BaseURL, etc.
	// Only override Output for command-specific stderr routing.
	var flow *auth.PKCEFlow
	if appDeps.TokenManager.Flow != nil {
		flowCopy := *appDeps.TokenManager.Flow
		flowCopy.Output = cmd.ErrOrStderr()
		flow = &flowCopy
	} else {
		flow = auth.NewPKCEFlow(auth.DefaultOAuthConfig())
		flow.Output = cmd.ErrOrStderr()
	}

	tokens, err := flow.Login(ctx)
	if err != nil {
		if ctx.Err() != nil {
			fmt.Fprintln(cmd.OutOrStdout(), "Login cancelled.")
			return nil
		}
		return fmt.Errorf("login failed: %w", err)
	}

	// Store OAuth tokens
	if err := appDeps.TokenManager.StoreOAuthTokens(tokens.AccessToken, tokens.RefreshToken); err != nil {
		return fmt.Errorf("storing credentials: %w", err)
	}

	// Verify and show user info
	client := api.NewClient(apiURL(), tokens.AccessToken, "oauth")
	user, err := client.GetMe(cmd.Context())
	if err != nil {
		// Credentials are stored either way; the verification call is best-effort
		fmt.Fprintln(cmd.OutOrStdout(), "Logged in successfully.")
		fmt.Fprintf(cmd.ErrOrStderr(), "Warning: Could not verify user info: %v\n", err)
		warnIfFileStore(cmd)
		return nil
	}

	msg := "Logged in successfully."
	if user.Email != "" {
		msg = fmt.Sprintf("Logged in as %s", user.Email)
	}
	fmt.Fprintln(cmd.OutOrStdout(), msg)
	warnIfFileStore(cmd)
	return nil
}

// warnIfFileStore prints a warning if credentials are stored in a plaintext file
// instead of the system keyring.
func warnIfFileStore(cmd *cobra.Command) {
	if appDeps != nil && appDeps.FileStoreFallback {
		fmt.Fprintln(cmd.ErrOrStderr(),
			"Warning: System keyring unavailable. Credentials stored in plaintext at "+
				appDeps.ConfigDir+"/credentials")
	}
}
