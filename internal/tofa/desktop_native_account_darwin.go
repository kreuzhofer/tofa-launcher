package tofa

import (
	"context"
	"encoding/json"
	"errors"
	"strconv"
	"time"
)

// Stable identity for NEW routed conversations; never replaces either openai or
// nebius-tofa in existing history. This candidate remains qualification-only.
const nativeDesktopProvider = "tofa-native-router"
const nativeDesktopHeader = "X-TOFA-Launch"
const nativeDesktopInferenceEnv = "TOFA_DESKTOP_INFERENCE"

func nativeDesktopProviderOverrides(endpoint string) []string {
	prefix := "model_providers." + nativeDesktopProvider + "."
	return []string{
		"model_provider=" + strconv.Quote(nativeDesktopProvider),
		prefix + `name="TOFA native-account router"`, prefix + "base_url=" + strconv.Quote(endpoint),
		prefix + `wire_api="responses"`, prefix + `requires_openai_auth=true`,
		prefix + `supports_websockets=false`, prefix + `request_max_retries=0`, prefix + `stream_max_retries=0`,
		prefix + `env_http_headers={"X-TOFA-Launch"="TOFA_DESKTOP_INFERENCE"}`,
	}
}

func checkDesktopNativeAccount(ctx context.Context, engine, home, profile, workspace, root string) error {
	ctx, cancel := context.WithTimeout(ctx, 15*time.Second)
	defer cancel()
	client, err := openDesktopConfig(ctx, engine, home, profile, workspace, root)
	if err != nil {
		return err
	}
	config, err := client.call("config/read", map[string]any{"includeLayers": true, "cwd": workspace})
	if err == nil {
		effective, _ := config["config"].(map[string]any)
		providers, _ := effective["model_providers"].(map[string]any)
		if providers[nativeDesktopProvider] != nil {
			err = errors.New("native-account routing provider conflicts with an existing definition; preserve it and resolve ownership before qualification")
		}
	}
	if err == nil {
		requirements, readErr := client.call("configRequirements/read", map[string]any{})
		err = readErr
		if err == nil {
			values, _ := requirements["requirements"].(map[string]any)
			err = checkDesktopRequirements(values)
		}
	}
	client.close()
	if err != nil {
		return err
	}
	client, err = openDesktopConfig(ctx, engine, home, profile, workspace, root, nativeDesktopProviderOverrides("http://127.0.0.1:0")...)
	if err != nil {
		return err
	}
	defer client.close()
	result, err := client.call("account/read", map[string]any{"refreshToken": false})
	if err != nil {
		return errors.New("existing ChatGPT sign-in could not be verified; open ordinary Desktop and sign in before qualifying TOFA")
	}
	account, _ := result["account"].(map[string]any)
	if account["type"] != "chatgpt" || result["requiresOpenaiAuth"] != true {
		return errors.New("native-account routing requires an existing ChatGPT sign-in; sign in through ordinary Desktop before qualifying TOFA")
	}
	return nil
}

// Add exclusions to the resolved native policy rather than replacing a user's
// restrictions. Only this list is overridden; inherit/include/set remain native.
func desktopSecretExclusions(ctx context.Context, engine, home, profile, workspace, root string) (string, error) {
	client, err := openDesktopConfig(ctx, engine, home, profile, workspace, root)
	if err != nil {
		return "", err
	}
	defer client.close()
	result, err := client.call("config/read", map[string]any{"includeLayers": true, "cwd": workspace})
	if err != nil {
		return "", err
	}
	config, _ := result["config"].(map[string]any)
	policy, _ := config["shell_environment_policy"].(map[string]any)
	excluded := []string{}
	if policy["exclude"] != nil {
		values, ok := policy["exclude"].([]any)
		if !ok {
			return "", errors.New("unsupported shell environment exclusion policy")
		}
		for _, v := range values {
			s, ok := v.(string)
			if !ok {
				return "", errors.New("unsupported shell environment exclusion policy")
			}
			excluded = append(excluded, s)
		}
	}
	excluded = append(excluded, "TOFA_*")
	raw, _ := json.Marshal(excluded)
	return "shell_environment_policy.exclude=" + string(raw), nil
}
