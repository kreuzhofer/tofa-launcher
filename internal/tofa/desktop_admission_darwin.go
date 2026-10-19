package tofa

// Admission validates local qualification intent/evidence, not a new credential.
// Owner-only evidence prevents accidental reuse; it cannot prove a same-user
// author's statements true. Native UI observations are explicitly attributed.
import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"io/fs"
	"os"
	"os/exec"
	"path/filepath"
	"reflect"
	"sort"
	"strconv"
	"strings"
	"syscall"
	"time"

	"github.com/pelletier/go-toml/v2"
)

const desktopQualificationRoot = "/tmp/tofa-presentation-validation"
const desktopDeclarationSchema = "tofa-native-account-declaration-v1"
const desktopProofSchema = "tofa-native-account-proof-v1"
const desktopCaseSchema = "tofa-native-account-case-v1"

var desktopQualificationCases = map[string][]string{
	"clean-exit":          {"account-visible", "code-review-eligible", "plugins-visible"},
	"repeat-launch":       {"account-visible", "code-review-eligible", "history-readable"},
	"launcher-crash":      {"account-visible", "code-review-eligible", "ordinary-recovery"},
	"native-crash":        {"account-visible", "code-review-eligible", "ordinary-recovery"},
	"ordinary-launch":     {"account-visible", "code-review-eligible", "history-readable", "actionable-relaunch-guidance"},
	"bridge-update":       {"account-visible", "code-review-eligible", "ordinary-recovery"},
	"uninstall-reinstall": {"account-visible", "code-review-eligible", "ordinary-recovery"},
	"service-switching":   {"service-labels", "retained-context"},
	"history-resume":      {"history-readable", "retained-context", "actionable-relaunch-guidance"},
	"review-routing":      {"native-approval-enforced"},
	"launch-naming":       {"title-visible-native", "title-visible-token-factory", "title-visible-existing-native", "title-policy-disclosed"},
	"runtime-preview":     {"native-pptx-preview", "native-pdf-preview"},
}

// Source is build provenance, not the commit containing subsequently published
// evidence. Hashes bind the actual bytes and all relevant installed resources.
type desktopAdmissionIdentity struct {
	Source  string            `json:"source_revision"`
	Home    string            `json:"home"`
	Profile string            `json:"profile"`
	Runtime string            `json:"runtime_root"`
	Harness string            `json:"harness_root"`
	Hashes  map[string]string `json:"hashes"`
}
type desktopCandidateDeclaration struct {
	Schema      string                   `json:"schema"`
	Attempt     string                   `json:"attempt"`
	Case        string                   `json:"case"`
	Root        string                   `json:"root"`
	Identity    desktopAdmissionIdentity `json:"identity"`
	Issued      time.Time                `json:"issued_utc"`
	Expires     time.Time                `json:"expires_utc"`
	Seconds     int                      `json:"seconds"`
	Requests    int                      `json:"requests"`
	ScopeSHA256 string                   `json:"scope_sha256,omitempty"`
}
type desktopEvidenceRef struct {
	Path   string `json:"path"`
	SHA256 string `json:"sha256"`
}
type desktopAdmission struct {
	mode         string
	path, digest string
	identity     desktopAdmissionIdentity
	declaration  desktopCandidateDeclaration
	consumed     bool
	protected    map[string]string
}

func admissionError(reason string) error {
	return fmt.Errorf("native-account qualification %s; retain this attempt and qualify the matching installation before relaunching", reason)
}
func validDigest(s string) bool {
	raw, e := hex.DecodeString(s)
	return e == nil && len(raw) == 32 && s == strings.ToLower(s)
}
func digestBytes(raw []byte) string { h := sha256.Sum256(raw); return hex.EncodeToString(h[:]) }
func canonicalPath(path string) (string, error) {
	if !filepath.IsAbs(path) {
		return "", admissionError("requires absolute paths")
	}
	return filepath.EvalSymlinks(path)
}
func withinPath(root, path string) bool {
	rel, e := filepath.Rel(root, path)
	return e == nil && rel != ".." && !strings.HasPrefix(rel, ".."+string(os.PathSeparator))
}

