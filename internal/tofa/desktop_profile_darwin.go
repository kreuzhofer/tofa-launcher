package tofa

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"reflect"
	"strconv"
	"strings"
	"syscall"
	"time"
)

// The qualified native shell acquires Chromium's profile singleton before
// Electron bootstrap. Never remove or rewrite its lock/socket/cookie.
func ordinaryDesktopProfile() (string, error) {
	home, err := os.UserHomeDir()
	if err != nil {
		return "", err
	}
	return filepath.Join(home, "Library", "Application Support", "Codex"), nil
}

// Keep the lease inode durable: unlinking it would allow a waiter and a later
// launcher to lock different files. This is separate from the native singleton.
func acquireDesktopLease(profile string) (*os.File, error) {
	if err := os.MkdirAll(profile, 0700); err != nil {
		return nil, err
	}
	info, err := os.Lstat(profile)
	if err != nil || !info.IsDir() {
		return nil, errors.New("ordinary desktop profile must be a real directory; resolve the profile path before launching")
	}
	fd, err := syscall.Open(filepath.Join(profile, ".tofa-launch.lock"), syscall.O_CREAT|syscall.O_RDWR|syscall.O_NOFOLLOW|syscall.O_CLOEXEC, 0600)
	if err != nil {
		return nil, errors.New("could not acquire ordinary desktop launcher lease")
	}
	file := os.NewFile(uintptr(fd), "desktop-profile-lease")
	if err := syscall.Flock(fd, syscall.LOCK_EX|syscall.LOCK_NB); err != nil {
		file.Close()
		return nil, errors.New("another tofa launch owns the ordinary desktop profile; wait for it to exit before relaunching")
	}
	if err := refuseDesktopOwner(profile); err != nil {
		file.Close()
		return nil, err
	}
	return file, nil
}

const legacyDesktopRecovery = "Token Factory is unavailable in ordinary mode. Relaunch through tofa with --model moonshotai/Kimi-K3 --allow-unverified; choosing GPT does not migrate this conversation."

const selectedMainDesktopRecovery = "Token Factory is unavailable in ordinary mode. Relaunch through tofa with the conversation's original main model: --model ID --allow-unverified; choosing GPT does not migrate this conversation."

var inactiveDesktopProvider = map[string]any{
	"name": "Nebius Token Factory", "base_url": "http://127.0.0.1:0",
	"env_key": "TOFA_DESKTOP_INACTIVE", "wire_api": "responses",
	"env_key_instructions": "Token Factory is unavailable in ordinary mode. Relaunch through tofa with any default main model, then reopen this conversation; choosing GPT does not migrate its provider.",
	"requires_openai_auth": false, "supports_websockets": false,
	"request_max_retries": float64(0), "stream_max_retries": float64(0),
}

// The engine owns TOML parsing, policy discovery and version-checked edits.
// Only its public configuration API is used; no credentials or history are read.
type desktopConfigClient struct {
	command *exec.Cmd
	input   io.WriteCloser
	encoder *json.Encoder
	decoder *json.Decoder
	id      int
}

func openDesktopConfig(ctx context.Context, engine, home, profile, workspace, runtimeDir string) (*desktopConfigClient, error) {
	command := exec.CommandContext(ctx, engine, "app-server", "-c", "log_dir="+strconv.Quote(filepath.Join(runtimeDir, "logs")), "-c", "sqlite_home="+strconv.Quote(filepath.Join(runtimeDir, "state")))
	command.Env, command.Dir = desktopEnv(home, profile, ""), workspace
	input, err := command.StdinPipe()
	if err != nil {
		return nil, err
	}
	output, err := command.StdoutPipe()
	if err != nil {
		input.Close()
		return nil, err
	}
	if err := command.Start(); err != nil {
		input.Close()
		return nil, errors.New("could not inspect ordinary engine configuration")
	}
	client := &desktopConfigClient{command: command, input: input, encoder: json.NewEncoder(input), decoder: json.NewDecoder(io.LimitReader(output, 16<<20))}
	if _, err := client.call("initialize", map[string]any{"clientInfo": map[string]string{"name": "tofa", "version": "experimental"}}); err != nil {
		client.close()
		return nil, err
	}
	if err := client.encoder.Encode(map[string]string{"method": "initialized"}); err != nil {
		client.close()
		return nil, err
	}
	return client, nil
}

func (client *desktopConfigClient) close() {
	client.input.Close()
	client.command.Process.Kill()
	client.command.Wait()
}

