package tofa

import (
	"bufio"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"slices"
	"strconv"
	"strings"
	"sync"
	"syscall"
	"time"
)

// The desktop's default picker writes model/effort into the ordinary user
// config before handling the engine's okOverridden result. Those writes leak
// into concurrent CLI clients even though launch flags override the desktop.
// Keep this exact write contract session-scoped: ask the engine for the current
// config version without writing, then return an explicit override result. The
// pinned renderer retains its requested selection locally on okOverridden and
// supplies it when starting a thread. All other protocol traffic stays native.
func runDesktopSettingsBridge(engine string, args, env []string, home, inferenceCapability string) error {
	configFile, err := filepath.EvalSymlinks(filepath.Join(home, "config.toml"))
	if err != nil {
		return errors.New("desktop model isolation could not resolve the ordinary configuration file")
	}
	// Keep the signed engine in Desktop's original child PID. Native app tools
	// authenticate Node -> engine -> Desktop; a supervising bridge breaks that
	// ancestry. A separate child relays the same protocol over inherited pipes.
	executable, err := os.Executable()
	if err != nil {
		return err
	}
	engineInput, relayInput, err := os.Pipe()
	if err != nil {
		return err
	}
	defer engineInput.Close()
	defer relayInput.Close()
	relayOutput, engineOutput, err := os.Pipe()
	if err != nil {
		return err
	}
	defer relayOutput.Close()
	defer engineOutput.Close()
	ready, readyWriter, err := os.Pipe()
	if err != nil {
		return err
	}
	defer ready.Close()
	defer readyWriter.Close()
	relayArgs := []string{"--tofa-desktop-settings-relay", configFile, strconv.Itoa(os.Getpid()), strconv.Itoa(os.Getppid())}
	if inferenceCapability != "" {
		relayArgs = append(relayArgs, "native-review-cancellation")
	}
	command := exec.Command(executable, relayArgs...)
	command.Env, command.Stdin, command.Stdout, command.Stderr = env, os.Stdin, os.Stdout, os.Stderr
	command.ExtraFiles = []*os.File{relayInput, relayOutput, readyWriter}
	if err := command.Start(); err != nil {
		return err
	}
	defer func() { command.Process.Kill(); command.Wait() }()
	relayInput.Close()
	relayOutput.Close()
	readyWriter.Close()
	if err := ready.SetReadDeadline(time.Now().Add(10 * time.Second)); err != nil {
		return err
	}
	var handshake [1]byte
	if _, err := io.ReadFull(ready, handshake[:]); err != nil || handshake[0] != 'R' {
		return errors.New("desktop settings relay failed to initialize")
	}
	if err := syscall.Dup2(int(engineInput.Fd()), int(os.Stdin.Fd())); err != nil {
		return err
	}
	if err := syscall.Dup2(int(engineOutput.Fd()), int(os.Stdout.Fd())); err != nil {
		return err
	}
	engineInput.Close()
	engineOutput.Close()
	if inferenceCapability != "" {
		env = slices.DeleteFunc(env, func(entry string) bool { return strings.HasPrefix(entry, "TOFA_") })
		env = append(env, nativeDesktopInferenceEnv+"="+inferenceCapability)
	}
	return syscall.Exec(engine, append([]string{engine}, args...), env)
}