// Resolve /tmp's OS alias once. Below the fixed root every component must be an
// owned, private directory and the leaf a non-symlink, private regular file.
func privateEvidencePath(path string, directory bool) (string, error) {
	root, e := filepath.EvalSymlinks(desktopQualificationRoot)
	if e != nil {
		return "", admissionError("root unavailable")
	}
	if strings.HasPrefix(path, desktopQualificationRoot+"/") {
		path = filepath.Join(root, strings.TrimPrefix(path, desktopQualificationRoot+"/"))
	}
	if !filepath.IsAbs(path) || filepath.Clean(path) != path || !withinPath(root, path) || path == root {
		return "", admissionError("evidence outside fixed root")
	}
	current := path
	for {
		info, e := os.Lstat(current)
		if e != nil {
			return "", admissionError("evidence unavailable")
		}
		stat, ok := info.Sys().(*syscall.Stat_t)
		if !ok || stat.Uid != uint32(os.Getuid()) || info.Mode()&os.ModeSymlink != 0 || info.Mode().Perm()&0077 != 0 {
			return "", admissionError("requires private owned evidence")
		}
		if current == path && !directory {
			if !info.Mode().IsRegular() {
				return "", admissionError("requires regular evidence")
			}
		} else if !info.IsDir() {
			return "", admissionError("requires owned evidence directories")
		}
		if filepath.Dir(current) == root {
			break
		}
		current = filepath.Dir(current)
	}
	return path, nil
}
func strictAdmissionJSON(raw []byte, target any) error {
	if uniqueReviewJSON(raw, 0) != nil {
		return admissionError("contains ambiguous JSON")
	}
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.DisallowUnknownFields()
	if decoder.Decode(target) != nil || decoder.Decode(new(any)) != io.EOF {
		return admissionError("has an unsupported record")
	}
	return nil
}
func readDesktopEvidence(path string, target any) (string, error) {
	path, e := privateEvidencePath(path, false)
	if e != nil {
		return "", e
	}
	fd, e := syscall.Open(path, syscall.O_RDONLY|syscall.O_NOFOLLOW, 0)
	if e != nil {
		return "", admissionError("evidence unavailable")
	}
	f := os.NewFile(uintptr(fd), path)
	defer f.Close()
	info, e := f.Stat()
	if e != nil || !info.Mode().IsRegular() || info.Mode().Perm()&0077 != 0 || info.Sys().(*syscall.Stat_t).Uid != uint32(os.Getuid()) || info.Size() > 4<<20 {
		return "", admissionError("evidence size invalid")
	}
	raw, e := io.ReadAll(io.LimitReader(f, (4<<20)+1))
	if e != nil || len(raw) > 4<<20 {
		return "", admissionError("evidence size invalid")
	}
	if e := strictAdmissionJSON(raw, target); e != nil {
		return "", e
	}
	return digestBytes(raw), nil
}
func readDesktopDeclaration(path string, id desktopAdmissionIdentity, seconds int, now time.Time) (*desktopAdmission, error) {
	var d desktopCandidateDeclaration
	digest, e := readDesktopEvidence(path, &d)
	if e != nil {
		return nil, e
	}
	canonical, e := privateEvidencePath(path, false)
	if e != nil {
		return nil, e
	}
	root, e := privateEvidencePath(d.Root, true)
	if e != nil {
		return nil, e
	}
	_, known := desktopQualificationCases[d.Case]
	if d.Schema != desktopDeclarationSchema || !known || !validText(d.Attempt, 128) || strings.ContainsAny(d.Attempt, "/\\ ") || root != filepath.Dir(canonical) || !reflect.DeepEqual(d.Identity, id) ||
		(seconds != 600 && seconds != 900) || d.Seconds != seconds || d.Requests < 1 || d.Requests > 80 || d.Issued.After(now) || now.Sub(d.Issued) > 30*time.Minute || !d.Expires.After(now) || d.Expires.Sub(d.Issued) != time.Duration(seconds)*time.Second {
		return nil, admissionError("declaration is stale or mismatched")
	}
	if e := validateAdmissionScope(root, d); e != nil {
		return nil, e
	}
	if _, e := os.Lstat(filepath.Join(root, "start.json")); !errors.Is(e, os.ErrNotExist) {
		return nil, admissionError("attempt already consumed")
	}
	return &desktopAdmission{mode: "candidate", path: canonical, digest: digest, identity: id, declaration: d}, nil
}
func (a *desktopAdmission) consume(now time.Time) error {
	if a == nil || a.mode != "candidate" {
		return nil
	}
	if !a.declaration.Expires.After(now) {
		return admissionError("attempt expired")
	}
	raw, _ := json.Marshal(map[string]any{"schema": "tofa-native-account-start-v1", "attempt": a.declaration.Attempt, "declaration_sha256": a.digest, "started_utc": now})
	f, e := os.OpenFile(filepath.Join(filepath.Dir(a.path), "start.json"), os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0600)
	if e != nil {
		return admissionError("attempt already consumed")
	}
	_, writeErr := f.Write(raw)
	syncErr := f.Sync()
	closeErr := f.Close()
	if e := errors.Join(writeErr, syncErr, closeErr); e != nil {
		return e
	}
	a.consumed = true
	return nil
}
func (a *desktopAdmission) permitsPlugins() bool {
	return a != nil && (a.mode == "candidate" && a.consumed || a.mode == "qualified")
}
func (a *desktopAdmission) checkFile() error {
	if a == nil {
		return nil
	}
	var raw json.RawMessage
	digest, e := readDesktopEvidence(a.path, &raw)
	if e != nil {
		return e
	}
	if digest != a.digest {
		return admissionError("record changed during launch")
	}
	if a.mode == "candidate" {
		if !a.declaration.Expires.After(time.Now()) {
			return admissionError("attempt expired")
		}
		if e := validateAdmissionScope(filepath.Dir(a.path), a.declaration); e != nil {
			return e
		}
	}
	return nil
}

