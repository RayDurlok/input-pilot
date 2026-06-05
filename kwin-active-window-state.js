const DBUS_SERVICE = "io.inputpilot.Automation";
const DBUS_PATH = "/io/inputpilot/Automation";
const DBUS_INTERFACE = "io.inputpilot.Automation";

function textProperty(window, propertyName) {
    try {
        const value = window ? window[propertyName] : "";
        return value === undefined || value === null ? "" : String(value);
    } catch (error) {
        return "";
    }
}

function boolProperty(window, propertyName) {
    try {
        return window ? Boolean(window[propertyName]) : false;
    } catch (error) {
        return false;
    }
}

function intProperty(window, propertyName) {
    try {
        const value = window ? Number(window[propertyName]) : 0;
        return Number.isFinite(value) ? Math.trunc(value) : 0;
    } catch (error) {
        return 0;
    }
}

function typeText(window) {
    const flags = [];
    if (boolProperty(window, "dialog")) {
        flags.push("dialog");
    }
    if (boolProperty(window, "modal")) {
        flags.push("modal");
    }
    if (boolProperty(window, "transient")) {
        flags.push("transient");
    }
    if (boolProperty(window, "normalWindow")) {
        flags.push("normal");
    }
    const type = textProperty(window, "windowType");
    if (type) {
        flags.push("type=" + type);
    }
    return flags.join(",");
}

function activeWindowLooksLikeFileDialog(window, caption, resourceClass, resourceName, role) {
    if (!window) {
        return false;
    }

    const haystack = [
        caption,
        resourceClass,
        resourceName,
        role,
    ].join(" ").toLowerCase();

    const strongMarkers = [
        "file dialog",
        "filedialog",
        "file chooser",
        "filechooser",
        "gtkfilechooser",
        "kfilewidget",
        "kfiledialog",
        "enter name of file to save",
        "name of file to save",
        "file to save",
    ];
    for (let i = 0; i < strongMarkers.length; i++) {
        if (haystack.indexOf(strongMarkers[i]) !== -1) {
            return true;
        }
    }

    const portalDialog = haystack.indexOf("portal.desktop") !== -1;
    const portalMarkers = [
        "file",
        "folder",
        "save",
        "open",
        "datei",
        "ordner",
        "speichern",
        "öffnen",
    ];
    if (portalDialog) {
        for (let i = 0; i < portalMarkers.length; i++) {
            if (haystack.indexOf(portalMarkers[i]) !== -1) {
                return true;
            }
        }
    }

    const type = textProperty(window, "windowType");
    const dialogLike = boolProperty(window, "dialog")
        || boolProperty(window, "modal")
        || boolProperty(window, "transient")
        || !boolProperty(window, "normalWindow")
        || (type !== "" && type !== "0");
    if (!dialogLike) {
        return false;
    }

    const dialogMarkers = [
        "open file",
        "save file",
        "save as",
        "select file",
        "select folder",
        "choose file",
        "choose folder",
        "datei öffnen",
        "datei speichern",
        "speichern unter",
        "ordner auswählen",
        "datei auswählen",
        "öffnen",
        "speichern",
    ];

    for (let i = 0; i < dialogMarkers.length; i++) {
        if (haystack.indexOf(dialogMarkers[i]) !== -1) {
            return true;
        }
    }
    return false;
}

function reportActiveWindow() {
    const window = workspace.activeWindow;
    const caption = textProperty(window, "caption");
    const resourceClass = textProperty(window, "resourceClass");
    const resourceName = textProperty(window, "resourceName");
    const role = textProperty(window, "windowRole");
    const windowType = typeText(window);
    const windowPid = intProperty(window, "pid");
    const isFileDialog = activeWindowLooksLikeFileDialog(
        window,
        caption,
        resourceClass,
        resourceName,
        role
    );

    callDBus(
        DBUS_SERVICE,
        DBUS_PATH,
        DBUS_INTERFACE,
        "SetActiveWindow",
        isFileDialog,
        caption,
        resourceClass,
        resourceName,
        role,
        windowType,
        windowPid
    );
}

workspace.windowActivated.connect(reportActiveWindow);
reportActiveWindow();
