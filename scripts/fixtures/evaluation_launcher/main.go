// A test executable using the real launcher and adapter with synthetic credentials.
// The production CLI deliberately has no endpoint override.
package main

import (
	"errors"
	"fmt"
	"net/http"
	"net/url"
	"os"
	"path/filepath"

	"github.com/kreuzhofer/tofa-launcher/internal/tofa"
)

func main() {
	// Saved engine references exec the bundled engine. They must not allocate
	// another credential store whose deferred cleanup exec would discard.
	if executable, err := os.Executable(); err == nil && filepath.Base(executable) == "tofa-desktop-engine" {
		app := tofa.App{}
		if err := app.Run(os.Args[1:]); err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(1)
		}
		return
	}
	if len(os.Args) == 2 && os.Args[1] == "--version" {
		fmt.Println("tofa evaluation-fixture")
		return
	}
	endpoint := os.Getenv("FIXTURE_ENDPOINT")
	target, err := url.Parse(endpoint)
	if err != nil || target.Scheme != "http" || target.Hostname() != "127.0.0.1" || target.Port() == "" || target.Path != "" || target.RawQuery != "" || target.User != nil || target.Fragment != "" {
		panic("fixture requires a loopback provider")
	}
	if err := run(endpoint); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func run(endpoint string) (result error) {
	dir := os.Getenv("FIXTURE_RETAINED_DIR")
	retained := dir != ""
	if retained {
		if !filepath.IsAbs(dir) {
			return errors.New("fixture retained directory must be absolute")
		}
		const marker = "tofa-evaluation-store-v1\n"
		path := filepath.Join(dir, ".evaluation-store")
		if err := os.Mkdir(dir, 0700); err == nil {
			if err := os.WriteFile(path, []byte(marker), 0600); err != nil {
				return err
			}
		} else if !errors.Is(err, os.ErrExist) {
			return err
		}
		info, err := os.Lstat(dir)
		if err != nil || !info.IsDir() || info.Mode().Perm()&0077 != 0 {
			return errors.New("fixture retained directory must be a private real directory")
		}
		info, err = os.Lstat(path)
		if err != nil || !info.Mode().IsRegular() || info.Mode().Perm()&0077 != 0 {
			return errors.New("fixture retained directory has no private ownership marker")
		}
		data, err := os.ReadFile(path)
		if err != nil || string(data) != marker {
			return errors.New("fixture retained directory ownership does not match")
		}
	} else {
		var err error
		dir, err = os.MkdirTemp("", "tofa-synthetic-store-")
		if err != nil {
			return err
		}
		defer func() { result = errors.Join(result, os.RemoveAll(dir)) }()
	}
	store := tofa.Store{Dir: dir}
	if err := store.Login("synthetic-project", "synthetic-fixture-token", "file"); err != nil {
		return err
	}
	if retained {
		// Desktop can persist this store's bridge in shared MCP definitions.
		// Retain that executable; remove only the fixture credential on clean exit.
		defer func() { result = errors.Join(result, store.Logout()) }()
	}
	app := tofa.App{Dir: dir, Endpoint: endpoint, HTTP: &http.Client{Transport: &http.Transport{Proxy: nil}}, Version: "evaluation-fixture"}
	return app.Run(os.Args[1:])
}
