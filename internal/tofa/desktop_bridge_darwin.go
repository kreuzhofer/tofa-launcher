package tofa

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"slices"
	"strconv"
	"strings"
	"syscall"
	"time"
)

const desktopBridgeName = "tofa-desktop-engine"

// This versioned ownership record contains installation data only, never routing.
type desktopBridgeOwner struct {
	Version int
	Engine  string
	SHA256  string
	// A write-ahead digest makes either side of an interrupted executable
	// replacement verifiable. Old bridges still recognize SHA256 before rename.
	PendingSHA256    string `json:",omitempty"`
	Detached         bool   `json:",omitempty"`
	LifecycleVersion int    `json:",omitempty"`
}

func desktopBridgePath(dir, engine string) string {
	id := sha256.Sum256([]byte(engine))
	return filepath.Join(dir, "desktop-bridge-v2", hex.EncodeToString(id[:]), desktopBridgeName)
}

func readDesktopBridge(path string) (desktopBridgeOwner, error) {
	var owner desktopBridgeOwner
	data, err := readPrivate(filepath.Join(filepath.Dir(path), "owner.json"))
	if err != nil || json.Unmarshal(data, &owner) != nil || (owner.Version != 1 && owner.Version != 2) || (owner.LifecycleVersion != 0 && owner.LifecycleVersion != 1) || !filepath.IsAbs(owner.Engine) {
		return owner, errors.New("desktop bridge ownership is missing or incompatible; restore its matching owner.json and executable or move the conflicting directory aside, then reinstall tofa; refusing to replace an unmanaged executable")
	}
	binary, err := readPrivate(path)
	if err != nil {
		return owner, err
	}
	digest := sha256.Sum256(binary)
	if hex.EncodeToString(digest[:]) != owner.SHA256 && hex.EncodeToString(digest[:]) != owner.PendingSHA256 {
		return owner, errors.New("desktop bridge executable differs from its ownership record; refusing to replace it")
	}
	owner.SHA256 = hex.EncodeToString(digest[:])
	return owner, nil
}

func installDesktopBridge(dir, engine string) (path string, result error) {
	path = desktopBridgePath(dir, engine)
	if override, ok := os.LookupEnv("CODEX_CLI_PATH"); ok && override != "" && override != path {
		return "", errors.New("CODEX_CLI_PATH is a user-managed executable override; unset it before launching codex-desktop")
	}
	parent := filepath.Dir(filepath.Dir(path))
	if err := privateDir(parent); err != nil {
		return "", err
	}
	root := filepath.Dir(path)
	if err := os.Mkdir(root, 0700); errors.Is(err, os.ErrExist) {
		info, statErr := os.Lstat(root)
		if statErr != nil || !info.IsDir() || info.Mode().Perm()&0077 != 0 {
			return "", errors.New("desktop bridge directory must be a private, real directory")
		}
		owner, err := readDesktopBridge(path)
		if err != nil {
			return "", err
		}
		if owner.Engine != engine {
			return "", errors.New("desktop bridge belongs to a different bundled engine")
		}
		if err := replaceDesktopBridge(path, owner, false); err != nil {
			return "", err
		}
		return path, nil
	} else if err != nil {
		return "", err
	}
	// Only a directory created by this invocation is eligible for setup rollback.
	defer func() {
		if result != nil {
			result = errors.Join(result, os.RemoveAll(root))
		}
	}()
	executable, err := os.Executable()
	if err != nil {
		return "", err
	}
	source, err := os.Open(executable)
	if err != nil {
		return "", err
	}
	defer source.Close()
	target, err := os.OpenFile(path, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0700)
	if err != nil {
		return "", err
	}
	digest := sha256.New()
	_, copyErr := io.Copy(io.MultiWriter(target, digest), source)
	if err := errors.Join(copyErr, target.Close()); err != nil {
		return "", err
	}
	owner, err := json.Marshal(desktopBridgeOwner{Version: 2, Engine: engine, SHA256: hex.EncodeToString(digest.Sum(nil)), LifecycleVersion: 1})
	if err != nil {
		return "", err
	}
	if err := os.WriteFile(filepath.Join(root, "owner.json"), owner, 0600); err != nil {
		return "", err
	}
	return path, nil
}

