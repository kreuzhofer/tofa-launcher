// PROTOTYPE: transparent process transport, never a production launcher.
package main

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"sync"
	"time"
)

type configuration struct {
	Engine      string `json:"engine"`
	SHA256      string `json:"sha256"`
	EvidenceDir string `json:"evidence_dir"`
}

type evidence struct {
	mu sync.Mutex
	f  *os.File
}

func (e *evidence) write(event string, fields map[string]any) {
	e.mu.Lock()
	defer e.mu.Unlock()
	fields["event"] = event
	fields["utc"] = time.Now().UTC().Format(time.RFC3339Nano)
	// Losing evidence fails the experiment; never leak a protocol payload as a diagnostic.
	if err := json.NewEncoder(e.f).Encode(fields); err != nil {
		fmt.Fprintln(os.Stderr, "prototype evidence write failed")
		os.Exit(125)
	}
}

func main() { os.Exit(run()) }
func run() int {
	data, err := os.ReadFile(os.Getenv("TOFA_PROTOTYPE_CONFIG"))
	if err != nil {
		fmt.Fprintln(os.Stderr, "prototype configuration unavailable")
		return 125
	}
	var cfg configuration
	if json.Unmarshal(data, &cfg) != nil || !filepath.IsAbs(cfg.Engine) || !filepath.IsAbs(cfg.EvidenceDir) || len(cfg.SHA256) != 64 {
		fmt.Fprintln(os.Stderr, "prototype configuration invalid")
		return 125
	}
	engine, err := os.Open(cfg.Engine)
	if err != nil {
		fmt.Fprintln(os.Stderr, "prototype engine unavailable")
		return 125
	}
	hash := sha256.New()
	_, err = io.Copy(hash, engine)
	closeErr := engine.Close()
	if err != nil || closeErr != nil || hex.EncodeToString(hash.Sum(nil)) != cfg.SHA256 {
		fmt.Fprintln(os.Stderr, "prototype engine hash mismatch")
		return 125
	}
	f, err := os.OpenFile(filepath.Join(cfg.EvidenceDir, fmt.Sprintf("bridge-%d.jsonl", os.Getpid())), os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0600)
	if err != nil {
		fmt.Fprintln(os.Stderr, "prototype evidence unavailable")
		return 125
	}
	defer f.Close()
	log := &evidence{f: f}
	mainServer, serviceFlag := false, false
	for _, arg := range os.Args[1:] {
		if arg == "app-server" {
			mainServer = true
		}
		if arg == "features.windows_sandbox_service=true" {
			serviceFlag = true
		}
	}
	log.write("start", map[string]any{"pid": os.Getpid(), "parent_pid": os.Getppid(), "engine_sha256": cfg.SHA256, "argc": len(os.Args) - 1, "app_server_argument": mainServer, "registered_core_present": os.Getenv("CODEX_WINDOWS_REGISTERED_CORE") != "", "sandbox_family_present": os.Getenv("CODEX_WINDOWS_SANDBOX_PACKAGE_FAMILY") != "", "sandbox_service_argument": serviceFlag})
	child := exec.Command(cfg.Engine, os.Args[1:]...)
	transport := &protocol{pending: make(map[string]string), log: log}
	input, err := child.StdinPipe()
	if err != nil {
		log.write("stdin_failed", map[string]any{})
		return 125
	}
	child.Stdout = io.MultiWriter(os.Stdout, &observer{protocol: transport})
	child.Stderr = os.Stderr
	if err := child.Start(); err != nil {
		log.write("start_failed", map[string]any{})
		return 125
	}
	log.write("child", map[string]any{"pid": child.Process.Pid})
	go func() {
		_, _ = io.Copy(input, io.TeeReader(os.Stdin, &observer{protocol: transport, request: true}))
		_ = input.Close()
	}()
	code := 0
	if err := child.Wait(); err != nil {
		if exit, ok := err.(*exec.ExitError); ok {
			code = exit.ExitCode()
		} else {
			code = 125
		}
	}
	log.write("exit", map[string]any{"exit_code": code})
	return code
}