func runDesktopSettingsRelay(args []string) (result error) {
	nativeReviewCancellation := len(args) == 4 && args[3] == "native-review-cancellation"
	if len(args) != 3 && !nativeReviewCancellation {
		return errors.New("invalid desktop settings relay arguments")
	}
	configFile := args[0]
	enginePID, err := strconv.Atoi(args[1])
	if err != nil || enginePID <= 1 || enginePID != os.Getppid() {
		return errors.New("desktop settings relay parent changed")
	}
	desktopPID, err := strconv.Atoi(args[2])
	if err != nil || desktopPID <= 1 || !filepath.IsAbs(configFile) {
		return errors.New("invalid desktop settings relay ownership")
	}
	input := os.NewFile(3, "engine-input")
	output := os.NewFile(4, "engine-output")
	ready := os.NewFile(5, "relay-ready")
	for _, file := range []*os.File{input, output, ready} {
		info, err := file.Stat()
		if err != nil || info.Mode()&os.ModeNamedPipe == 0 {
			return errors.New("desktop settings relay requires inherited pipes")
		}
		defer file.Close()
	}
	killEngine := func() {
		// A relay must never signal a recycled PID after its engine parent exits.
		if os.Getppid() == enginePID {
			syscall.Kill(enginePID, syscall.SIGKILL)
		}
	}
	defer func() {
		if result != nil {
			killEngine()
		}
	}()
	if _, err := ready.Write([]byte{'R'}); err != nil {
		return err
	}
	ready.Close()
	var writesMu, pendingMu sync.Mutex
	pending := map[string]json.RawMessage{}
	mainInitialize := false
	write := func(value any) error {
		writesMu.Lock()
		defer writesMu.Unlock()
		return json.NewEncoder(os.Stdout).Encode(value)
	}
	failure := func(id json.RawMessage, message string) error {
		return write(map[string]any{"id": id, "error": map[string]any{"code": -32600, "message": message}})
	}
	inputDone := make(chan error, 1)
	go func() {
		scanner := bufio.NewScanner(os.Stdin)
		scanner.Buffer(make([]byte, 64<<10), 64<<20)
		for scanner.Scan() {
			line := append([]byte(nil), scanner.Bytes()...)
			var request struct {
				ID     json.RawMessage
				Method string
				Params json.RawMessage
			}
			if json.Unmarshal(line, &request) != nil {
				inputDone <- errors.New("invalid desktop protocol request")
				killEngine()
				return
			}
			// This named initialization identifies the conversation connection on
			// both qualified clients. The short-lived network-initialize helper
			// must not become the engine whose exit ends the desktop session.
			if request.Method == "initialize" && string(request.ID) == `"__codex_initialize__"` {
				pendingMu.Lock()
				mainInitialize = true
				pendingMu.Unlock()
			}
			if nativeReviewCancellation && request.Method == "turn/interrupt" {
				if err := cancelDesktopReview(os.Getenv("TOFA_DESKTOP_CONTEXT"), os.Getenv("TOFA_API_KEY"), request.Params); err != nil {
					failure(request.ID, "tofa: review cancellation could not be authenticated; the engine is stopping without releasing pending approvals")
					inputDone <- err
					killEngine()
					return
				}
			}
			intercept, valid := desktopModelWrite(request.Method, request.Params)
			if intercept {
				if !valid || len(request.ID) == 0 || string(request.ID) == "null" {
					if err := failure(request.ID, "tofa: unsupported desktop model-default write; use the model picker for this session; unrelated settings were not changed"); err != nil {
						inputDone <- err
						killEngine()
						return
					}
					continue
				}
				pendingMu.Lock()
				pending[string(request.ID)] = request.Params
				pendingMu.Unlock()
				line, _ = json.Marshal(map[string]any{"id": request.ID, "method": "config/read", "params": map[string]any{"includeLayers": true}})
			}
			if _, err := input.Write(append(line, '\n')); err != nil {
				inputDone <- err
				return
			}
		}
		input.Close()
		inputDone <- scanner.Err()
		if scanner.Err() != nil {
			killEngine()
		}
	}()
	scanner := bufio.NewScanner(output)
	scanner.Buffer(make([]byte, 64<<10), 64<<20)
	for scanner.Scan() {
		line := append(json.RawMessage(nil), scanner.Bytes()...)
		var response struct {
			ID     json.RawMessage
			Method string
			Result json.RawMessage
			Error  json.RawMessage
		}
		if json.Unmarshal(line, &response) != nil {
			return errors.New("invalid bundled engine protocol response")
		}
		var params json.RawMessage
		intercepted := false
		mainReady := false
		// Server requests (including approvals) have their own ID namespace.
		// They must never consume a pending client configuration response.
		if response.Method == "" {
			pendingMu.Lock()
			if mainInitialize && string(response.ID) == `"__codex_initialize__"` {
				mainReady = true
				mainInitialize = false
			}
			params, intercepted = pending[string(response.ID)]
			delete(pending, string(response.ID))
			pendingMu.Unlock()
		}
		if mainReady && len(response.Result) != 0 && (len(response.Error) == 0 || string(response.Error) == "null") {
			if _, err := fetchDesktopRouteForParent(os.Getenv("TOFA_DESKTOP_CONTEXT"), os.Getenv("TOFA_API_KEY"), enginePID, desktopPID); err != nil {
				return fmt.Errorf("desktop main engine acknowledgement failed: %w", err)
			}
		}
		if intercepted && (len(response.Error) == 0 || string(response.Error) == "null") {
			var result struct {
				Config map[string]any
				Layers []struct {
					Name    map[string]any
					Version string
				}
			}
			var request struct{ ExpectedVersion *string }
			json.Unmarshal(params, &request)
			if json.Unmarshal(response.Result, &result) != nil {
				return errors.New("invalid engine configuration response")
			}
			version := ""
			for _, layer := range result.Layers {
				if layer.Name["type"] == "user" && layer.Name["file"] == configFile {
					version = layer.Version
				}
			}
			if version == "" || (request.ExpectedVersion != nil && *request.ExpectedVersion != version) {
				if err := failure(response.ID, "tofa: desktop model selection could not verify the current settings version; refresh and retry; CLI defaults were not changed"); err != nil {
					return err
				}
				continue
			}
			if err := write(map[string]any{"id": response.ID, "result": map[string]any{
				"status": "okOverridden", "version": version, "filePath": configFile,
				"overriddenMetadata": map[string]any{"message": "tofa: model selection applies only to this desktop session; CLI defaults were not written.", "effectiveValue": result.Config["model"], "overridingLayer": map[string]any{"name": map[string]any{"type": "sessionFlags"}, "version": version}},
			}}); err != nil {
				return err
			}
			continue
		}
		if err := write(line); err != nil {
			return err
		}
	}
	if err := scanner.Err(); err != nil {
		return fmt.Errorf("desktop engine protocol: %w", err)
	}
	select {
	case err := <-inputDone:
		return err
	default:
		return nil
	}
}

