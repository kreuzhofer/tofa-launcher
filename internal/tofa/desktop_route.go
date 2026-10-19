package tofa

import "sync/atomic"

// Only served by a live launch's authenticated loopback adapter. It is never
// written to the durable bridge or desktop settings.
type desktopRoute struct {
	Bridge              string
	Engine              string
	Home                string
	Overrides           []string
	InferenceCapability string `json:",omitempty"`
	ready               chan struct{}
	claim               chan int
	mainPID             *atomic.Int64
	mainModels          map[string]bool
	services            map[string]inferenceService
	namingUnavailable   string
}
