import AppKit
import WebKit

final class AppDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate {
    private let server = ServerProcess()
    private let web = WebController()
    private var window: NSWindow!
    private var mainMenu: NSMenu!
    private var serverReady = false
    private var selfTest: SelfTest?
    private var quittingForUpdate = false
    let updater = Updater()
    private var pendingFiles: [URL] = []
    private var strings: [String: String] = UserDefaults.standard.dictionary(forKey: "strings") as? [String: String] ?? [:]

    func text(_ english: String) -> String { strings[english] ?? english }

    func applicationDidFinishLaunching(_ notification: Notification) {
        mainMenu = Menus.build(target: self)
        Menus.localize(mainMenu, strings)
        NSApp.mainMenu = mainMenu
        web.owner = self
        selfTest = SelfTest(web: web)
        makeWindow()
        NSApp.activate(ignoringOtherApps: true)
        server.onUnexpectedExit = { [weak self] in self?.fail("The server stopped unexpectedly.") }
        do {
            try server.start()
        } catch {
            return fail(error.localizedDescription)
        }
        server.waitUntilHealthy(timeout: 60) { [weak self] healthy in
            guard let self else { return }
            guard healthy else { return self.fail("The server did not start. Port 5565 may be in use.") }
            self.serverReady = true
            self.web.load("/")
            let files = self.pendingFiles
            self.pendingFiles = []
            if !files.isEmpty { self.importFiles(files) }
        }
    }