func (client *desktopConfigClient) call(method string, params any) (map[string]any, error) {
	client.id++
	if err := client.encoder.Encode(map[string]any{"id": client.id, "method": method, "params": params}); err != nil {
		return nil, errors.New("ordinary engine configuration request failed")
	}
	for {
		var response struct {
			ID     int
			Result map[string]any
			Error  json.RawMessage
		}
		if err := client.decoder.Decode(&response); err != nil {
			return nil, errors.New("ordinary engine configuration check failed; inspect the installed client and managed policy")
		}
		if response.ID != client.id {
			continue
		}
		if len(response.Error) > 0 && string(response.Error) != "null" {
			return nil, fmt.Errorf("ordinary engine rejected %s or a competing configuration edit; resolve the conflict and relaunch", method)
		}
		return response.Result, nil
	}
}

func (client *desktopConfigClient) inspect(workspace string) (string, bool, error) {
	result, err := client.call("configRequirements/read", map[string]any{})
	if err != nil {
		return "", false, err
	}
	requirements, _ := result["requirements"].(map[string]any)
	if err := checkDesktopRequirements(requirements); err != nil {
		return "", false, err
	}
	result, err = client.call("config/read", map[string]any{"includeLayers": true, "cwd": workspace})
	if err != nil {
		return "", false, err
	}
	config, _ := result["config"].(map[string]any)
	providers, _ := config["model_providers"].(map[string]any)
	provider, present := providers["nebius-tofa"]
	if present {
		settings, ok := provider.(map[string]any)
		if !ok {
			return "", false, errors.New("conflicting user-owned nebius-tofa provider; resolve it before launching")
		}
		clean := map[string]any{}
		for key, value := range settings {
			if value == nil || (key == "supports_standalone_web_search" && value == false) {
				continue
			}
			clean[key] = value
		}
		// Keep the exact legacy owned entry compatible without changing user settings.
		if clean["env_key_instructions"] == legacyDesktopRecovery || clean["env_key_instructions"] == selectedMainDesktopRecovery {
			clean["env_key_instructions"] = inactiveDesktopProvider["env_key_instructions"]
		}
		if !reflect.DeepEqual(clean, inactiveDesktopProvider) {
			return "", false, errors.New("conflicting user-owned nebius-tofa provider; preserve or rename that integration before launching")
		}
	}
	layers, _ := result["layers"].([]any)
	for _, raw := range layers {
		layer, _ := raw.(map[string]any)
		name, _ := layer["name"].(map[string]any)
		if name["type"] == "user" {
			version, _ := layer["version"].(string)
			if version != "" {
				return version, present, nil
			}
		}
	}
	return "", false, errors.New("ordinary engine did not supply a user configuration version; launch cancelled")
}

func integrateDesktopProvider(ctx context.Context, engine, home, profile, workspace, runtimeDir string, ownerPID int) error {
	ctx, cancel := context.WithTimeout(ctx, 15*time.Second)
	defer cancel()
	client, err := openDesktopConfig(ctx, engine, home, profile, workspace, runtimeDir)
	if err != nil {
		return err
	}
	defer client.close()
	version, present, err := client.inspect(workspace)
	if err != nil || present || ownerPID == 0 {
		return err
	}
	if !desktopOwnsNativeProfile(profile, ownerPID) {
		return errors.New("desktop native profile ownership lost before integration; owned launch cancelled")
	}
	_, err = client.call("config/batchWrite", map[string]any{"filePath": nil, "expectedVersion": version, "reloadUserConfig": true, "edits": []any{map[string]any{"keyPath": "model_providers.nebius-tofa", "value": inactiveDesktopProvider, "mergeStrategy": "replace"}}})
	return err
}

func desktopOwnsNativeProfile(profile string, pid int) bool {
	owner, err := os.Readlink(filepath.Join(profile, "SingletonLock"))
	host, hostErr := os.Hostname()
	return err == nil && hostErr == nil && owner == host+"-"+strconv.Itoa(pid) && syscall.Kill(pid, 0) == nil
}

