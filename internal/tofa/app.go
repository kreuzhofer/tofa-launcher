// Package tofa implements the experimental Token Factory launcher.
package tofa

import (
	"context"
	"errors"
	"flag"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"os/exec"
	"os/signal"
	"path/filepath"
	"strconv"
	"strings"
	"syscall"

	"golang.org/x/term"
)

type App struct {
	Out     io.Writer
	Version string
	Dir     string
	Vault   Vault
	// Endpoint and HTTP exist for local protocol tests. The CLI never overrides the endpoint.
	Endpoint  string
	HTTP      *http.Client
	Listen    func(network, address string) (net.Listener, error)
	RunClient func(args, env []string) error
	Prompt    func(label string, secret bool) (string, error)
	Uninstall func(purge bool) error
}

const help = `tofa — Token Factory launcher (prototype)

  tofa [--allow-unverified]                  Choose an app, then a main model
  tofa auth login [--storage keyring|file]   Save API key and project ID
  tofa auth logout                          Remove locally saved credentials
  tofa models [--project-id ID]              List available models
  tofa launch codex [--model ID] [--guardian-model ID] [--project-id ID] [--allow-unverified] [--direct] [-- ARGS]
  tofa launch codex-desktop [--model ID] [--guardian-model ID] [--project-id ID] [--allow-unverified] [--app-bundle PATH]
  tofa doctor                               Check local prerequisites; no inference
  tofa uninstall [--purge]                   Remove installation; optionally saved data
  tofa --version

Supported desktop pairs: deepseek-ai/DeepSeek-V4.1-Flash or zai-org/GLM-5.3 main
with zai-org/GLM-5.3-Flash Guardian, on the pinned macOS desktop adapted route.
Automatic naming remains unsupported for these mains. See docs/codex-desktop.md
for tested versions and evidence limits. Desktop experimental models are always enabled
and labelled Experimental. The desktop picker offers every eligible available model;
--model sets the initial/default main and each conversation keeps its own selection.
Supported CLI mains on macOS ARM64: deepseek-ai/DeepSeek-V4.1-Flash,
zai-org/GLM-5.3, moonshotai/Kimi-K3, each with zai-org/GLM-5.3-Flash Guardian
on the adapted route. Windows ARM64 also supports DeepSeek V4.1 Flash and Kimi K3
with that Guardian and route. Other CLI combinations remain Experimental.
See docs/evaluation/cli-windows-2026-10-05.md for baselines and evidence limits.
Experimental CLI pairs need consent: confirm Y in the picker, or pass
--allow-unverified for explicit/scripted models.
Models in the catalog are not certified by availability.
Fresh interactive launches run first-use setup and authenticate the catalog before selection.
Existing logins skip setup. Interactive bare launches choose Codex CLI or Codex desktop.
Omit --model to choose its main model next; Up/Down and Enter select, Escape/Ctrl-C cancels.
Scripts must supply --model ID. Saved model preferences never bypass the picker.
Both selected roles must be available in the project and have compatible model metadata.
Adapted Codex CLI and desktop launches default to Guardian zai-org/GLM-5.3-Flash; --guardian-model
selects an override, with no Guardian prompt or substitution if unavailable.
Launch uses a per-launch Responses request adapter. --direct bypasses it explicitly,
preserves native reviewer selection, and rejects --guardian-model.

Login reuses a saved storage choice. Fresh logins prefer the native credential vault.
Only an absent or unsupported vault facility selects an unencrypted credentials file
automatically, with its location shown before input. Locked, denied, uncertain, or
failed vault operations are errors. Override with --storage keyring or --storage file.
`

func (a *App) Run(args []string) error {
	return a.RunContext(context.Background(), args)
}

