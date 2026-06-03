const p = workspace.cursorPos;
callDBus(
    "io.inputpilot.Automation",
    "/io/inputpilot/Automation",
    "io.inputpilot.Automation",
    "SetCursorPosition",
    p.x,
    p.y
);
