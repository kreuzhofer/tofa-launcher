package tofa

import (
	_ "embed"
	"encoding/json"
	"slices"
)

// The naming role is deliberately separate from picker/main/Guardian metadata.
//
//go:embed assets/desktop-naming.json
var desktopNamingSnapshot []byte

func desktopNamingUnavailable(models []Model) string {
	var snapshot struct {
		Model struct {
			ID       string   `json:"model_id"`
			Type     string   `json:"model_type"`
			Context  int      `json:"max_model_len"`
			UseCases []string `json:"use_cases"`
		} `json:"model"`
	}
	if json.Unmarshal(desktopNamingSnapshot, &snapshot) != nil || snapshot.Model.ID != desktopNamingModel ||
		snapshot.Model.Type != "text2text" || snapshot.Model.Context <= 4096 ||
		!slices.Contains(snapshot.Model.UseCases, "responses_api") || !slices.Contains(snapshot.Model.UseCases, "function_calling") {
		return "naming model " + desktopNamingModel + " has incompatible bundled metadata; automatic titles are unavailable"
	}
	for _, model := range models {
		if model.ID == desktopNamingModel {
			return ""
		}
	}
	return "naming model " + desktopNamingModel + " is unavailable in this project's catalog; automatic titles are unavailable; no fallback"
}
