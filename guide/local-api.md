# Opening the local workspace

Run `deykit serve` to start the local browser workspace. It listens on
`127.0.0.1:8765` and opens the browser after the service is ready. Use
`deykit serve --port 0` to let the operating system choose a port, or
`deykit serve --no-open` to keep the browser closed. Passing the root
`--project PATH` option explicitly opens that project when the service starts.

The first screen does not open a project. Choose Open project or Create project
and enter an absolute local folder path. The recent list stores project paths as
local preferences. Try support demo creates an authored fixture project that
needs no provider key. The demo is example content, not measured model output.

The service accepts only its exact loopback address and a same-origin browser
session. Restarting the service ends the current browser session; use Reconnect
to establish a fresh one. Project folder paths and typed values remain in the
form while reconnecting.