    private func makeWindow() {
        window = AppWindow(contentRect: NSRect(x: 0, y: 0, width: 1320, height: 860),
                           styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
        window.title = "VS Gammon"
        window.titleVisibility = .hidden
        window.titlebarAppearsTransparent = true
        window.minSize = NSSize(width: 480, height: 480)
        window.isReleasedWhenClosed = false
        window.delegate = self
        window.contentView = web.webView
        web.webView.isHidden = true
        applyAppearance(background: UserDefaults.standard.string(forKey: "background"), theme: UserDefaults.standard.string(forKey: "theme"))
        window.center()
        window.setFrameAutosaveName("main")
        window.makeKeyAndOrderFront(nil)
    }

    func pageDidLoad() {
        web.webView.isHidden = false
        selfTest?.pageDidLoad()
    }

    private func applyAppearance(background: String?, theme: String?) {
        if let theme { window.appearance = NSAppearance(named: theme == "dark" ? .darkAqua : .aqua) }
        window.backgroundColor = background.flatMap(Self.color(fromCSS:)) ?? .windowBackgroundColor
    }

    private static func color(fromCSS css: String) -> NSColor? {
        let parts = css.components(separatedBy: CharacterSet(charactersIn: "0123456789.").inverted).compactMap(Double.init)
        guard parts.count >= 3 else { return nil }
        return NSColor(srgbRed: parts[0] / 255, green: parts[1] / 255, blue: parts[2] / 255, alpha: 1)
    }

    /// Called from the page whenever language, theme or the due count changes.
    func applyState(_ state: [String: Any]) {
        if let menu = state["strings"] as? [String: String] {
            strings = menu
            UserDefaults.standard.set(menu, forKey: "strings")
            Menus.localize(mainMenu, menu)
        }
        let background = state["background"] as? String
        let theme = state["theme"] as? String
        if background != nil || theme != nil {
            UserDefaults.standard.set(background, forKey: "background")
            UserDefaults.standard.set(theme, forKey: "theme")
            applyAppearance(background: background, theme: theme)
        }
        if let due = state["due"] as? Int { NSApp.dockTile.badgeLabel = due > 0 ? String(due) : nil }
    }

    private func fail(_ reason: String) {
        let alert = NSAlert()
        alert.alertStyle = .critical
        alert.messageText = "VS Gammon could not start"
        alert.informativeText = "\(reason)\n\nDetails are in ~/Library/Logs/VS Gammon.log."
        alert.runModal()
        exit(1)
    }

    // MARK: Files

    func application(_ application: NSApplication, open urls: [URL]) { importFiles(urls) }

    func importFiles(_ urls: [URL]) {
        guard serverReady else { pendingFiles += urls; return }
        var request = URLRequest(url: serverBase.appendingPathComponent("api/matches"))
        request.httpMethod = "POST"
        let boundary = UUID().uuidString
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        var body = Data()
        for url in urls {
            guard let data = try? Data(contentsOf: url) else { continue }
            let name = url.lastPathComponent.replacingOccurrences(of: "\"", with: "")
            body.append(Data("--\(boundary)\r\nContent-Disposition: form-data; name=\"files\"; filename=\"\(name)\"\r\nContent-Type: text/plain\r\n\r\n".utf8))
            body.append(data)
            body.append(Data("\r\n".utf8))
        }
        body.append(Data("--\(boundary)--\r\n".utf8))
        URLSession.shared.uploadTask(with: request, from: body) { [weak self] _, _, _ in
            DispatchQueue.main.async {
                self?.web.load("/matches")
                self?.window.makeKeyAndOrderFront(nil)
            }
        }.resume()
    }

    @objc func importMatches(_ sender: Any?) {
        let panel = NSOpenPanel()
        panel.allowsMultipleSelection = true
        panel.canChooseDirectories = false
        panel.beginSheetModal(for: window) { [weak self] response in
            if response == .OK, let urls = Optional(panel.urls) { self?.importFiles(urls) }
        }
    }

    // MARK: Menu actions

    @objc func navigate(_ sender: NSMenuItem) { if let path = sender.representedObject as? String { web.load(path) } }
    @objc func runScript(_ sender: NSMenuItem) { if let js = sender.representedObject as? String { web.webView.evaluateJavaScript(js) } }
    @objc func goBack(_ sender: Any?) { web.webView.goBack() }
    @objc func goForward(_ sender: Any?) { web.webView.goForward() }
    @objc func reload(_ sender: Any?) { web.webView.reload() }
    @objc func openHelp(_ sender: Any?) { NSWorkspace.shared.open(URL(string: "https://github.com/ruolez/vs-gammon#readme")!) }
    @objc func openEngineSource(_ sender: Any?) { NSWorkspace.shared.open(URL(string: "https://ftp.gnu.org/gnu/gnubg/")!) }
    @objc func checkForUpdates(_ sender: Any?) { web.load("/settings#updates") }

    @objc func showAbout(_ sender: Any?) {
        let credits = NSAttributedString(string: "Analysis by GNU Backgammon, free software under the GNU GPL version 3.",
                                         attributes: [.foregroundColor: NSColor.secondaryLabelColor, .font: NSFont.systemFont(ofSize: 11)])
        NSApp.orderFrontStandardAboutPanel(options: [.credits: credits])
    }

    func installUpdate(reply: @escaping (Any?, String?) -> Void) {
        updater.install { [weak self] result in
            switch result {
            case .success:
                reply(["ok": true], nil)
                self?.quittingForUpdate = true
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) { NSApp.terminate(nil) }
            case .failure(Updater.Failure.moveToApplications):
                reply(["ok": false, "reason": "move"], nil)
            case .failure:
                reply(["ok": false, "reason": "failed"], nil)
            }
        }
    }

    // MARK: Quitting

    func windowShouldClose(_ sender: NSWindow) -> Bool {
        NSApp.terminate(nil)
        return false
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        window.makeKeyAndOrderFront(nil)
        return true
    }

    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        guard serverReady, !quittingForUpdate else { return .terminateNow }
        URLSession.shared.dataTask(with: serverBase.appendingPathComponent("api/matches")) { [weak self] data, _, _ in
            let matches = (data.flatMap { try? JSONSerialization.jsonObject(with: $0) } as? [String: Any])?["matches"] as? [[String: Any]] ?? []
            let busy = matches.contains { ["analyzing", "queued"].contains($0["status"] as? String ?? "") }
            DispatchQueue.main.async {
                guard let self else { return }
                NSApp.reply(toApplicationShouldTerminate: !busy || self.confirmQuit())
            }
        }.resume()
        return .terminateLater
    }

    private func confirmQuit() -> Bool {
        let alert = NSAlert()
        alert.messageText = text("Analysis is still running")
        alert.informativeText = text("It carries on from the start of that match next time you open VS Gammon.")
        alert.addButton(withTitle: text("Quit"))
        alert.addButton(withTitle: text("Cancel"))
        return alert.runModal() == .alertFirstButtonReturn
    }

    func applicationWillTerminate(_ notification: Notification) { server.stop() }
}
