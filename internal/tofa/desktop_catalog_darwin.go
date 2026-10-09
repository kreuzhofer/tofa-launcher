package tofa

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"reflect"
	"strings"
	"time"
)

// Export before applying Token Factory overrides. The engine owns native auth,
// policy, cache freshness and descriptor resolution; model/list is a lossy
// picker projection and cannot be used to reconstruct these descriptors.
func prepareDesktopCatalog(ctx context.Context, bundle desktopBundle, home, electron, workspace string, models []string, guardian, runtimeDir string) (string, error) {
	ctx, cancel := context.WithTimeout(ctx, 30*time.Second)
	defer cancel()
	command := exec.CommandContext(ctx, bundle.engine, "debug", "models")
	command.Env, command.Dir = desktopEnv(home, electron, ""), workspace
	data, err := desktopCatalogOutput(command)
	if err != nil {
		return "", err
	}
	var native struct {
		Models []json.RawMessage `json:"models"`
	}
	if json.Unmarshal(data, &native) != nil || len(native.Models) == 0 {
		return "", errors.New("native model catalog is invalid or empty; launch cancelled")
	}
	if err := checkDesktopCatalogFreshness(ctx, bundle, home, electron, workspace, data); err != nil {
		return "", err
	}
	seen := make(map[string]bool)
	for _, model := range models {
		seen[model] = true
	}
	for _, raw := range native.Models {
		var descriptor struct{ Slug string }
		if json.Unmarshal(raw, &descriptor) != nil || !validText(descriptor.Slug, 256) || seen[descriptor.Slug] {
			return "", errors.New("native model catalog contains an invalid, duplicate or conflicting model identity; launch cancelled")
		}
		seen[descriptor.Slug] = true
	}
	// Preserve every native descriptor, including fields unknown to this launcher.
	// Each eligible Token Factory main uses the launch Guardian, including when
	// the same model is selected for both roles.
	entries := make([]any, 0, len(native.Models)+len(models))
	for _, raw := range native.Models {
		entries = append(entries, raw)
	}
	for _, identity := range models {
		entry, err := modelCatalogEntry(identity, guardian)
		if err != nil {
			return "", err
		}
		// THROWAWAY #117 experiment; confined to the three pilot Desktop mains.
		// Keep a selected Guardian's descriptor unchanged even if it is a pilot main.
		if identity != guardian && (identity == "zai-org/GLM-5.3" || identity == "moonshotai/Kimi-K3" || identity == "deepseek-ai/DeepSeek-V4.1-Flash") {
			prompt, err := prototypeDesktopMarkdownPrompt(codexPrompt)
			if err != nil {
				return "", err
			}
			entry["model_messages"] = map[string]any{"instructions_template": prompt}
		}
		status, err := selectionStatus("codex-desktop", "adapted", identity, guardian, true)
		if err != nil {
			return "", err
		}
		entry["description"] = "Token Factory main; " + status + "; Guardian: " + guardian
		if identity == "nvidia/Nemotron-3-Ultra-550b-a55b" {
			entry["display_name"] = "Nemotron 3 Ultra (Token Factory)"
		}
		if status != "supported" {
			entry["display_name"] = strings.TrimSuffix(entry["display_name"].(string), " (Token Factory)") + " (TF Experimental)"
		}
		entries = append(entries, entry)
	}
	catalog, err := writeModelCatalog(entries, runtimeDir)
	if err != nil {
		return "", err
	}
	return catalog, nil
}

// This is an experimental candidate only, not adopted production guidance.
func prototypeDesktopMarkdownPrompt(original string) (string, error) {
	before, section, found := strings.Cut(original, "**File References**")
	if !found {
		return "", errors.New("prototype file-reference section is missing")
	}
	_, after, found := strings.Cut(section, "**Structure**")
	if !found {
		return "", errors.New("prototype file-reference boundary is missing")
	}
	const replacement = `**File References**
For local document delivery, use a normal Markdown link: [document name](/absolute/path/to/document.ext).
Use the exact verified absolute path and put each deliverable in its own link.
This document-delivery rule takes precedence over the generic monospace rule above: do not wrap the link or its label in backticks, and do not return a bare path in place of the link.
If a path contains spaces, put angle brackets around the link target. Do not use file:// or vscode:// URLs.
Preserve existing files when asked; do not regenerate or upload them to make links. Do not claim that a preview opened unless the user confirms it.
For source-code references, use inline code with a relevant start line when known; do not provide a line range.

**Structure**`
	return before + replacement + after, nil
}

