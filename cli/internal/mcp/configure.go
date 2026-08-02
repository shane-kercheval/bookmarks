package mcp

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"errors"
	"fmt"
	"io"
	"os"
	"regexp"
	"sort"
	"strings"
	"time"

	"github.com/shane-kercheval/tiddly/cli/internal/api"
)

// dryRunPlaceholder is the token shown in dry-run output when a new token would be created.
const dryRunPlaceholder = "<new-token-would-be-created>"

// tokenPrefixLen is the number of leading characters the API stores as
// token_prefix. Not exported — callers that need the derived prefix value
// use PATPrefix() instead of doing the slice themselves.
const tokenPrefixLen = 12

// PATPrefix returns the leading characters of pat that match the
// token_prefix the API stores for each token. Returns "" when pat is too
// short to yield a usable prefix (that case is semantically "no match
// possible" — callers may treat it as "nothing to subtract" or "nothing
// to delete" depending on context). Centralizing this avoids the duplicate
// len-gated slice pattern that previously lived in both DeleteTokensByPrefix
// and the cmd-layer orphan-token filter.
func PATPrefix(pat string) string {
	if len(pat) < tokenPrefixLen {
		return ""
	}
	return pat[:tokenPrefixLen]
}

// ConfigureOpts configures the MCP configure flow.
type ConfigureOpts struct {
	Ctx       context.Context
	Client    *api.Client
	Handlers  []ToolHandler // handler list for dispatch
	AuthType  string        // "oauth", "pat", "flag", "env"
	DryRun    bool
	Scope     string   // Tiddly scope: "user" (default) or "directory"
	Cwd       string   // working directory for directory scope resolution
	Servers   []string // which servers to configure: "content", "prompts" (default: both)
	ExpiresIn *int     // PAT expiration in days (nil = no expiration)
	Output    io.Writer
	ErrOutput io.Writer

	// Force, when true, tells preflight to proceed even if a CLI-managed
	// key exists at an unexpected URL (non-Tiddly or wrong-type Tiddly).
	// The mismatched entry is overwritten with the canonical value. Does
	// NOT override any other safety check.
	Force bool
}

// canonicalMismatch describes a CLI-managed-named key whose current URL
// doesn't match the expected Tiddly URL for its type. Covers BOTH the
// non-Tiddly URL sub-case (entry shows up in OtherServers) and the
// wrong-type Tiddly URL sub-case (entry shows up in Servers with
// MatchByName but a ServerType that disagrees with the expected one).
type canonicalMismatch struct {
	Name string // serverNameContent or serverNamePrompts
	URL  string // current on-disk URL
}

// toolMismatches groups per-tool mismatches for aggregated error reporting.
type toolMismatches struct {
	ToolName   string
	ConfigPath string
	Entries    []canonicalMismatch
}

// preflightedTool holds per-tool state computed during Phase 1 (pre-flight)
// of RunConfigure. Everything here is gathered without mutating the user's
// filesystem or any server-side state.
type preflightedTool struct {
	tool            DetectedTool
	handler         ToolHandler
	rc              ResolvedConfig
	preservedNames  []string            // non-canonical Tiddly-URL entry names the run leaves alone, scoped to opts.Servers
	forceOverwrites []canonicalMismatch // populated only when opts.Force && this tool has mismatches
}

// ServerTypeForCanonicalName is the inverse of CanonicalName: given a
// CLI-managed entry key name, returns its expected server type. ok is
// false for any non-canonical name. Paired with CanonicalName so callers
// can translate both directions through a single source of truth.
func ServerTypeForCanonicalName(name string) (serverType string, ok bool) {
	switch name {
	case serverNameContent:
		return ServerContent, true
	case serverNamePrompts:
		return ServerPrompts, true
	default:
		return "", false
	}
}

// wantServer returns true if the given server name is in the requested servers list.
func (o ConfigureOpts) wantServer(name string) bool {
	if len(o.Servers) == 0 {
		return true // default: both
	}
	for _, s := range o.Servers {
		if s == name {
			return true
		}
	}
	return false
}

// BackupRecord points at a single timestamped backup file created before
// a destructive write.
type BackupRecord struct {
	Tool string // tool name (e.g. "claude-desktop")
	Path string // absolute path to the <original>.bak.<timestamp> file
}

