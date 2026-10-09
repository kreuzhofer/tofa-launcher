# Nebius Agent Launcher

A launcher that connects locally installed coding agents and desktop applications
to Nebius Token Factory.

## Language

**Launcher**:
The standalone command-line tool that starts a target client with settings for
Nebius Token Factory.
_Avoid_: Agent, inference server

**Target client**:
A locally installed coding agent or desktop application that the launcher connects
to Nebius Token Factory. The target client has its own installation prerequisites.

**Token Factory**:
The Nebius inference service that supplies models to target clients launched by
this tool.
_Avoid_: Local model runtime

**Direct connection**:
A target client's inference connection straight to Token Factory, without a
launcher-provided request adapter.

**Request adapter**:
An intermediary for a launched target client that reconciles demonstrated request
format differences with Token Factory while retaining the inference protocol.

**Adapted connection**:
A target client's inference connection to Token Factory through a request adapter
whose lifetime is tied to that launch.

**Available model**:
A model listed in the selected Token Factory project's catalog. Availability
alone does not establish compatibility with a target client.

**Main model**:
The model selected to conduct the user's conversation and propose tool actions
in a target client.

**Guardian model**:
The model selected to assess automatic approval requests for proposed actions.
The target client enforces execution according to its approval policy and the
assessment result.

**Supported model**:
An available model verified with a particular target client to handle streaming,
tool calls, and continued conversation. Support applies to the tested combination.
_Avoid_: Available model as a synonym for supported model

**Capability evaluation**:
An assessment of how a main model performs a defined user workflow in a particular
target client and environment. Its results describe task-specific strengths and
gaps separately from the verified compatibility represented by a Supported model.

**Experimental selection**:
Use of an available model in a target-client role whose compatibility has not
yet been verified. Experimental status is shown explicitly. The desktop enables
these choices by default; CLI selection requires explicit opt-in. Selection
requires sufficient model metadata and a compatible client contract; it does not
establish support.
