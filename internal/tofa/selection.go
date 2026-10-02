package tofa

import (
	_ "embed"
	"encoding/json"
	"errors"
	"fmt"
	"runtime"
	"slices"
)

//go:embed assets/model-verification.json
var verificationSnapshot []byte

var errUnverifiedCombination = errors.New("unverified combination")

func mainModelChoices(models []Model, target, route, guardian string, allow bool) ([]pickerChoice, error) {
	if len(models) == 0 {
		return nil, errors.New("no models available in this project's catalog")
	}
	choices := []pickerChoice{}
	for _, model := range models {
		status, err := selectionStatus(target, route, model.ID, guardian, allow)
		if errors.Is(err, errUnverifiedCombination) {
			continue
		}
		if err != nil {
			return nil, err
		}
		choice := pickerChoice{identity: model.ID, status: status}
		if _, err := metadataFor(model.ID); err != nil {
			if !allow {
				continue
			}
			choice.disabled = err.Error()
		}
		choices = append(choices, choice)
	}
	if len(choices) == 0 {
		return nil, errors.New("no supported main models for this target, route and Guardian; use --allow-unverified to inspect the available catalog for experimental selection")
	}
	return choices, nil
}

func validateAvailableRole(models []Model, role, identity string) error {
	found := false
	for _, model := range models {
		if model.ID == identity {
			found = true
			break
		}
	}
	if !found {
		return fmt.Errorf("%s model %s: not available in this project's catalog", role, identity)
	}
	if _, err := metadataFor(identity); err != nil {
		return fmt.Errorf("%s model %s: %w", role, identity, err)
	}
	return nil
}

// A record approves a complete role combination; evidence for a main or a
// Guardian in another launch does not transfer to this selection.
func selectionStatus(target, route, main, guardian string, allow bool) (string, error) {
	var snapshot struct {
		Records []struct {
			Target, Route, Main, Guardian, Status, Evidence string
			Platforms                                       []string
		}
	}
	if err := json.Unmarshal(verificationSnapshot, &snapshot); err != nil || snapshot.Records == nil {
		return "", errors.New("invalid bundled model verification records")
	}
	for _, record := range snapshot.Records {
		if record.Evidence == "" || (record.Status != "supported" && record.Status != "experimental") {
			return "", errors.New("invalid bundled model verification record")
		}
		if record.Target == target && record.Route == route && record.Main == main && record.Guardian == guardian && record.Status == "supported" {
			if len(record.Platforms) > 0 && !slices.Contains(record.Platforms, runtime.GOOS+"/"+runtime.GOARCH) {
				continue
			}
			return "supported", nil
		}
	}
	if !allow {
		return "", fmt.Errorf("%w for %s %s (main %s, Guardian %s); experimental selection requires --allow-unverified", errUnverifiedCombination, target, route, main, guardian)
	}
	return "experimental (unverified)", nil
}