func desktopHome(ctx context.Context) (string, error) {
	if err := checkDesktopLoginShell(ctx); err != nil {
		return "", err
	}
	ctx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()
	// Ordinary startup uses the account's interactive login shell. Resolve only
	// its history path; never capture or print its hydrated credentials.
	command := exec.CommandContext(ctx, "/bin/zsh", "-ilc", `builtin printf '\0tofa-desktop-home\0%s\0' "${CODEX_HOME:-$HOME/.codex}"`)
	// Match the qualified desktop's shell query, including overrides of caller
	// values, so desktop-specific startup rules select the ordinary history.
	command.Env = append(os.Environ(), "CODEX_SHELL=1", "DISABLE_AUTO_UPDATE=true", "ZSH_TMUX_AUTOSTARTED=true", "ZSH_TMUX_AUTOSTART=false")
	output, err := command.Output()
	parts := strings.Split(string(output), "\x00tofa-desktop-home\x00")
	if err != nil || len(parts) != 2 || !strings.HasSuffix(parts[1], "\x00") {
		return "", errors.New("could not resolve ordinary desktop history through the login shell; check shell startup and relaunch")
	}
	home := strings.TrimSuffix(parts[1], "\x00")
	if !filepath.IsAbs(home) || strings.ContainsRune(home, '\x00') {
		return "", errors.New("ordinary desktop CODEX_HOME must resolve to an absolute path")
	}
	return filepath.Clean(home), nil
}

func refuseDesktopOwner(profile string) error {
	_, err := os.Lstat(filepath.Join(profile, "SingletonLock"))
	if err == nil {
		owner, readErr := os.Readlink(filepath.Join(profile, "SingletonLock"))
		host, hostErr := os.Hostname()
		prefix := host + "-"
		if readErr == nil && hostErr == nil && strings.HasPrefix(owner, prefix) {
			pid, parseErr := strconv.Atoi(strings.TrimPrefix(owner, prefix))
			if parseErr == nil && pid > 0 && errors.Is(syscall.Kill(pid, 0), syscall.ESRCH) {
				return nil // Qualified native startup reclaims a proven-dead owner; never unlink its artifacts here.
			}
		}
		return errors.New("ordinary desktop profile is already owned or has an unresolved native lock. Quit Codex desktop before launching through tofa; resolve unrecognized profile ownership in the ordinary client first. No existing process was changed")
	}
	if !errors.Is(err, os.ErrNotExist) {
		return fmt.Errorf("could not establish ordinary desktop profile ownership: %w", err)
	}
	return nil
}

// Fixed in release builds; offline tests supply a process inventory fixture.
var desktopProcessCommand = "/bin/ps"

// A native launch race can leave a live desktop without SingletonLock. Refuse
// that incumbent as well; a process snapshot is only a refusal check, never
// evidence that this launcher owns the profile.
func refuseDesktopProcesses(ctx context.Context, profile string) error {
	ctx, cancel := context.WithTimeout(ctx, 2*time.Second)
	defer cancel()
	output, err := exec.CommandContext(ctx, desktopProcessCommand, "-axww", "-o", "args=").Output()
	if err != nil {
		return errors.New("could not check for an existing desktop; launch cancelled")
	}
	for _, line := range strings.Split(string(output), "\n") {
		line = strings.TrimSpace(line)
		for _, suffix := range []string{".app/Contents/MacOS/ChatGPT", ".app/Contents/MacOS/Codex"} {
			index := strings.Index(line, suffix)
			if index < 0 {
				continue
			}
			prefix := line[:index]
			// Exclude shell commands that merely mention an app path. Interpreter
			// scripts are included for executable-boundary fixtures and wrappers.
			if !strings.HasPrefix(prefix, "/") || strings.Contains(prefix, " -") {
				continue
			}
			rest := line[index+len(suffix):]
			if rest != "" && !strings.HasPrefix(rest, " ") {
				continue
			}
			if strings.Contains(rest, " --user-data-dir=") && !strings.Contains(rest+" ", " --user-data-dir="+profile+" ") {
				continue
			}
			return errors.New("Codex desktop is already running. Quit it before launching through tofa; no existing process was changed")
		}
	}
	return nil
}

func checkDesktopRequirements(requirements map[string]any) error {
	for _, key := range []string{"modelProvider", "modelProviders", "modelCatalogJson", "models", "sqliteHome", "logDir", "cliAuthCredentialsStore", "allowedLoginMethods", "enforceResidency"} {
		// The engine reports both effective login methods even when only
		// unrelated managed requirements are present. This set is unrestricted.
		if key == "allowedLoginMethods" && (reflect.DeepEqual(requirements[key], []any{"api", "chatgpt"}) || reflect.DeepEqual(requirements[key], []any{"chatgpt", "api"})) {
			continue
		}
		if requirements[key] != nil {
			return fmt.Errorf("managed %s requirement is not qualified for desktop routing; contact your administrator", key)
		}
	}
	return nil
}