// Exact semantic exception. Unknown keys, unused profiles, disabled plugins and
// TOML primitive types stay in the full decoded document. No snapshot restore.
func normalizeDesktopConfig(raw []byte, engine, bridge string) ([]byte, error) {
	if len(raw) > 4<<20 {
		return nil, admissionError("settings too large")
	}
	var value map[string]any
	if toml.Unmarshal(raw, &value) != nil {
		return nil, admissionError("settings cannot be parsed")
	}
	if !admissionValueBounded(value, 0) {
		return nil, admissionError("settings nesting too deep")
	}
	if providers, ok := value["model_providers"].(map[string]any); ok {
		for id, expected := range map[string]map[string]any{"nebius-tofa": inactiveDesktopProvider, nativeDesktopProvider: inactiveNativeDesktopProvider} {
			if provider, exists := providers[id]; exists {
				if !exactInactiveTOMLProvider(provider, expected) {
					return nil, admissionError("provider ownership conflict")
				}
				delete(providers, id)
			}
		}
		if len(providers) == 0 {
			delete(value, "model_providers")
		}
	}
	if e := normalizeDesktopReference(value, []string{"mcp_servers", "node_repl", "env", "CODEX_CLI_PATH"}, engine, bridge); e != nil {
		return nil, e
	}
	return json.Marshal(admissionTypedValue(value))
}
func exactInactiveTOMLProvider(raw any, expected map[string]any) bool {
	actual, ok := raw.(map[string]any)
	if !ok {
		return false
	}
	wanted := map[string]any{}
	for key, value := range expected {
		if number, ok := value.(float64); ok {
			wanted[key] = int64(number)
		} else {
			wanted[key] = value
		}
	}
	if expected["env_key"] == "TOFA_DESKTOP_INACTIVE" && (actual["env_key_instructions"] == legacyDesktopRecovery || actual["env_key_instructions"] == selectedMainDesktopRecovery) {
		wanted["env_key_instructions"] = actual["env_key_instructions"]
	}
	return reflect.DeepEqual(actual, wanted)
}

// Preserve TOML types as well as values (1 differs from 1.0, dates from strings).
func admissionTypedValue(v any) any {
	switch value := v.(type) {
	case float64:
		return []any{"float64", strconv.FormatFloat(value, 'g', -1, 64)}
	case map[string]any:
		result := map[string]any{}
		for k, x := range value {
			result[k] = admissionTypedValue(x)
		}
		return []any{"table", result}
	case []any:
		result := make([]any, len(value))
		for i, x := range value {
			result[i] = admissionTypedValue(x)
		}
		return []any{"array", result}
	default:
		return []any{fmt.Sprintf("%T", v), v}
	}
}
func admissionValueBounded(v any, depth int) bool {
	if depth > 64 {
		return false
	}
	switch value := v.(type) {
	case map[string]any:
		for _, item := range value {
			if !admissionValueBounded(item, depth+1) {
				return false
			}
		}
	case []any:
		for _, item := range value {
			if !admissionValueBounded(item, depth+1) {
				return false
			}
		}
	}
	return true
}
func readAdmissionBounded(path string, limit int64) ([]byte, error) {
	file, e := os.Open(path)
	if e != nil {
		return nil, e
	}
	defer file.Close()
	info, e := file.Stat()
	if e != nil || !info.Mode().IsRegular() || info.Size() > limit {
		return nil, admissionError("record unavailable or too large")
	}
	raw, e := io.ReadAll(io.LimitReader(file, limit+1))
	if e != nil || int64(len(raw)) > limit {
		return nil, admissionError("record unavailable or too large")
	}
	return raw, nil
}

