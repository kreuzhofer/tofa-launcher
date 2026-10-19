package tofa

import (
	"errors"
	"flag"
	"runtime"
)

// Parse before onboarding so invalid invocations never solicit credentials.
// An empty target represents the bare launch, whose target is still to be picked.
type launchOptions struct {
	model, guardian, project, bundle string
	allow, direct, modelSelected     bool
	extra                            []string
	evaluation                       string
	nativeAccountCandidate           bool
	nativeAccountProof               string
}

func parseLaunchOptions(target string, args []string) (launchOptions, error) {
	var o launchOptions
	fs := flags("launch")
	fs.StringVar(&o.model, "model", "", "")
	fs.StringVar(&o.guardian, "guardian-model", "", "")
	fs.StringVar(&o.project, "project-id", "", "")
	fs.BoolVar(&o.allow, "allow-unverified", false, "")
	fs.StringVar(&o.evaluation, "evaluation-observer", "", "")
	if target != "codex-desktop" {
		fs.StringVar(&o.guardian, "evaluation-guardian-model", "", "")
		fs.BoolVar(&o.direct, "direct", false, "")
	}
	if target == "codex-desktop" {
		fs.BoolVar(&o.nativeAccountCandidate, "native-account-candidate", false, "")
		fs.StringVar(&o.nativeAccountProof, "native-account-proof", "", "")
	}
	if target != "codex" {
		fs.StringVar(&o.bundle, "app-bundle", "", "")
	}
	if err := fs.Parse(args); err != nil {
		return o, err
	}
	o.extra = fs.Args()
	if o.nativeAccountProof != "" && (o.nativeAccountCandidate || o.evaluation != "") {
		return o, errors.New("choose either bounded native candidate evaluation or qualified native-account proof")
	}
	if o.nativeAccountCandidate && o.evaluation == "" {
		return o, errors.New("native-account candidate requires a bounded evaluation observer; ordinary Desktop qualification remains pending")
	}
	if o.evaluation != "" && o.direct {
		return o, errors.New("evaluation requires the adapted connection")
	}
	guardians := 0
	projectSelected := false
	fs.Visit(func(f *flag.Flag) {
		o.modelSelected = o.modelSelected || f.Name == "model"
		projectSelected = projectSelected || f.Name == "project-id"
		if f.Name == "guardian-model" || f.Name == "evaluation-guardian-model" {
			guardians++
		}
	})
	if o.modelSelected && !validText(o.model, 512) {
		if target == "codex-desktop" {
			return o, errors.New("specify a valid explicit --model ID; see tofa models")
		}
		return o, errors.New("specify a valid --model ID; see tofa models")
	}
	if projectSelected && !validText(o.project, 256) {
		return o, errors.New("invalid project ID")
	}
	if guardians > 1 {
		return o, errors.New("use only one of --guardian-model and --evaluation-guardian-model")
	}
	if guardians > 0 && (!validText(o.guardian, 512) || o.direct) {
		return o, errors.New("Guardian requires a valid model ID and the adapted connection")
	}
	if !o.direct && guardians == 0 {
		o.guardian = "zai-org/GLM-5.3-Flash"
	}
	if target == "codex-desktop" {
		if runtime.GOOS != "darwin" || runtime.GOARCH != "arm64" {
			return o, errors.New("codex-desktop requires macOS arm64; use launch codex for the CLI")
		}
		if len(o.extra) != 0 {
			return o, errors.New("codex-desktop does not accept client arguments or routing overrides")
		}
	} else if _, err := childArgs(o.model, o.project, Endpoint, o.extra); err != nil {
		return o, err
	}
	return o, nil
}