// ConfigureResult captures what was done during configure.
type ConfigureResult struct {
	ToolsConfigured []string
	TokensCreated   []string
	TokensReused    []string
	Warnings        []string
	// Backups holds one record per tool whose config file existed before
	// configure and was copied to a timestamped backup.
	Backups []BackupRecord
	// PreservedEntries lists, per tool, the non-canonical Tiddly-URL entry
	// names that were left alone by this run. Scoped to opts.Servers.
	PreservedEntries map[string][]string
}

// RunConfigure orchestrates MCP server configuration for the given tools.
//
// Phase 1 (preflight): resolve paths, read current state, detect CLI-managed
// slots pointing at unexpected URLs, gather preserved-entry names. No writes
// or server-side mutations.
//
// Preflight outcome:
//   - No mismatches → proceed to commit.
//   - opts.Force → mark mismatched slots for overwrite, proceed to commit.
//   - opts.DryRun → emit per-entry stderr warnings, proceed to commit so
//     the diff is still produced.
//   - Otherwise → return an aggregated error before any tool's commit runs.
//
// Phase 2 (commit): PAT resolution + Configure. Commit-phase failure for a
// tool revokes that tool's freshly-minted tokens to avoid orphans.
func RunConfigure(opts ConfigureOpts, tools []DetectedTool) (*ConfigureResult, error) {
	if opts.Output == nil {
		opts.Output = os.Stdout
	}
	if opts.ErrOutput == nil {
		opts.ErrOutput = os.Stderr
	}
	if opts.Ctx == nil {
		opts.Ctx = context.Background()
	}

	result := &ConfigureResult{}

	isPATAuth := opts.AuthType == "pat" || opts.AuthType == "flag" || opts.AuthType == "env"
	if isPATAuth {
		result.Warnings = append(result.Warnings,
			"Using your current token for MCP servers. Login via 'tiddly login' to auto-create dedicated tokens per server.")
	}

	// Phase 1: preflight. Status errors are tolerated in dry-run but
	// fail-closed in a real configure — otherwise we'd bypass the
	// URL-mismatch detection the user is relying on.
	plan := make([]preflightedTool, 0, len(tools))
	var allMismatches []toolMismatches
	for _, tool := range tools {
		if !tool.Detected {
			continue
		}

		handler, ok := GetHandler(opts.Handlers, tool.Name)
		if !ok {
			return nil, fmt.Errorf("no handler for tool %q", tool.Name)
		}

		nativeScope := TranslateScope(opts.Scope, tool.Name)
		rc, err := ResolveToolConfig(handler, tool.ConfigPath, nativeScope, opts.Cwd)
		if err != nil {
			return nil, fmt.Errorf("%s: %w", tool.Name, err)
		}

		pf := preflightedTool{tool: tool, handler: handler, rc: rc}

		sr, statusErr := handler.Status(rc)
		switch {
		case statusErr != nil && opts.DryRun:
			// Diff is still informative; skip mismatch + preserved-entry derivation for this tool.
			plan = append(plan, pf)
			continue
		case statusErr != nil:
			return nil, fmt.Errorf("reading %s config for safety check: %w", tool.Name, statusErr)
		}

		// Mismatch detection, scoped to opts.Servers. Both sub-cases route
		// here: non-Tiddly URL entries live in sr.OtherServers; wrong-type
		// Tiddly URL entries live in sr.Servers with MatchByName.
		var mismatches []canonicalMismatch
		for _, o := range sr.OtherServers {
			// An entry with no recognizable URL isn't a URL conflict — there's
			// nothing for the canonical write to clash with, so overwrite it
			// freely (the backup preserves the prior contents) rather than
			// refusing with a misleading "unexpected URL" error. This also
			// lets a canonical entry mis-keyed with "url" instead of the
			// agy-required "serverUrl" (which reads as an empty URL under
			// Antigravity's strict serverUrl-only classification) self-heal on
			// configure instead of demanding --force.
			if o.URL == "" {
				continue
			}
			expected, known := ServerTypeForCanonicalName(o.Name)
			if !known {
				continue
			}
			if !opts.wantServer(expected) {
				continue
			}
			mismatches = append(mismatches, canonicalMismatch{Name: o.Name, URL: o.URL})
		}
		for _, s := range sr.Servers {
			if s.MatchMethod != MatchByName {
				continue
			}
			expected, known := ServerTypeForCanonicalName(s.Name)
			if !known {
				continue
			}
			if s.ServerType == expected {
				continue
			}
			if !opts.wantServer(expected) {
				continue
			}
			mismatches = append(mismatches, canonicalMismatch{Name: s.Name, URL: s.URL})
		}
		sort.Slice(mismatches, func(i, j int) bool { return mismatches[i].Name < mismatches[j].Name })

		if len(mismatches) > 0 {
			allMismatches = append(allMismatches, toolMismatches{
				ToolName:   tool.Name,
				ConfigPath: rc.Path,
				Entries:    mismatches,
			})
		}

		// Preserved-entries derivation: non-canonical Tiddly-URL entries
		// whose server type is in scope for this run.
		var preserved []string
		for _, s := range sr.Servers {
			if s.MatchMethod != MatchByURL {
				continue
			}
			if !opts.wantServer(s.ServerType) {
				continue
			}
			preserved = append(preserved, s.Name)
		}
		sort.Strings(preserved)
		pf.preservedNames = preserved

		plan = append(plan, pf)
	}

	// Resolve mismatch outcome. Order matters: Force is checked BEFORE
	// DryRun so `--dry-run --force` shows the diff with overwrites applied
	// and no warnings.
	switch {
	case len(allMismatches) == 0:
		// nothing to do
	case opts.Force:
		for i := range plan {
			for _, m := range allMismatches {
				if m.ToolName == plan[i].tool.Name {
					plan[i].forceOverwrites = m.Entries
				}
			}
		}
	case opts.DryRun:
		for _, m := range allMismatches {
			for _, e := range m.Entries {
				fmt.Fprintf(opts.ErrOutput,
					"Warning: %s at %s — real run will require --force\n", e.Name, e.URL)
			}
		}
	default:
		return nil, formatMismatchError(allMismatches)
	}

	// Phase 2: commit. PAT resolution (which may create tokens server-side)
	// and the filesystem write happen here. Commit-phase errors return the
	// partial result alongside the error so callers can surface what already
	// succeeded. Minted tokens for the FAILING tool are revoked to avoid
	// orphaning them on the user's account.
	for _, pf := range plan {
		res, err := resolveToolPATs(opts, pf.handler, pf.tool, pf.rc, isPATAuth)
		if err != nil {
			cleanupCtx, cancel := context.WithTimeout(context.Background(), cleanupTimeout)
			err = withRevokeError(err, revokeMintedTokens(cleanupCtx, opts.Client, res.Minted))
			cancel()
			return result, fmt.Errorf("resolving tokens for %s: %w", pf.tool.Name, err)
		}

		if opts.DryRun {
			fmt.Fprintf(opts.Output, "\n--- %s ---\n", pf.tool.Name)
			before, after, dErr := pf.handler.DryRun(pf.rc, res.ContentPAT, res.PromptPAT)
			if dErr != nil {
				return result, dErr
			}
			printDiff(opts.Output, pf.rc.Path, before, after)
			result.TokensReused = append(result.TokensReused, res.Reused...)
			continue
		}

		// Emit the force-overwrite log only here, after PAT resolution
		// succeeded and immediately before the write attempt, so a failure
		// in resolveToolPATs never produces a misleading "Forcing overwrite
		// of X" line followed by an error.
		for _, e := range pf.forceOverwrites {
			fmt.Fprintf(opts.ErrOutput, "Forcing overwrite of %s (currently %s)\n", e.Name, e.URL)
		}

		warnings, backupPath, cErr := pf.handler.Configure(pf.rc, res.ContentPAT, res.PromptPAT, pf.tool)
		if backupPath != "" {
			result.Backups = append(result.Backups, BackupRecord{Tool: pf.tool.Name, Path: backupPath})
		}
		if cErr != nil {
			cleanupCtx, cancel := context.WithTimeout(context.Background(), cleanupTimeout)
			cErr = withRevokeError(cErr, revokeMintedTokens(cleanupCtx, opts.Client, res.Minted))
			cancel()
			return result, fmt.Errorf("configuring %s: %w", pf.tool.Name, cErr)
		}

		for _, m := range res.Minted {
			result.TokensCreated = append(result.TokensCreated, m.Name)
		}
		result.TokensReused = append(result.TokensReused, res.Reused...)
		result.Warnings = append(result.Warnings, warnings...)
		result.ToolsConfigured = append(result.ToolsConfigured, pf.tool.Name)
		if len(pf.preservedNames) > 0 {
			if result.PreservedEntries == nil {
				result.PreservedEntries = make(map[string][]string)
			}
			result.PreservedEntries[pf.tool.Name] = pf.preservedNames
		}
	}

	return result, nil
}