func runDesktopBridge(args []string) error {
	path, err := os.Executable()
	if err != nil {
		return err
	}
	owner, err := readDesktopBridge(path)
	if err != nil {
		return err
	}
	if len(args) > 0 && args[0] == "--tofa-desktop-settings-relay" {
		return runDesktopSettingsRelay(args[1:])
	}
	// A retained, verified bridge also supplies the standalone uninstaller's
	// recovery coordinator after the main launcher executable has been removed.
	if len(args) > 0 && args[0] == "--tofa-installed-lifecycle" {
		app := App{Dir: filepath.Dir(filepath.Dir(filepath.Dir(path))), Out: os.Stdout}
		return app.desktopLifecycle(context.Background(), args[1:])
	}
	env := os.Environ()
	engine := owner.Engine
	if endpoint, present := os.LookupEnv("TOFA_DESKTOP_CONTEXT"); present {
		if owner.Detached {
			return errors.New("tofa is uninstalled; this saved engine reference supports ordinary history only. Reinstall tofa and relaunch to continue Token Factory conversations")
		}
		route, err := fetchDesktopRoute(endpoint, os.Getenv("TOFA_API_KEY"), 0)
		if err != nil {
			return err
		}
		if route.Bridge != path || route.Engine != owner.Engine || route.Home != os.Getenv("CODEX_HOME") {
			return errors.New("desktop launch context does not match this bridge or home; relaunch through tofa")
		}
		// Codex's app-server has its own -c parser. Global -c values can be
		// displaced when Electron supplies any subcommand overrides.
		if index := desktopAppServerIndex(args); index >= 0 {
			end := len(args)
			if separator := slices.Index(args[index+1:], "--"); separator >= 0 {
				end = index + 1 + separator
			}
			merged := append([]string{}, args[:end]...)
			for _, value := range route.Overrides {
				merged = append(merged, "-c", value)
			}
			args = append(merged, args[end:]...)
			return runDesktopSettingsBridge(owner.Engine, args, env, route.Home, route.InferenceCapability)
		}
	} else {
		// An ordinary invocation must not revive inactive Token Factory metadata
		// using a bearer inherited from an earlier launch.
		env = slices.DeleteFunc(env, func(entry string) bool {
			return strings.HasPrefix(entry, "TOFA_API_KEY=") || strings.HasPrefix(entry, "TOFA_DESKTOP_INACTIVE=") || strings.HasPrefix(entry, nativeDesktopInferenceEnv+"=")
		})
		// Saved ordinary references survive known bundle layout changes. Keep the
		// recorded identity immutable; active launches use their own current bridge.
		if _, err := os.Stat(engine); errors.Is(err, os.ErrNotExist) {
			root, err := desktopBundlePath(engine)
			if err != nil {
				return err
			}
			bundle, err := discoverDesktop(context.Background(), root)
			if err != nil {
				return fmt.Errorf("saved desktop engine moved but its replacement is incompatible: %w", err)
			}
			engine = bundle.engine
			fmt.Fprintln(os.Stderr, "tofa: desktop engine moved; saved reference now uses the compatible engine in the same app bundle")
		}

		if desktopAppServerIndex(args) >= 0 {
			workspace, err := os.Getwd()
			if err != nil {
				return err
			}
			root, err := os.MkdirTemp(filepath.Dir(path), "ordinary-provider-check-")
			if err != nil {
				return errors.New("could not inspect ordinary routed-history metadata; relaunch through tofa")
			}
			home := os.Getenv("CODEX_HOME")
			if home == "" {
				userHome, err := os.UserHomeDir()
				if err != nil {
					os.RemoveAll(root)
					return err
				}
				home = filepath.Join(userHome, ".codex")
			}
			end := len(args)
			if separator := slices.Index(args, "--"); separator >= 0 {
				end = separator
			}
			overrides, inspectErr := ordinaryNativeDesktopOverrides(engine, home, workspace, root, args[:end])
			os.RemoveAll(root)
			if inspectErr != nil {
				return inspectErr
			}
			merged := append([]string{}, args[:end]...)
			for _, override := range overrides {
				merged = append(merged, "-c", override)
			}
			args = append(merged, args[end:]...)
		}
	}
	if err := syscall.Exec(engine, append([]string{engine}, args...), env); err != nil {
		return fmt.Errorf("desktop bridge could not execute the installed bundled engine: %w", err)
	}
	return nil
}

// The pinned desktop prefixes app-server with global config/feature options.
// Stop at any other command, prompt, or separator; argument values are never
// subcommands. Unrecognized invocation shapes are passed to Codex unchanged.
func desktopAppServerIndex(args []string) int {
	for index := 0; index < len(args); index++ {
		arg := args[index]
		switch arg {
		case "app-server":
			return index
		case "-c", "--config", "--enable", "--disable":
			index++
		case "--strict-config":
		default:
			if !strings.HasPrefix(arg, "--config=") && !strings.HasPrefix(arg, "--enable=") && !strings.HasPrefix(arg, "--disable=") && !(strings.HasPrefix(arg, "-c") && len(arg) > 2) {
				return -1
			}
		}
	}
	return -1
}

func fetchDesktopRoute(endpoint, token string, mainPID int) (desktopRoute, error) {
	return fetchDesktopRouteForParent(endpoint, token, mainPID, os.Getppid())
}

func fetchDesktopRouteForParent(endpoint, token string, mainPID, parentPID int) (desktopRoute, error) {
	var route desktopRoute
	invalid := errors.New("desktop launch context is invalid or expired; relaunch through tofa")
	u, err := url.Parse(endpoint)
	if err != nil || u.Scheme != "http" || u.Hostname() != "127.0.0.1" || u.User != nil || u.Path != "" || u.RawQuery != "" || u.Fragment != "" {
		return route, invalid
	}
	port, err := strconv.Atoi(u.Port())
	if err != nil || port < 1 || port > 65535 {
		return route, invalid
	}
	credential, err := hex.DecodeString(token)
	if err != nil || len(credential) != 32 {
		return route, invalid
	}
	request, err := http.NewRequest(http.MethodGet, endpoint+"/desktop-launch", nil)
	if err != nil {
		return route, invalid
	}
	request.Header.Set("Authorization", "Bearer "+token)
	request.Header.Set("X-Tofa-Parent-Pid", strconv.Itoa(parentPID))
	if mainPID != 0 {
		request.Header.Set("X-Tofa-Main-Engine-Pid", strconv.Itoa(mainPID))
	}
	transport := &http.Transport{Proxy: nil}
	defer transport.CloseIdleConnections()
	client := &http.Client{Transport: transport, Timeout: 45 * time.Second, CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }}
	response, err := client.Do(request)
	if err != nil {
		return route, invalid
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK || json.NewDecoder(io.LimitReader(response.Body, 64<<10)).Decode(&route) != nil || len(route.Overrides) == 0 {
		return route, invalid
	}
	return route, nil
}
