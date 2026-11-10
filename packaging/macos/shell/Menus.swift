import AppKit

/// Items are titled in English; `localize` retitles them from the strings the web app sends, keyed by English title.
enum Menus {
    static func item(_ title: String, _ action: Selector?, _ key: String = "", _ modifiers: NSEvent.ModifierFlags = .command, tag: Int = 0, represented: Any? = nil) -> NSMenuItem {
        let item = NSMenuItem(title: title, action: action, keyEquivalent: key)
        item.keyEquivalentModifierMask = modifiers
        item.identifier = NSUserInterfaceItemIdentifier(title)
        item.tag = tag
        item.representedObject = represented
        return item
    }

    static func menu(_ title: String, _ items: [NSMenuItem]) -> NSMenuItem {
        let holder = NSMenuItem(title: title, action: nil, keyEquivalent: "")
        holder.identifier = NSUserInterfaceItemIdentifier(title)
        let submenu = NSMenu(title: title)
        items.forEach(submenu.addItem)
        holder.submenu = submenu
        return holder
    }

    static func build(target: AppDelegate) -> NSMenu {
        let sel = #selector(AppDelegate.navigate(_:))
        let main = NSMenu()
        let app = NSMenuItem()
        app.submenu = NSMenu()
        [
            item("About VS Gammon", #selector(AppDelegate.showAbout(_:))),
            item("Check for Updates…", #selector(AppDelegate.checkForUpdates(_:))),
            .separator(),
            item("Settings…", sel, ",", represented: "/settings"),
            .separator(),
            item("Hide VS Gammon", #selector(NSApplication.hide(_:)), "h"),
            item("Hide Others", #selector(NSApplication.hideOtherApplications(_:)), "h", [.command, .option]),
            item("Show All", #selector(NSApplication.unhideAllApplications(_:))),
            .separator(),
            item("Quit VS Gammon", #selector(NSApplication.terminate(_:)), "q"),
        ].forEach(app.submenu!.addItem)
        main.addItem(app)
        main.addItem(menu("File", [
            item("Import Matches…", #selector(AppDelegate.importMatches(_:)), "o"),
            .separator(),
            item("Close Window", #selector(NSWindow.performClose(_:)), "w"),
        ]))
        main.addItem(menu("Edit", [
            item("Undo", Selector(("undo:")), "z"),
            item("Redo", Selector(("redo:")), "z", [.command, .shift]),
            .separator(),
            item("Cut", #selector(NSText.cut(_:)), "x"),
            item("Copy", #selector(NSText.copy(_:)), "c"),
            item("Paste", #selector(NSText.paste(_:)), "v"),
            item("Select All", #selector(NSText.selectAll(_:)), "a"),
        ]))
        let run = #selector(AppDelegate.runScript(_:))
        main.addItem(menu("View", [
            item("Dashboard", sel, "1", represented: "/"),
            item("Practice", sel, "2", represented: "/practice"),
            item("Review", sel, "3", represented: "/review"),
            item("Matches", sel, "4", represented: "/matches"),
            item("History", sel, "5", represented: "/history"),
            .separator(),
            item("Back", #selector(AppDelegate.goBack(_:)), "["),
            item("Forward", #selector(AppDelegate.goForward(_:)), "]"),
            item("Reload", #selector(AppDelegate.reload(_:)), "r"),
            .separator(),
            item("Larger Text", run, "=", represented: "TextSize.step(1)"),
            item("Smaller Text", run, "-", represented: "TextSize.step(-1)"),
            item("Actual Size", run, "0", represented: "TextSize.set(100)"),
            .separator(),
            menu("Theme", [
                item("Light", run, represented: "Theme.set('light')"),
                item("Dark", run, represented: "Theme.set('dark')"),
                item("Match System", run, represented: "Theme.set('system')"),
            ]),
            menu("Language", [
                item("English", run, represented: "I18n.set('en');location.reload()"),
                item("Русский", run, represented: "I18n.set('ru');location.reload()"),
            ]),
            item("Toggle Sidebar", run, "\\", represented: "Shell.toggleCollapse()"),
            .separator(),
            item("Enter Full Screen", #selector(NSWindow.toggleFullScreen(_:)), "f", [.command, .control]),
        ]))
        let window = menu("Window", [
            item("Minimize", #selector(NSWindow.performMiniaturize(_:)), "m"),
            item("Zoom", #selector(NSWindow.performZoom(_:))),
        ])
        main.addItem(window)
        NSApp.windowsMenu = window.submenu
        main.addItem(menu("Help", [
            item("VS Gammon Help", #selector(AppDelegate.openHelp(_:))),
            item("GNU Backgammon Source Code", #selector(AppDelegate.openEngineSource(_:))),
        ]))
        return main
    }

    static func localize(_ menu: NSMenu, _ strings: [String: String]) {
        for item in menu.items {
            if let key = item.identifier?.rawValue, let title = strings[key] {
                item.title = title
                item.submenu?.title = title
            }
            if let submenu = item.submenu { localize(submenu, strings) }
        }
    }
}