// formatMismatchError renders the aggregated CLI-managed-URL-mismatch error.
// Single-tool and multi-tool forms have distinct headers and footers:
// single-tool pluralizes on entry count within one tool ("it"/"them",
// "entry"/"entries", "has"/"have") and says "the file"; multi-tool always
// uses "them" and says "each file". No leading "Error: " — the process
// entrypoint (main.go) prefixes all returned errors with that.
func formatMismatchError(mismatches []toolMismatches) error {
	var b strings.Builder
	if len(mismatches) == 1 {
		m := mismatches[0]
		n := len(m.Entries)
		entryWord := "entry"
		verb := "has"
		pronoun := "it"
		if n > 1 {
			entryWord = "entries"
			verb = "have"
			pronoun = "them"
		}
		fmt.Fprintf(&b, "%d CLI-managed %s in %s %s an unexpected URL:\n",
			n, entryWord, m.ConfigPath, verb)
		for _, e := range m.Entries {
			fmt.Fprintf(&b, "  - %s → %s\n", e.Name, e.URL)
		}
		fmt.Fprintln(&b)
		fmt.Fprintln(&b, "Options:")
		fmt.Fprintf(&b, "  - Preserve %s: edit the file to rename the %s, then re-run.\n", pronoun, entryWord)
		fmt.Fprintf(&b, "  - Replace %s:  re-run with --force.\n", pronoun)
	} else {
		fmt.Fprintf(&b, "unexpected URLs on CLI-managed entries in %d tools:\n\n", len(mismatches))
		for i, m := range mismatches {
			if i > 0 {
				fmt.Fprintln(&b)
			}
			fmt.Fprintf(&b, "%s (%s):\n", m.ToolName, m.ConfigPath)
			for _, e := range m.Entries {
				fmt.Fprintf(&b, "  - %s → %s\n", e.Name, e.URL)
			}
		}
		fmt.Fprintln(&b)
		fmt.Fprintln(&b, "Options:")
		fmt.Fprintln(&b, "  - Preserve them: edit each file to rename the mismatched entries, then re-run.")
		fmt.Fprintln(&b, "  - Replace them:  re-run with --force (applies to all tools in this run).")
	}
	return errors.New(strings.TrimRight(b.String(), "\n"))
}

