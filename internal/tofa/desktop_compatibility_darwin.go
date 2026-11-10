package tofa

import (
	"context"
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"time"
)

// A diagnostic snapshot, never an admission proof or bearer capability. Launch
// must recheck live ownership/account/configuration and apply its existing gate.
type desktopCompatibilityReport struct {
	Schema           string            `json:"schema"`
	Status           string            `json:"status"`
	Checked          time.Time         `json:"checked_utc"`
	ReleaseQualified bool              `json:"release_qualified"`
	Identity         map[string]string `json:"identity"`
	Checks           map[string]string `json:"checks"`
	Unobserved       []string          `json:"unobserved"`
}

func (a *App) desktopCompatibility(ctx context.Context, args []string) error {
	fs := flags("desktop-compatibility")
	path := fs.String("app-bundle", "", "")
	if err := fs.Parse(args); err != nil {
		return err
	}
	if fs.NArg() != 0 {
		return errors.New("desktop-compatibility accepts only --app-bundle PATH")
	}
	ctx, cancel := context.WithTimeout(ctx, 30*time.Second)
	defer cancel()
	bundle, err := discoverDesktop(ctx, *path)
	if err != nil {
		return err
	}
	profile, err := ordinaryDesktopProfile()
	if err != nil {
		return err
	}
	if err = checkDesktopDiagnosticOwnership(ctx, profile); err != nil {
		return err
	}
	home, err := desktopHome(ctx)
	if err != nil {
		return err
	}
	// Do not create a user home or repair shared state during a diagnostic.
	info, err := os.Lstat(home)
	if err != nil || !info.IsDir() {
		return errors.New("ordinary Codex home must be an existing directory; open ordinary Desktop and sign in first")
	}
	workspace, err := os.Getwd()
	if err != nil {
		return err
	}
	root, err := os.MkdirTemp("", "tofa-compatibility-")
	if err != nil {
		return err
	}
	defer os.RemoveAll(root)
	if err = checkDesktopNativeAccount(ctx, bundle.engine, home, profile, workspace, root); err != nil {
		return err
	}
	client, err := openDesktopConfig(ctx, bundle.engine, home, profile, workspace, root)
	if err != nil {
		return err
	}
	_, _, err = client.inspectConfiguration(workspace, true, true)
	client.close()
	if err != nil {
		return err
	}
	if _, err = desktopSecretExclusions(ctx, bundle.engine, home, profile, workspace, root); err != nil {
		return err
	}
	launcher, err := os.Executable()
	if err != nil {
		return errors.New("could not identify this launcher")
	}
	identity := map[string]string{}
	for key, path := range map[string]string{"launcher_sha256": launcher, "engine_sha256": bundle.engine, "application_sha256": bundle.executable, "bundle_sha256": filepath.Join(filepath.Dir(filepath.Dir(bundle.executable)), "Info.plist")} {
		hash, e := hashAdmissionFile(path)
		if e != nil {
			return errors.New("could not record installed Desktop identity")
		}
		identity[key] = hash
	}
	// Refusal checks are repeated to catch an incumbent appearing during probes.
	if err = checkDesktopDiagnosticOwnership(ctx, profile); err != nil {
		return err
	}
	return json.NewEncoder(a.Out).Encode(desktopCompatibilityReport{
		Schema: "tofa-desktop-compatibility-v1", Status: "compatible", Checked: time.Now().UTC(), Identity: identity,
		Checks:     map[string]string{"platform-layout": "passed", "ownership": "passed", "account-policy": "passed", "provider-configuration": "passed", "secret-exclusion": "passed"},
		Unobserved: []string{"native-ui", "routing-turns", "model-availability", "release-qualification"},
	})
}