// debug models does not propagate remote refresh errors to its exit status (or
// reliably to stderr). For ChatGPT accounts, require its result to agree with a
// fresh engine cache. Do not parse or copy auth.json: login status is the pinned
// engine's public auth boundary. The engine owns cache identity validation.
func checkDesktopCatalogFreshness(ctx context.Context, bundle desktopBundle, home, electron, workspace string, exported []byte) error {
	command := exec.CommandContext(ctx, bundle.engine, "login", "status")
	command.Env, command.Dir = desktopEnv(home, electron, ""), workspace
	status, err := command.CombinedOutput()
	message := strings.TrimSpace(string(status))
	var exit *exec.ExitError
	if errors.As(err, &exit) && exit.ExitCode() == 1 && message == "Not logged in" {
		return nil // Bundled metadata is the engine's normal unauthenticated catalog.
	}
	if err == nil && strings.HasPrefix(message, "Logged in using an API key") {
		return nil // This engine's debug command does not enable API-key discovery.
	}
	if err != nil || message != "Logged in using ChatGPT" {
		return errors.New("could not establish native catalog authentication; check native engine login status, then relaunch")
	}
	unavailable := errors.New("native account catalog freshness could not be established; check ordinary model_catalog_json overrides (static catalogs bypass native discovery), refresh native models and relaunch; use launch codex if needed")
	file, err := os.Open(filepath.Join(home, "models_cache.json"))
	if err != nil {
		return unavailable
	}
	defer file.Close()
	data, err := io.ReadAll(io.LimitReader(file, (16<<20)+1))
	var cache struct {
		FetchedAt time.Time        `json:"fetched_at"`
		Identity  string           `json:"identity"`
		Version   string           `json:"client_version"`
		Models    []map[string]any `json:"models"`
	}
	var catalog struct {
		Models []map[string]any `json:"models"`
	}
	if err != nil || len(data) > 16<<20 || json.Unmarshal(data, &cache) != nil || json.Unmarshal(exported, &catalog) != nil {
		return unavailable
	}
	// ModelsResponse adds this legacy projection of model_messages when exporting;
	// FileModelsCache serializes ModelInfo without it. Compare canonical fields.
	for _, descriptor := range catalog.Models {
		delete(descriptor, "base_instructions")
	}
	age := time.Since(cache.FetchedAt)
	if age < 0 || age > 5*time.Minute || cache.Identity == "" || cache.Version != bundle.catalogVersion || !reflect.DeepEqual(cache.Models, catalog.Models) {
		return unavailable
	}
	// A rejected foreign cache can happen to contain the same descriptors as
	// the bundled fallback. The export has no refresh-success attestation, so
	// refuse this ambiguous case even if a real account catalog is identical.
	command = exec.CommandContext(ctx, bundle.engine, "debug", "models", "--bundled")
	command.Env, command.Dir = desktopEnv(home, electron, ""), workspace
	data, err = desktopCatalogOutput(command)
	var bundled struct {
		Models []map[string]any `json:"models"`
	}
	if err != nil || json.Unmarshal(data, &bundled) != nil {
		return unavailable
	}
	for _, descriptor := range bundled.Models {
		delete(descriptor, "base_instructions")
	}
	if reflect.DeepEqual(bundled.Models, catalog.Models) {
		return errors.New("native account catalog freshness is ambiguous: engine returned bundled-identical metadata; this account catalog cannot be qualified for a desktop launch")
	}
	return nil
}

// Bound native output and suppress account-bearing diagnostics at this boundary.
func desktopCatalogOutput(command *exec.Cmd) ([]byte, error) {
	var diagnostics bytes.Buffer
	command.Stderr = &diagnostics
	stdout, err := command.StdoutPipe()
	if err != nil {
		return nil, err
	}
	if err := command.Start(); err != nil {
		return nil, errors.New("could not start native model catalog discovery")
	}
	const limit = 16 << 20
	data, readErr := io.ReadAll(io.LimitReader(stdout, limit+1))
	if readErr != nil || len(data) > limit {
		command.Process.Kill()
	}
	err = command.Wait()
	// The engine can log refresh failure and still exit successfully with bundled
	// metadata. Refuse diagnostic-bearing exports rather than silently freezing
	// that fallback. Never echo diagnostics: they can contain account details.
	if err != nil || readErr != nil || len(data) > limit || diagnostics.Len() != 0 {
		return nil, errors.New("native model catalog discovery failed; check native engine configuration and catalog connectivity, then relaunch")
	}
	return data, nil
}