// mintedToken records a server-side PAT created during a commit-phase run
// so we can revoke it if a subsequent step for the same tool fails.
type mintedToken struct {
	ID   string
	Name string
	// Token is the plaintext PAT. Used only to derive a last-4 prefix in
	// cleanup error messages.
	Token string
}

// toolPATResolution is the per-tool output of resolveToolPATs.
type toolPATResolution struct {
	ContentPAT string
	PromptPAT  string
	Minted     []mintedToken // revoke targets on failure
	Reused     []string      // "tool/serverType" labels for reused tokens
}

// resolveToolPATs determines the content and prompt PATs for a specific tool.
// For PAT auth: reuses the login token. For OAuth: reads existing CLI-managed
// PATs, validates them, creates new ones only when needed.
func resolveToolPATs(opts ConfigureOpts, handler ToolHandler, tool DetectedTool, rc ResolvedConfig, isPATAuth bool) (toolPATResolution, error) {
	var out toolPATResolution
	if isPATAuth {
		pat := opts.Client.Token
		if opts.wantServer(ServerContent) {
			out.ContentPAT = pat
		}
		if opts.wantServer(ServerPrompts) {
			out.PromptPAT = pat
		}
		return out, nil
	}

	ext := handler.ExtractPATs(rc)

	if opts.wantServer(ServerContent) {
		pat, minted, reused, err := resolveServerPAT(opts, tool.Name, ServerContent, ext.ContentPAT)
		if err != nil {
			return out, err
		}
		out.ContentPAT = pat
		if minted != nil {
			out.Minted = append(out.Minted, *minted)
		}
		if reused {
			out.Reused = append(out.Reused, fmt.Sprintf("%s/%s", tool.Name, ServerContent))
		}
	}
	if opts.wantServer(ServerPrompts) {
		pat, minted, reused, err := resolveServerPAT(opts, tool.Name, ServerPrompts, ext.PromptPAT)
		if err != nil {
			return out, err
		}
		out.PromptPAT = pat
		if minted != nil {
			out.Minted = append(out.Minted, *minted)
		}
		if reused {
			out.Reused = append(out.Reused, fmt.Sprintf("%s/%s", tool.Name, ServerPrompts))
		}
	}

	return out, nil
}

