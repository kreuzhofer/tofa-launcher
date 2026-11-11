package tofa

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"io"
	"os"
	"path/filepath"
	"reflect"
	"sort"
	"strings"
	"syscall"
)

// Optional qualification evidence, never an ordinary-launch prerequisite.
// The private contract retains exact engine-generated inventories. No path
// prefix alone authorizes a refresh, and the full raw skill hash stays recorded.
type desktopSystemSkills struct {
	Path     string   `json:"path"`
	SHA256   string   `json:"sha256"`
	Accepted []string `json:"accepted_skills_sha256"`
}
type desktopSystemSkillsContract struct {
	Schema  string `json:"schema"`
	Sources []struct {
		Engine  string            `json:"engine"`
		SHA256  string            `json:"engine_sha256"`
		Version string            `json:"version"`
		Files   map[string]string `json:"files"`
	} `json:"sources"`
}

func systemSkillsDigest(value string, evidence *desktopSystemSkills) string {
	if evidence != nil {
		for _, accepted := range evidence.Accepted {
			if value == accepted {
				raw, _ := json.Marshal(evidence.Accepted)
				return digestBytes(raw)
			}
		}
	}
	return value
}

// Compute the allowed aggregates from the CURRENT user files and the pinned
// generated inventories. Thus a changed user file changes every allowed hash
// and cannot compare equal to the original declaration.
func bindDesktopSystemSkills(id *desktopAdmissionIdentity, ref *desktopSystemSkills, entries map[string]string) error {
	return bindDesktopSystemSkillsEvidence(id, ref, entries, true)
}

// Historical linkage uses its retained contract, never today's executable bytes.
func bindDesktopSystemSkillsEvidence(id *desktopAdmissionIdentity, ref *desktopSystemSkills, entries map[string]string, live bool) error {
	if ref == nil {
		return nil
	}
	var contract desktopSystemSkillsContract
	digest, e := readDesktopEvidence(ref.Path, &contract)
	if e != nil {
		return e
	}
	if ref.SHA256 != "" && ref.SHA256 != digest {
		return admissionError("system skills contract changed")
	}
	if contract.Schema != "tofa-generated-system-skills-v1" || len(contract.Sources) < 1 || len(contract.Sources) > 4 {
		return admissionError("system skills contract invalid")
	}
	if entries == nil {
		entries, e = admissionTreeEntries(filepath.Join(id.Home, "skills"), "", "")
		if e != nil {
			return e
		}
	}
	raw, _ := json.Marshal(entries)
	if digestBytes(raw) != id.Hashes["skills"] {
		return admissionError("skills changed during snapshot")
	}
	user, system := map[string]string{}, map[string]string{}
	for path, value := range entries {
		if strings.HasPrefix(path, ".system/") {
			system[path] = value
		} else {
			user[path] = value
		}
	}
	// A root symlink, absent tree, or unobserved version never qualifies.
	if _, exists := entries[".system"]; exists {
		return admissionError("system skills root must be a directory")
	}
	matched := false
	accepted := map[string]bool{}
	for _, source := range contract.Sources {
		if !filepath.IsAbs(source.Engine) || !validDigest(source.SHA256) || !validText(source.Version, 256) || len(source.Files) < 2 || len(source.Files) > 4096 {
			return admissionError("system skills source invalid")
		}
		if live {
			actual, e := hashSystemSkillsEngine(source.Engine)
			if e != nil || actual != source.SHA256 {
				return admissionError("system skills source engine changed or is not a regular executable")
			}
		}
		if !validDigest(source.Files[".system/.codex-system-skills.marker"]) {
			return admissionError("system skills marker missing")
		}
		merged := map[string]string{}
		for path, value := range user {
			merged[path] = value
		}
		for path, value := range source.Files {
			if !strings.HasPrefix(path, ".system/") || filepath.Clean(path) != path || strings.Contains(path, "\\") || !validDigest(value) {
				return admissionError("system skills inventory invalid")
			}
			merged[path] = value
		}
		if reflect.DeepEqual(system, source.Files) {
			matched = true
		}
		raw, _ := json.Marshal(merged)
		accepted[digestBytes(raw)] = true
	}
	if !matched {
		return admissionError("system skills do not match a verified generated inventory")
	}
	values := make([]string, 0, len(accepted))
	for hash := range accepted {
		values = append(values, hash)
	}
	sort.Strings(values)
	path, e := privateEvidencePath(ref.Path, false)
	if e != nil {
		return e
	}
	id.SystemSkills = &desktopSystemSkills{Path: path, SHA256: digest, Accepted: values}
	return nil
}

// Nonblocking open refuses FIFOs/devices without waiting for a writer. Inspect
// the opened descriptor, not just a path that can change before the read.
func hashSystemSkillsEngine(path string) (string, error) {
	fd, e := syscall.Open(path, syscall.O_RDONLY|syscall.O_NOFOLLOW|syscall.O_NONBLOCK, 0)
	if e != nil {
		return "", e
	}
	file := os.NewFile(uintptr(fd), path)
	defer file.Close()
	info, e := file.Stat()
	if e != nil || !info.Mode().IsRegular() || info.Mode().Perm()&0111 == 0 || info.Size() > 1<<30 {
		return "", admissionError("invalid system skills source executable")
	}
	hash := sha256.New()
	n, e := io.Copy(hash, io.LimitReader(file, (1<<30)+1))
	if e != nil || n > 1<<30 {
		return "", admissionError("invalid system skills source size")
	}
	return hex.EncodeToString(hash.Sum(nil)), nil
}