func (a *App) RunContext(ctx context.Context, args []string) error {
	if err := ctx.Err(); err != nil {
		return err
	}
	if executable, err := os.Executable(); err == nil && filepath.Base(executable) == "tofa-desktop-engine" {
		return runDesktopBridge(args)
	}
	if a.Out == nil {
		a.Out = os.Stdout
	}
	if a.Vault == nil {
		a.Vault = NativeVault{}
	}
	if len(args) == 1 && args[0] == "--version" {
		_, err := fmt.Fprintln(a.Out, "tofa", a.Version)
		return err
	}
	if len(args) == 1 && (args[0] == "--help" || args[0] == "help" || args[0] == "-h") {
		fmt.Fprint(a.Out, help)
		return nil
	}
	if a.Dir == "" {
		var err error
		a.Dir, err = ConfigDir()
		if err != nil {
			return err
		}
	}
	s := Store{Dir: a.Dir, Vault: a.Vault}
	if len(args) == 0 || strings.HasPrefix(args[0], "--") {
		target := "codex"
		if term.IsTerminal(int(os.Stdin.Fd())) {
			options, err := parseLaunchOptions("", args)
			if err != nil {
				return err
			}
			if err := a.onboard(ctx, s, options.project); err != nil {
				return err
			}
			target, err = a.pickTargetClient(ctx)
			if err != nil {
				return err
			}
		}
		return a.launch(ctx, s, append([]string{target}, args...))
	}
	switch args[0] {
	case "desktop-lifecycle":
		return a.desktopLifecycle(ctx, args[1:])
	case "auth":
		if len(args) < 2 {
			return errors.New("use tofa auth login or tofa auth logout")
		}
		if args[1] == "logout" && len(args) == 2 {
			if err := s.Logout(); err != nil {
				return err
			}
			fmt.Fprintln(a.Out, "Local credentials removed. Preferences retained; the Nebius API key remains valid.")
			return nil
		}
		if args[1] != "login" {
			return errors.New("use tofa auth login or tofa auth logout")
		}
		return a.login(s, args[2:])
	case "models":
		fs := flags("models")
		project := fs.String("project-id", "", "")
		if err := fs.Parse(args[1:]); err != nil {
			return err
		}
		if fs.NArg() != 0 {
			return errors.New("unexpected models argument")
		}
		c, key, err := s.Credentials()
		if err != nil {
			return err
		}
		if *project != "" {
			c.ProjectID = *project
		}
		if !validText(c.ProjectID, 256) {
			return errors.New("invalid project ID")
		}
		models, err := a.models(c.ProjectID, key)
		if err != nil {
			return err
		}
		fmt.Fprintln(a.Out, "MODEL\tCODEX COMPATIBILITY")
		for _, m := range models {
			fmt.Fprintln(a.Out, m.ID+"\tunverified")
		}
		if len(models) == 0 {
			fmt.Fprintln(a.Out, "No models available for this project.")
		}
		return nil
	case "launch":
		return a.launch(ctx, s, args[1:])
	case "doctor":
		if len(args) != 1 {
			return errors.New("doctor takes no arguments")
		}
		fmt.Fprintln(a.Out, "Local checks only; no network request or inference.")
		c, err := s.Config()
		if err != nil {
			return err
		}
		fmt.Fprintln(a.Out, "Configuration:", a.Dir)
		if c.Reference == "" {
			return errors.New("no saved login; run tofa auth login")
		}
		fmt.Fprintf(a.Out, "Credential backend: %s (access not tested; no keychain prompt)\n", c.Backend)
		if _, err = exec.LookPath("codex"); err != nil {
			return errors.New("Codex CLI not found on PATH")
		}
		fmt.Fprintln(a.Out, "Codex CLI found. Live protocol/model compatibility remains unverified.")
		return nil
	case "uninstall":
		fs := flags("uninstall")
		purge := fs.Bool("purge", false, "")
		if err := fs.Parse(args[1:]); err != nil {
			return err
		}
		if fs.NArg() != 0 {
			return errors.New("unexpected uninstall argument")
		}
		if a.Uninstall == nil {
			return errors.New("uninstall is unavailable in this build; use the standalone uninstall script")
		}
		return a.Uninstall(*purge)
	}
	return errors.New("unknown command; run tofa --help")
}
func flags(name string) *flag.FlagSet {
	fs := flag.NewFlagSet(name, flag.ContinueOnError)
	fs.SetOutput(io.Discard)
	return fs
}
func (a *App) ask(label string, secret bool) (string, error) {
	if a.Prompt != nil {
		return a.Prompt(label, secret)
	}
	if !term.IsTerminal(int(os.Stdin.Fd())) {
		return "", errors.New("interactive terminal required; run tofa auth login in a terminal")
	}
	fmt.Fprint(a.Out, label+": ")
	if secret {
		b, err := readPassword(a.Out)
		fmt.Fprintln(a.Out)
		if err != nil {
			return "", errors.New("credential input cancelled")
		}
		return strings.TrimSpace(string(b)), nil
	}
	// Read one byte at a time: a buffered reader must not consume the next prompt's input.
	var b strings.Builder
	for {
		one := make([]byte, 1)
		n, err := os.Stdin.Read(one)
		if err != nil || n == 0 {
			return "", errors.New("input cancelled")
		}
		if one[0] == '\n' {
			break
		}
		if b.Len() > 4096 {
			return "", errors.New("input too long")
		}
		b.WriteByte(one[0])
	}
	return strings.TrimSpace(b.String()), nil
}
func (a *App) launch(ctx context.Context, s Store, args []string) (result error) {
	if len(args) > 0 && args[0] == "codex-desktop" {
		return a.launchDesktop(ctx, s, args[1:])
	}
	if len(args) == 0 || args[0] != "codex" {
		return errors.New("only Codex CLI is available in this prototype")
	}
	options, err := parseLaunchOptions("codex", args[1:])
	if err != nil {
		return err
	}
	model, guardian, project := &options.model, &options.guardian, &options.project
	allow, direct := &options.allow, &options.direct
	modelSelected, extra := options.modelSelected, options.extra

	if !modelSelected && !term.IsTerminal(int(os.Stdin.Fd())) {
		return errors.New("noninteractive launch requires --model ID; use tofa launch codex --model ID (and --allow-unverified for experimental selection); for first use, run tofa auth login in a terminal")
	}
	if err := a.onboard(ctx, s, *project); err != nil {
		return err
	}
	c, key, err := s.Credentials()
	if err != nil {
		return err
	}
	if *project != "" {
		c.ProjectID = *project
	}
	if modelSelected && !validText(*model, 512) {
		return errors.New("specify a valid --model ID; see tofa models")
	}
	if !validText(c.ProjectID, 256) {
		return errors.New("invalid project ID")
	}
	child, err := childArgs(*model, c.ProjectID, Endpoint, extra)
	if err != nil {
		return err
	}
	runner := a.RunClient
	if runner == nil {
		if _, err = exec.LookPath("codex"); err != nil {
			return errors.New("Codex CLI not found on PATH; install it first")
		}
	}
	models, err := a.models(c.ProjectID, key)
	if err != nil {
		return err
	}
	if len(models) == 0 {
		return errors.New("no models available in this project's catalog")
	}
	if *guardian != "" {
		if err := validateAvailableRole(models, "Guardian", *guardian); err != nil {
			return err
		}
	}
	route := "adapted"
	if *direct {
		route = "direct"
	}
	if !modelSelected {
		choices, err := mainModelChoices(models, "codex", route, *guardian, true)
		if err != nil {
			return err
		}
		*model, err = a.pickMainModel(ctx, choices, "Codex CLI", route, *guardian, *allow)
		if err != nil {
			return err
		}
		// The picker requires explicit consent for experimental selections.
		*allow = true
	}
	if err := validateAvailableRole(models, "main", *model); err != nil {
		return err
	}
	child, err = childArgs(*model, c.ProjectID, Endpoint, extra)
	if err != nil {
		return err
	}
	status, err := selectionStatus("codex", route, *model, *guardian, *allow)
	if err != nil {
		return err
	}
	catalog, err := prepareModelCatalog(*model, *guardian)
	if err != nil {
		return err
	}
	if catalog != "" {
		defer func() {
			if err := os.Remove(catalog); err != nil {
				fmt.Fprintln(a.Out, "Could not remove temporary model catalog:", catalog)
				if result == nil {
					result = errors.New("temporary model catalog cleanup failed")
				}
			}
		}()
		fmt.Fprintln(a.Out, "Model metadata: bundled candidate catalog (provider snapshot 2026-09-23).")
	}
	run := func(ctx context.Context, args, env []string) error {
		if catalog != "" {
			args = append([]string{"-c", "model_catalog_json=" + strconv.Quote(catalog)}, args...)
		}
		if runner == nil {
			return runClient(ctx, args, env)
		}
		return runner(args, env)
	}
	fmt.Fprintf(a.Out, "Launching Codex, project %s.\nMain: %s\nStatus: %s\n", c.ProjectID, *model, status)
	if *direct {
		fmt.Fprintln(a.Out, "Guardian: native reviewer selection (Codex client).")
	} else {
		fmt.Fprintf(a.Out, "Guardian: %s\nRoute: adapted Token Factory connection.\n", *guardian)
	}
	ctx, stop := signal.NotifyContext(ctx, os.Interrupt, syscall.SIGTERM)
	defer stop()
	if *direct {
		fmt.Fprintln(a.Out, "Route: direct Token Factory connection (--direct); no request adaptation.")
		return run(ctx, child, childEnv(key))
	}
	adapter, err := a.startAdapter(ctx, c.ProjectID, key, "", "")
	if err != nil {
		return err
	}
	defer adapter.close()
	child, err = childArgs(*model, "", adapter.endpoint, extra)
	if err != nil {
		adapter.close()
		return err
	}
	err = run(adapter.context, child, childEnv(adapter.token))
	cleanupErr := adapter.close()
	if serveErr := <-adapter.done; serveErr != nil {
		return errors.New("request adapter stopped unexpectedly; Codex launch cancelled")
	}
	if cleanupErr != nil {
		return cleanupErr
	}
	if err == nil && ctx.Err() != nil {
		return ctx.Err()
	}
	return err
}

