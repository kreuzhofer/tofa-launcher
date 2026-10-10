//go:build !darwin

package tofa

import (
	"context"
	"errors"
)

func evaluationDesktopPreflight(context.Context, string) error {
	return errors.New("Desktop evaluation requires macOS arm64")
}

func (a *App) launchDesktop(context.Context, Store, []string) error {
	return errors.New("experimental codex-desktop requires the tested macOS arm64 application; use launch codex for the CLI")
}

func runDesktopBridge([]string) error {
	return errors.New("desktop engine bridge requires macOS")
}

func (a *App) desktopLifecycle(context.Context, []string) error {
	return errors.New("desktop installed lifecycle requires macOS")
}