// resolveServerPAT resolves a single PAT for a specific server.
func resolveServerPAT(opts ConfigureOpts, toolName, serverType, existingPAT string) (pat string, minted *mintedToken, reused bool, err error) {
	if opts.DryRun {
		if existingPAT != "" {
			return existingPAT, nil, true, nil
		}
		return dryRunPlaceholder, nil, false, nil
	}

	if existingPAT != "" {
		valid, vErr := validatePAT(opts.Ctx, opts.Client.BaseURL, existingPAT)
		if vErr != nil {
			return "", nil, false, fmt.Errorf("checking existing %s token for %s: %w", serverType, toolName, vErr)
		}
		if valid {
			return existingPAT, nil, true, nil
		}
	}

	name := generateTokenName(toolName, serverType)
	resp, cErr := opts.Client.CreateToken(opts.Ctx, name, opts.ExpiresIn)
	if cErr != nil {
		return "", nil, false, fmt.Errorf("creating %s MCP token for %s: %w", serverType, toolName, cErr)
	}
	return resp.Token, &mintedToken{ID: resp.ID, Name: resp.Name, Token: resp.Token}, false, nil
}

// cleanupTimeout bounds the best-effort token-revoke window.
const cleanupTimeout = 10 * time.Second

// withRevokeError joins a commit-phase primary error with a revoke-failure
// error if cleanup also failed.
func withRevokeError(primary, revoke error) error {
	if revoke == nil {
		return primary
	}
	return errors.Join(primary, fmt.Errorf("cleanup partially failed: %w", revoke))
}

// revokeMintedTokens best-effort deletes the given server-side tokens by ID.
func revokeMintedTokens(ctx context.Context, client *api.Client, minted []mintedToken) error {
	if len(minted) == 0 {
		return nil
	}
	var orphans []string
	for _, m := range minted {
		if delErr := client.DeleteToken(ctx, m.ID); delErr != nil {
			prefix := PATPrefix(m.Token)
			if prefix == "" {
				// Defensive: tokens minted by the API are always long
				// enough; this branch only fires if an adversarial/mock
				// response returned something truncated. Fall back to
				// the whole token rather than printing "" which would
				// be confusing.
				prefix = m.Token
			}
			orphans = append(orphans, fmt.Sprintf("%s (prefix %s)", m.Name, prefix))
		}
	}
	if len(orphans) == 0 {
		return nil
	}
	return fmt.Errorf("failed to revoke %d minted token(s); clean up manually at https://tiddly.me/settings: %s",
		len(orphans), strings.Join(orphans, ", "))
}

// tokenNamePrefix is the prefix for all CLI-created MCP tokens.
const tokenNamePrefix = "cli-mcp-"

// generateTokenName creates a unique token name like "cli-mcp-claude-code-content-a1b2c3".
func generateTokenName(tool, server string) string {
	b := make([]byte, 3)
	_, _ = rand.Read(b)
	suffix := hex.EncodeToString(b)
	return fmt.Sprintf("%s%s-%s-%s", tokenNamePrefix, tool, server, suffix)
}

// validatePAT checks whether a PAT is still valid by calling GET /users/me.
// Returns (true, nil) if the token works (200).
// Returns (false, nil) if the token is definitively invalid (401).
// Returns (false, err) if validation couldn't be determined.
func validatePAT(ctx context.Context, baseURL, pat string) (bool, error) {
	client := api.NewClient(baseURL, pat, "pat")
	_, err := client.GetMe(ctx)
	if err == nil {
		return true, nil
	}
	if apiErr, ok := err.(*api.APIError); ok && apiErr.StatusCode == 401 {
		return false, nil
	}
	return false, fmt.Errorf("validating token: %w", err)
}

// TokenRevokeRequest names a PAT whose matching server-side tokens should be
// revoked. EntryLabel is a caller-chosen label (typically the canonical entry
// name) that the result is tagged with so the caller can surface a per-entry
// note when nothing matched.
type TokenRevokeRequest struct {
	EntryLabel string
	PAT        string
}

// TokenRevokeResult mirrors one input request. DeletedNames lists the
// cli-mcp-* token names revoked for this PAT (empty if nothing matched);
// Err is populated only for per-request failures — top-level errors from
// DeleteTokensByPrefix cover list-tokens failure.
type TokenRevokeResult struct {
	EntryLabel   string
	DeletedNames []string
	Err          error
}

