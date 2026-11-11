package tofa

import (
	"errors"
	"os"
	"path/filepath"
)

// This identity binds one startup's probes to the executables being launched.
// It is never compared to another installation or a historical receipt. Runtime,
// model catalog and plugin cache updates are not admission prerequisites.
func desktopLocalIdentity(bundle desktopBundle, home, profile string) (desktopAdmissionIdentity, error) {
	identity := desktopAdmissionIdentity{Home: home, Profile: profile, Hashes: map[string]string{}}
	launcher, err := os.Executable()
	if err != nil {
		return identity, err
	}
	for name, path := range map[string]string{
		"launcher":         launcher,
		"engine":           bundle.engine,
		"application":      bundle.executable,
		"application_info": filepath.Join(filepath.Dir(filepath.Dir(bundle.executable)), "Info.plist"),
	} {
		hash, err := hashAdmissionFile(path)
		if err != nil {
			return identity, errors.New("could not verify installed Desktop component: " + name)
		}
		identity.Hashes[name] = hash
	}
	return identity, nil
}

func (a *desktopAdmission) startupDrift(component string) error {
	if a.mode == "local" {
		return errors.New("Desktop " + component + " drifted during startup; quit Desktop and retry after resolving the change")
	}
	return admissionError(component + " drifted")
}