// Intercept cancellation while terminal echo is disabled, restoring state before
// returning. The process exits after this error; no subsequent prompt is started.
func readPassword(out io.Writer) ([]byte, error) {
	fd := int(os.Stdin.Fd())
	signals := make(chan os.Signal, 1)
	signal.Notify(signals, os.Interrupt, syscall.SIGTERM)
	defer signal.Stop(signals)
	state, err := term.MakeRaw(fd)
	if err != nil {
		return nil, err
	}
	defer term.Restore(fd, state)
	type result struct {
		value []byte
		err   error
	}
	done := make(chan result, 1)
	go func() {
		value := []byte{}
		for {
			var ch [1]byte
			if _, e := os.Stdin.Read(ch[:]); e != nil {
				done <- result{nil, e}
				return
			}
			switch ch[0] {
			case 3, 4:
				done <- result{nil, errors.New("input cancelled")}
				return
			case 10, 13:
				done <- result{value, nil}
				return
			case 8, 127:
				if len(value) > 0 {
					value = value[:len(value)-1]
					if _, e := io.WriteString(out, "\b \b"); e != nil {
						done <- result{nil, e}
						return
					}
				}
			default:
				if len(value) >= 2048 {
					done <- result{nil, errors.New("key too long")}
					return
				}
				value = append(value, ch[0])
				if _, e := io.WriteString(out, "*"); e != nil {
					done <- result{nil, e}
					return
				}
			}
		}
	}()
	select {
	case r := <-done:
		return r.value, r.err
	case <-signals:
		return nil, errors.New("credential input cancelled")
	}
}