func normalizeDesktopReference(value map[string]any, route []string, engine, bridge string) error {
	current := value
	for index, key := range route[:len(route)-1] {
		raw, exists := current[key]
		if !exists {
			if route[0] == "mcpServers" || index > 1 {
				return admissionError("MCP executable reference missing")
			}
			return nil
		}
		next, ok := raw.(map[string]any)
		if !ok {
			return admissionError("MCP reference structure changed")
		}
		current = next
	}
	leaf := route[len(route)-1]
	raw, exists := current[leaf]
	if !exists {
		return admissionError("MCP executable reference missing")
	}
	if raw != engine && (bridge == "" || raw != bridge) {
		return admissionError("MCP executable reference changed")
	}
	current[leaf] = "<owned-native-engine-reference>"
	return nil
}
func hashAdmissionFile(path string) (string, error) {
	f, e := os.Open(path)
	if e != nil {
		return "", e
	}
	defer f.Close()
	h := sha256.New()
	if _, e = io.Copy(h, f); e != nil {
		return "", e
	}
	return hex.EncodeToString(h.Sum(nil)), nil
}
func admissionTree(root, engine, bridge, pluginFile string) (string, error) {
	entries := map[string]string{}
	e := filepath.WalkDir(root, func(path string, d fs.DirEntry, e error) error {
		if errors.Is(e, os.ErrNotExist) && path == root {
			entries["."] = "absent"
			return nil
		}
		if e != nil {
			return e
		}
		if d.Name() == "__pycache__" && d.IsDir() {
			return filepath.SkipDir
		}
		if strings.HasSuffix(d.Name(), ".pyc") {
			return nil
		}
		rel, e := filepath.Rel(root, path)
		if e != nil {
			return e
		}
		if d.Type()&os.ModeSymlink != 0 {
			target, e := os.Readlink(path)
			if e != nil {
				return e
			}
			resolved, e := filepath.EvalSymlinks(path)
			if errors.Is(e, os.ErrNotExist) {
				entries[rel] = "dangling-link:" + target
				return nil
			}
			if e != nil || !withinPath(root, resolved) {
				return admissionError("resource symlink leaves its root")
			}
			entries[rel] = "link:" + target
			return nil
		}
		if d.IsDir() {
			return nil
		}
		info, e := d.Info()
		if e != nil || !info.Mode().IsRegular() {
			return admissionError("unsupported resource file")
		}
		if path == pluginFile {
			raw, e := readAdmissionBounded(path, 4<<20)
			if e != nil {
				return e
			}
			var value map[string]any
			if uniqueReviewJSON(raw, 0) != nil || json.Unmarshal(raw, &value) != nil {
				return admissionError("MCP configuration invalid")
			}
			if e = normalizeDesktopReference(value, []string{"mcpServers", "cua_repl", "env", "CODEX_CLI_PATH"}, engine, bridge); e != nil {
				return e
			}
			raw, e = json.Marshal(value)
			if e != nil {
				return e
			}
			entries[rel] = digestBytes(raw)
			return nil
		}
		hash, e := hashAdmissionFile(path)
		if e != nil {
			return e
		}
		entries[rel] = hash
		return nil
	})
	if e != nil {
		return "", e
	}
	raw, _ := json.Marshal(entries)
	return digestBytes(raw), nil
}

var qualificationHarnessFiles = []string{"desktop_qualification.py", "capability_observer.py", "capability_evaluation.py", "capability_actions.py", "presentation_calibration.py", "presentation_runtime.py", "presentation_smoke.py", "presentation_synthetic.py", "presentation_preview.py", "capability_runtime.py", "retained_mcp.py", "evaluation_proxy.py", "fixtures/presentation-smoke.mjs"}

