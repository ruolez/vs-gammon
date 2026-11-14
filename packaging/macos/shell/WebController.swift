import AppKit
import UniformTypeIdentifiers
import UserNotifications
import WebKit

/// An unhandled key in a web view makes AppKit beep; the app's own shortcuts are plain keys, so stay quiet.
final class AppWindow: NSWindow {
    override func noResponder(for eventSelector: Selector) {
        if eventSelector == #selector(NSResponder.keyDown(with:)) { return }
        super.noResponder(for: eventSelector)
    }
}

final class WebController: NSObject, WKNavigationDelegate, WKUIDelegate, WKScriptMessageHandlerWithReply {
    let webView: WKWebView
    let play = PlayController()
    weak var owner: AppDelegate?

    override init() {
        let config = WKWebViewConfiguration()
        config.websiteDataStore = .default()
        let marker = WKUserScript(source: "document.documentElement.dataset.shell='mac'", injectionTime: .atDocumentStart, forMainFrameOnly: true)
        config.userContentController.addUserScript(marker)
        // Live stats keep reading the game while the window is behind others.
        if #available(macOS 14.0, *) { config.preferences.inactiveSchedulingPolicy = .none }
        webView = WKWebView(frame: .zero, configuration: config)
        super.init()
        config.userContentController.addScriptMessageHandler(self, contentWorld: .page, name: "vsg")
        webView.navigationDelegate = self
        webView.uiDelegate = self
        webView.allowsBackForwardNavigationGestures = true
        webView.setValue(false, forKey: "drawsBackground")
        if #available(macOS 13.3, *) { webView.isInspectable = UserDefaults.standard.bool(forKey: "inspectable") }
        play.onState = { [weak self] state in self?.dispatch("playstate", state) }
    }

    /// App → page: a DOM event on the document, the same shape the Windows app sends.
    func dispatch(_ event: String, _ detail: [String: Any]) {
        guard let data = try? JSONSerialization.data(withJSONObject: detail), let json = String(data: data, encoding: .utf8) else { return }
        webView.evaluateJavaScript("document.dispatchEvent(new CustomEvent('\(event)',{detail:\(json)}))")
    }

    func load(_ path: String) {
        webView.load(URLRequest(url: URL(string: path, relativeTo: serverBase)!))
    }

    func webView(_ webView: WKWebView, didCommit navigation: WKNavigation!) {
        if webView.url?.path != "/play" { play.hide() }
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        owner?.pageDidLoad()
    }

    func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard let url = action.request.url else { return decisionHandler(.cancel) }
        if url.isFileURL {
            // A file dropped outside the drop zone would replace the page; import it instead.
            owner?.importFiles([url])
            return decisionHandler(.cancel)
        }
        if url.host == serverBase.host || url.scheme == "about" || url.scheme == "blob" { return decisionHandler(.allow) }
        NSWorkspace.shared.open(url)
        decisionHandler(.cancel)
    }

    func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration, for action: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        if let url = action.request.url { NSWorkspace.shared.open(url) }
        return nil
    }

    func webView(_ webView: WKWebView, runOpenPanelWith parameters: WKOpenPanelParameters, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping ([URL]?) -> Void) {
        let panel = NSOpenPanel()
        panel.allowsMultipleSelection = parameters.allowsMultipleSelection
        panel.canChooseDirectories = false
        panel.beginSheetModal(for: webView.window!) { completionHandler($0 == .OK ? panel.urls : nil) }
    }

    func userContentController(_ controller: WKUserContentController, didReceive message: WKScriptMessage, replyHandler: @escaping (Any?, String?) -> Void) {
        guard let body = message.body as? [String: Any], let name = body["name"] as? String else {
            return replyHandler(nil, "bad message")
        }
        let args = body["args"] as? [String: Any] ?? [:]
        switch name {
        case "sync":
            owner?.applyState(args)
            replyHandler(nil, nil)
        case "copy":
            NSPasteboard.general.clearContents()
            NSPasteboard.general.setString(args["text"] as? String ?? "", forType: .string)
            replyHandler(true, nil)
        case "saveFile":
            saveFile(args, replyHandler)
        case "pickFolder":
            pickFolder(args, replyHandler)
        case "reveal":
            if let path = args["path"] as? String { NSWorkspace.shared.activateFileViewerSelecting([URL(fileURLWithPath: path)]) }
            replyHandler(nil, nil)
        case "openPrivacySettings":
            NSWorkspace.shared.open(URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_FilesAndFolders")!)
            replyHandler(nil, nil)
        case "appInfo":
            replyHandler(["version": Updater.currentVersion], nil)
        case "checkUpdate":
            owner?.updater.check { replyHandler($0, $1) }
        case "installUpdate":
            owner?.installUpdate { replyHandler($0, $1) }
        case "play" where args["action"] as? String == "snapshot":
            play.snapshot(width: args["width"] as? Double ?? 1000) { replyHandler($0.map { ["image": $0] } ?? NSNull(), nil) }
        case "play":
            replyHandler(play.handle(args), nil)
        case "notify":
            notify(args)
            replyHandler(nil, nil)
        default:
            replyHandler(nil, "unknown call \(name)")
        }
    }

    private func saveFile(_ args: [String: Any], _ reply: @escaping (Any?, String?) -> Void) {
        guard let base64 = args["base64"] as? String, let data = Data(base64Encoded: base64) else { return reply(nil, "bad file") }
        let panel = NSSavePanel()
        panel.nameFieldStringValue = args["name"] as? String ?? "positions.zip"
        panel.allowedContentTypes = [.zip]
        panel.beginSheetModal(for: webView.window!) { response in
            guard response == .OK, let url = panel.url else { return reply(nil, nil) }
            do {
                try data.write(to: url, options: .atomic)
                reply(url.path, nil)
            } catch {
                reply(nil, error.localizedDescription)
            }
        }
    }

    private func pickFolder(_ args: [String: Any], _ reply: @escaping (Any?, String?) -> Void) {
        let panel = NSOpenPanel()
        panel.canChooseFiles = false
        panel.canChooseDirectories = true
        panel.canCreateDirectories = false
        if let start = args["start"] as? String { panel.directoryURL = URL(fileURLWithPath: start) }
        panel.beginSheetModal(for: webView.window!) { reply($0 == .OK ? panel.url?.path : nil, nil) }
    }

    private func notify(_ args: [String: Any]) {
        guard !NSApp.isActive else { return }
        let center = UNUserNotificationCenter.current()
        center.requestAuthorization(options: [.alert, .sound]) { granted, _ in
            guard granted else { return }
            let content = UNMutableNotificationContent()
            content.title = args["title"] as? String ?? "VS Gammon"
            content.body = args["body"] as? String ?? ""
            center.add(UNNotificationRequest(identifier: UUID().uuidString, content: content, trigger: nil))
        }
    }
}