// DeleteTokensByPrefix revokes server-side tokens whose token_prefix matches
// any input PAT and whose name starts with the cli-mcp- prefix (avoiding
// accidental deletion of user-created tokens that happen to share a prefix).
//
// Returns one result per input request in input order, preserving EntryLabels.
// Requests sharing a PAT are deduped internally: one deletion pass per unique
// PAT, with the resulting DeletedNames and Err mirrored into every matching
// result. Callers never see duplicate deletions or false "nothing matched"
// for shared PATs.
//
// For PATs too short to yield a prefix (see PATPrefix), the result has an empty
// DeletedNames and nil Err — treated as "nothing matched" so the caller can
// emit a per-entry note consistently. The top-level error is reserved for
// list-tokens failure.
func DeleteTokensByPrefix(ctx context.Context, client *api.Client, reqs []TokenRevokeRequest) ([]TokenRevokeResult, error) {
	results := make([]TokenRevokeResult, len(reqs))
	for i, r := range reqs {
		results[i].EntryLabel = r.EntryLabel
	}
	if len(reqs) == 0 {
		return results, nil
	}

	tokens, err := client.ListTokens(ctx)
	if err != nil {
		return nil, fmt.Errorf("listing tokens: %w", err)
	}

	// One deletion pass per unique PAT; mirror the outcome back to every
	// result whose PAT matches.
	type patOutcome struct {
		deleted []string
		err     error
	}
	byPAT := make(map[string]*patOutcome)
	for _, r := range reqs {
		if _, ok := byPAT[r.PAT]; ok {
			continue
		}
		o := &patOutcome{}
		if prefix := PATPrefix(r.PAT); prefix != "" {
			var perPATErrors []error
			for _, t := range tokens {
				if t.TokenPrefix == prefix && strings.HasPrefix(t.Name, tokenNamePrefix) {
					if delErr := client.DeleteToken(ctx, t.ID); delErr != nil {
						perPATErrors = append(perPATErrors, fmt.Errorf("deleting token %s: %w", t.Name, delErr))
					} else {
						o.deleted = append(o.deleted, t.Name)
					}
				}
			}
			if len(perPATErrors) > 0 {
				o.err = errors.Join(perPATErrors...)
			}
		}
		byPAT[r.PAT] = o
	}

	for i, r := range reqs {
		o := byPAT[r.PAT]
		results[i].DeletedNames = o.deleted
		results[i].Err = o.err
	}
	return results, nil
}

// bearerRE matches "Bearer bm_<token>" sequences in either JSON-escaped or
// raw form.
var bearerRE = regexp.MustCompile(`Bearer[ \t]+bm_[A-Za-z0-9_-]+`)

// redactBearers replaces every "Bearer bm_<token>" with "Bearer bm_REDACTED"
// so dry-run output never lands tokens in the user's terminal history.
func redactBearers(s string) string {
	return bearerRE.ReplaceAllString(s, "Bearer bm_REDACTED")
}

func printDiff(w io.Writer, path, before, after string) {
	fmt.Fprintf(w, "File: %s\n", path)
	if before == "" || before == "{}" || before == "{}\n" {
		fmt.Fprintln(w, "(new file)")
	} else {
		fmt.Fprintln(w, "Before:")
		fmt.Fprintln(w, redactBearers(before))
	}
	fmt.Fprintln(w, "After:")
	fmt.Fprintln(w, redactBearers(after))
}

// CheckOrphanedTokens returns server-side tokens matching the
// cli-mcp-{toolName}-{serverType}- name pattern. The caller must subtract
// tokens whose TokenPrefix matches a PAT still referenced by a retained
// entry on disk before presenting them as "potentially orphaned" —
// otherwise tokens in active use by non-canonical entries would be
// misreported.
//
// Known limitation: does not see repurposed canonical slots (canonical
// names at non-Tiddly URLs). A CLI-minted PAT pasted into such an entry
// may be reported as "potentially orphaned" even though it's still in use.
// Accepted pre-GA; see the plan document for context.
func CheckOrphanedTokens(ctx context.Context, client *api.Client, toolName string, serverTypes []string) ([]api.TokenInfo, error) {
	tokens, err := client.ListTokens(ctx)
	if err != nil {
		return nil, err
	}

	var prefixes []string
	for _, st := range serverTypes {
		prefixes = append(prefixes, fmt.Sprintf("%s%s-%s-", tokenNamePrefix, toolName, st))
	}
	if len(prefixes) == 0 {
		prefixes = []string{fmt.Sprintf("%s%s-", tokenNamePrefix, toolName)}
	}

	var orphaned []api.TokenInfo
	for _, t := range tokens {
		for _, p := range prefixes {
			if strings.HasPrefix(t.Name, p) {
				orphaned = append(orphaned, t)
				break
			}
		}
	}
	return orphaned, nil
}