func desktopCompatibilityIdentity(bundle desktopBundle, home, profile, bridge, runtimeRoot, harness, source string, models []Model) (desktopAdmissionIdentity, error) {
	result := desktopAdmissionIdentity{Source: source, Home: home, Profile: profile, Runtime: runtimeRoot, Harness: harness, Hashes: map[string]string{}}
	if len(source) != 40 {
		return result, admissionError("requires frozen source revision")
	}
	if _, e := hex.DecodeString(source); e != nil {
		return result, admissionError("invalid source revision")
	}
	for _, p := range []string{home, profile, runtimeRoot, harness} {
		if !filepath.IsAbs(p) {
			return result, admissionError("identity path invalid")
		}
	}
	var resolveError error
	runtimeRoot, resolveError = canonicalPath(runtimeRoot)
	if resolveError != nil {
		return result, admissionError("runtime root unavailable")
	}
	harness, resolveError = canonicalPath(harness)
	if resolveError != nil {
		return result, admissionError("harness root unavailable")
	}
	result.Runtime = runtimeRoot
	result.Harness = harness
	if e := validateAdmissionRuntime(runtimeRoot); e != nil {
		return result, e
	}
	executable, e := os.Executable()
	if e != nil {
		return result, e
	}
	app, e := desktopBundlePath(bundle.engine)
	if e != nil {
		return result, e
	}
	files := map[string]string{"launcher": executable, "engine": bundle.engine, "application": bundle.executable, "application_info": filepath.Join(app, "Contents/Info.plist"), "application_archive": filepath.Join(app, "Contents/Resources/app.asar"), "native_transport": filepath.Join(app, "Contents/Resources/plugins/openai-bundled/plugins/codex-app-tools/server.mjs")}
	for name, path := range files {
		hash, e := hashAdmissionFile(path)
		if e != nil {
			return result, admissionError(name + " identity unavailable")
		}
		result.Hashes[name] = hash
	}
	versionBytes, e := exec.Command("/usr/libexec/PlistBuddy", "-c", "Print :CFBundleShortVersionString", filepath.Join(app, "Contents/Info.plist")).Output()
	if e != nil {
		return result, admissionError("native plugin version unavailable")
	}
	version := strings.TrimSpace(string(versionBytes))
	if !validText(version, 80) || strings.ContainsAny(version, "/\\") {
		return result, admissionError("native plugin version invalid")
	}
	pluginRoot := filepath.Join(home, "plugins/cache/openai-bundled/unified-computer-use")
	pluginFile := filepath.Join(pluginRoot, version, ".mcp.json")
	if _, e := os.Lstat(pluginRoot); e == nil {
		if _, e := os.Lstat(pluginFile); e != nil {
			return result, admissionError("current native MCP plugin path unqualified")
		}
	}

	if _, e := os.Lstat(bridge); e == nil {
		owner, e := readDesktopBridge(bridge)
		if e != nil || owner.Engine != bundle.engine {
			return result, admissionError("saved bridge ownership invalid")
		}
	} else if errors.Is(e, os.ErrNotExist) {
		bridge = ""
	} else {
		return result, admissionError("saved bridge unavailable")
	}
	for name, path := range map[string]string{"plugins": filepath.Join(home, "plugins/cache"), "skills": filepath.Join(home, "skills"), "agent_skills": filepath.Join(filepath.Dir(home), ".agents/skills"), "runtime": runtimeRoot} {
		hash, e := admissionTree(path, bundle.engine, bridge, pluginFile)
		if e != nil {
			return result, e
		}
		result.Hashes[name] = hash
	}
	for _, name := range qualificationHarnessFiles {
		hash, e := hashAdmissionFile(filepath.Join(harness, name))
		if e != nil {
			return result, admissionError("harness unavailable")
		}
		result.Hashes["harness/"+name] = hash
	}
	cacheBytes, e := readAdmissionBounded(filepath.Join(home, "models_cache.json"), 16<<20)
	if e != nil || len(cacheBytes) > 16<<20 || uniqueReviewJSON(cacheBytes, 0) != nil {
		return result, admissionError("native catalog identity unavailable")
	}
	var cache struct {
		Models []map[string]any `json:"models"`
	}
	if json.Unmarshal(cacheBytes, &cache) != nil || len(cache.Models) == 0 {
		return result, admissionError("native catalog identity invalid")
	}
	seen := map[string]bool{}
	for _, descriptor := range cache.Models {
		slug, ok := descriptor["slug"].(string)
		if !ok || slug == "" || seen[slug] {
			return result, admissionError("native catalog model identity invalid")
		}
		seen[slug] = true
	}
	sort.Slice(cache.Models, func(i, j int) bool { return cache.Models[i]["slug"].(string) < cache.Models[j]["slug"].(string) })
	nativeRaw, _ := json.Marshal(cache.Models)
	result.Hashes["native_catalog"] = digestBytes(nativeRaw)
	ids := make([]string, 0, len(models))
	for _, m := range models {
		ids = append(ids, m.ID)
	}
	sort.Strings(ids)
	raw, _ := json.Marshal(ids)
	result.Hashes["catalog"] = digestBytes(raw)
	return result, nil
}
func desktopProtectedSnapshot(home, engine, bridge string) (map[string]string, error) {
	normalizationBridge := bridge
	if _, e := os.Lstat(bridge); errors.Is(e, os.ErrNotExist) {
		normalizationBridge = ""
	} else {
		owner, e := readDesktopBridge(bridge)
		if e != nil || owner.Engine != engine {
			return nil, admissionError("saved bridge ownership invalid")
		}
	}
	result := map[string]string{}
	for _, name := range []string{"config.toml", "auth.json", "managed_config.toml", "AGENTS.md", "AGENTS.override.md"} {
		path := filepath.Join(home, name)
		raw, e := readAdmissionBounded(path, 4<<20)
		if len(raw) > 4<<20 {
			return nil, admissionError("protected settings too large")
		}
		if errors.Is(e, os.ErrNotExist) {
			if name == "config.toml" {
				empty, _ := normalizeDesktopConfig(nil, engine, normalizationBridge)
				result[name] = digestBytes(empty)
			} else {
				result[name] = "absent"
			}
			continue
		}
		if e != nil {
			return nil, e
		}
		if name == "config.toml" {
			raw, e = normalizeDesktopConfig(raw, engine, normalizationBridge)
			if e != nil {
				return nil, e
			}
		}
		result[name] = digestBytes(raw)
	}
	launcherRoot := filepath.Dir(filepath.Dir(filepath.Dir(bridge)))
	for _, name := range []string{"config.json", "credentials.json"} {
		path := filepath.Join(launcherRoot, name)
		raw, e := readAdmissionBounded(path, 4<<20)
		if errors.Is(e, os.ErrNotExist) {
			result["launcher/"+name] = "absent"
			continue
		}
		if e != nil {
			return nil, e
		}
		result["launcher/"+name] = digestBytes(raw)
	}
	return result, nil
}
func (a *desktopAdmission) recheck(bundle desktopBundle, home, profile, bridge string, models []Model) error {
	if a == nil {
		return nil
	}
	if e := a.checkFile(); e != nil {
		return e
	}
	owner, e := readDesktopBridge(bridge)
	if e != nil || owner.Engine != bundle.engine || owner.SHA256 != a.identity.Hashes["launcher"] {
		return admissionError("owned bridge drifted")
	}
	current, e := desktopCompatibilityIdentity(bundle, home, profile, bridge, a.identity.Runtime, a.identity.Harness, a.identity.Source, models)
	if e != nil {
		return e
	}
	if !reflect.DeepEqual(current, a.identity) {
		return admissionError("installation drifted")
	}
	if a.mode == "qualified" {
		if _, e := readDesktopProof(a.path, current); e != nil {
			return e
		}
	}
	state, e := desktopProtectedSnapshot(home, bundle.engine, bridge)
	if e != nil {
		return e
	}
	if !reflect.DeepEqual(a.protected, state) {
		return admissionError("protected state drifted")
	}
	return nil
}

