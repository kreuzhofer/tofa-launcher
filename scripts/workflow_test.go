package scripts

import (
	"os"
	"os/exec"
	"path/filepath"
	"reflect"
	"sort"
	"strings"
	"testing"

	"gopkg.in/yaml.v3"
)

// The checked-in Actions document is the public release automation interface.
// Keep graph/permission assertions here; command behavior is exercised offline
// by release_test.py without creating disposable public releases.
func TestReleaseWorkflow(t *testing.T) {
	data, err := os.ReadFile("../.github/workflows/prototype.yml")
	if err != nil {
		t.Fatal(err)
	}
	var workflow struct {
		On struct {
			Push struct{ Branches, Tags []string }
		}
		Permissions map[string]string
		Jobs        map[string]struct {
			Needs       []string
			If          string
			Permissions map[string]string
			Steps       []struct {
				ID, Uses, Run string
				With          map[string]string
				Env           map[string]string
			}
		}
	}
	if err := yaml.Unmarshal(data, &workflow); err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(workflow.On.Push.Tags, []string{"v*"}) || len(workflow.On.Push.Branches) == 0 {
		t.Fatal("CI must trigger on version tags and ordinary branch pushes")
	}
	if !reflect.DeepEqual(workflow.Permissions, map[string]string{"contents": "read"}) {
		t.Fatal("default credentials must be read-only")
	}
	publish, ok := workflow.Jobs["publish"]
	if !ok {
		t.Fatal("missing publication job")
	}
	sort.Strings(publish.Needs)
	if !reflect.DeepEqual(publish.Needs, []string{"artifacts", "native"}) {
		t.Fatal("publication must depend on every required job")
	}
	// Evaluate the boolean/string expression against the event and job-result
	// boundary, allowing equivalent term ordering and parenthesization. Python's
	// operators implement the subset of Actions expressions used by this gate.
	conditionCheck := exec.Command("python3", "-c", `
import itertools, sys
from types import SimpleNamespace as NS
expression = sys.argv[1].removeprefix('${{').removesuffix('}}').strip()
expression = expression.replace('&&', ' and ').replace('||', ' or ')
for event, ref, native, artifacts in itertools.product(
        ['push', 'pull_request', 'workflow_dispatch'],
        ['refs/heads/main', 'refs/tags/v0.1.0-rc.1', 'refs/tags/v1.0.0'],
        ['success', 'failure', 'cancelled', 'skipped', ''],
        ['success', 'failure', 'cancelled', 'skipped', '']):
    context = dict(github=NS(event_name=event, ref=ref),
                   needs=NS(native=NS(result=native), artifacts=NS(result=artifacts)),
                   startsWith=lambda value, prefix: value.startswith(prefix))
    actual = eval(expression, {'__builtins__': {}}, context)
    expected = event == 'push' and ref.startswith('refs/tags/') and native == artifacts == 'success'
    assert actual == expected, (event, ref, native, artifacts, actual)
`, publish.If)
	if output, err := conditionCheck.CombinedOutput(); err != nil {
		t.Fatalf("publication gate permits or rejects the wrong conditions: %v\n%s", err, output)
	}
	if !reflect.DeepEqual(publish.Permissions, map[string]string{"contents": "write"}) {
		t.Fatal("only publication needs contents: write")
	}
	for name, job := range workflow.Jobs {
		if name != "publish" && len(job.Permissions) != 0 {
			t.Fatalf("unexpected permission override for %s", name)
		}
	}
	for _, name := range []string{"native", "publish"} {
		job := workflow.Jobs[name]
		download := false
		for _, step := range job.Steps {
			if step.Uses == "actions/download-artifact@v4" && step.With["name"] == "checked-candidate" && step.With["path"] == "dist" {
				download = true
			}
			if strings.Contains(step.Run, "scripts/build.sh") {
				t.Fatalf("%s must consume the original candidate, not rebuild", name)
			}
		}
		if !download {
			t.Fatalf("%s must download the same checked candidate", name)
		}
	}
	if !reflect.DeepEqual(workflow.Jobs["native"].Needs, []string{"artifacts"}) {
		t.Fatal("native checks must wait for the candidate")
	}
	for _, step := range workflow.Jobs["artifacts"].Steps {
		if step.ID != "version" {
			continue
		}
		output := filepath.Join(t.TempDir(), "outputs")
		cmd := exec.Command("bash", "-e", "-o", "pipefail", "-c", step.Run)
		cmd.Dir = ".."
		cmd.Env = append(os.Environ(), "GITHUB_REF=refs/tags/v01.0.0", "GITHUB_OUTPUT="+output)
		if out, err := cmd.CombinedOutput(); err == nil {
			t.Fatalf("invalid version must fail the workflow step: %s", out)
		}
		if data, _ := os.ReadFile(output); len(data) != 0 {
			t.Fatal("invalid version must not emit a build version")
		}
	}
}