// Accept only the pinned model picker writes. Never partially apply a mixed
// model/settings batch, and never intercept unrelated engine settings.
func desktopModelWrite(method string, params json.RawMessage) (intercept, valid bool) {
	if method != "config/batchWrite" && method != "config/value/write" {
		return false, false
	}
	type edit struct {
		KeyPath       string
		Value         json.RawMessage
		MergeStrategy string
	}
	var request struct {
		Edits         []edit
		KeyPath       string
		Value         json.RawMessage
		MergeStrategy string
		FilePath      *string
	}
	if json.Unmarshal(params, &request) != nil {
		return true, false
	}
	edits := request.Edits
	if method == "config/value/write" {
		edits = []edit{{request.KeyPath, request.Value, request.MergeStrategy}}
	}
	valid = request.FilePath == nil && len(edits) > 0
	for _, change := range edits {
		key := change.KeyPath
		modelKey := key == "model" || key == "model_reasoning_effort" || key == "service_tier" || key == "plan_mode_reasoning_effort"
		if modelKey || key == "" || strings.HasPrefix(key, "model.") || strings.HasPrefix(key, "profiles") {
			intercept = true
		}
		if !modelKey || (change.MergeStrategy != "replace" && change.MergeStrategy != "upsert") {
			valid = false
		}
		var value *string
		if len(change.Value) == 0 || json.Unmarshal(change.Value, &value) != nil {
			valid = false
		}
	}
	return intercept, valid
}