// Construct only after native sign-in, policy and ordinary profile ownership
// checks. A zero value never relaxes the legacy plugin guard.
func resolveDesktopAdmission(ctx context.Context, options launchOptions, observer *evaluationObserver, bundle desktopBundle, home, profile, bridge string, models []Model) (*desktopAdmission, error) {
	path := options.nativeAccountProof
	candidate := false
	if options.nativeAccountCandidate && observer != nil {
		path = observer.QualificationDeclaration
		candidate = true
	}
	if path == "" {
		return nil, nil
	}
	// First strict decoding uses the mode's complete schema, then binds its paths
	// to current discovered values; evidence cannot select a different engine.
	var id desktopAdmissionIdentity
	if candidate {
		var d desktopCandidateDeclaration
		if _, e := readDesktopEvidence(path, &d); e != nil {
			return nil, e
		}
		id = d.Identity
	} else {
		var p desktopQualificationProof
		if _, e := readDesktopEvidence(path, &p); e != nil {
			return nil, e
		}
		id = p.Identity
	}
	current, e := desktopCompatibilityIdentity(bundle, home, profile, bridge, id.Runtime, id.Harness, id.Source, models)
	if e != nil {
		return nil, e
	}
	var a *desktopAdmission
	if candidate {
		a, e = readDesktopDeclaration(path, current, observer.Seconds, time.Now())
	} else {
		a, e = readDesktopProof(path, current)
	}
	if e != nil {
		return nil, e
	}
	a.protected, e = desktopProtectedSnapshot(home, bundle.engine, bridge)
	if e != nil {
		return nil, e
	}
	if e = a.consume(time.Now()); e != nil {
		return nil, e
	}
	return a, nil
}

func selectedDesktopAdmission(values []*desktopAdmission) *desktopAdmission {
	if len(values) == 1 {
		return values[0]
	}
	return nil
}
func checkDesktopPluginAdmission(home string, a *desktopAdmission) error {
	if a != nil {
		if e := a.checkFile(); e != nil {
			return e
		}
	}
	if a.permitsPlugins() {
		return nil
	}
	return refuseDesktopPluginRemoval(home)
}

func validateAdmissionScope(root string, d desktopCandidateDeclaration) error {
	required := d.Case == "service-switching" || d.Case == "history-resume" || d.Case == "review-routing" || d.Case == "launch-naming"
	if d.ScopeSHA256 == "" {
		if required {
			return admissionError("declared conversation scope required")
		}
		return nil
	}
	if !validDigest(d.ScopeSHA256) {
		return admissionError("scope digest invalid")
	}
	var scope map[string]json.RawMessage
	digest, e := readDesktopEvidence(filepath.Join(root, "scope.json"), &scope)
	if e != nil || digest != d.ScopeSHA256 {
		return admissionError("scope changed")
	}
	var schema, attempt, boundRoot string
	json.Unmarshal(scope["schema"], &schema)
	json.Unmarshal(scope["attempt"], &attempt)
	json.Unmarshal(scope["root"], &boundRoot)
	if schema != "tofa-observer-scope-v1" || attempt != d.Attempt || boundRoot != root {
		return admissionError("scope binding mismatch")
	}
	return nil
}

// Preservation inventory can retain inert supplier metadata links. Executables
// and the presentation package must resolve to live files inside this runtime.
func validateAdmissionRuntime(root string) error {
	resolved, e := filepath.EvalSymlinks(root)
	if e != nil || resolved != root {
		return admissionError("runtime root unavailable or indirect")
	}
	raw, e := readAdmissionBounded(filepath.Join(root, "runtime.json"), 1<<20)
	var manifest map[string]any
	if e != nil || len(raw) > 1<<20 || uniqueReviewJSON(raw, 0) != nil || json.Unmarshal(raw, &manifest) != nil || manifest["bundleFormatVersion"] != float64(2) || manifest["targetPlatform"] != "darwin" || manifest["targetArch"] != "arm64" {
		return admissionError("runtime manifest invalid")
	}
	for _, relative := range []string{"dependencies/node/bin/node", "dependencies/python/bin/python3", "dependencies/bin/override/soffice", "dependencies/bin/override/pdfinfo", "dependencies/bin/override/pdftoppm", "dependencies/node/node_modules/@oai/artifact-tool/package.json"} {
		path, e := filepath.EvalSymlinks(filepath.Join(root, relative))
		if e != nil || !withinPath(root, path) {
			return admissionError("required runtime path unavailable or external")
		}
		info, e := os.Stat(path)
		if e != nil || !info.Mode().IsRegular() || !strings.HasSuffix(relative, "package.json") && info.Mode().Perm()&0111 == 0 {
			return admissionError("required runtime executable unavailable")
		}
	}
	return nil
}
